"""ENTSO-E Transparency Platform data client.

Uses the entsoe-py library (already installed).
API docs: https://documenter.getpostman.com/view/7009892/2s93JtP3F6
entsoe-py docs: https://github.com/EnergieID/entsoe-py

Data available:
- Day-ahead prices (hourly, all EU bidding zones)
- Generation forecasts (wind onshore/offshore, solar, by TSO area)
- Actual generation (by type: wind, solar, gas, coal, nuclear, hydro, etc.)
- Load forecasts and actuals
- Cross-border physical flows
- Generation unit outages (REMIT UMMs)
- Imbalance prices
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional
import pandas as pd

from dotenv import load_dotenv
import requests_cache
from retry_requests import retry
from entsoe.entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError, InvalidBusinessParameterError

try:
    from .ote_client import get_official_exchange_rate
    from .config import get_config
    from .energy_utils import (
        get_entsoe_area_code,
        delivery_date_to_entsoe_period,
        handle_dst_transition,
        format_price_table,
        get_cache_path,
        CET,
    )
    from . import cache_layer
except ImportError:
    from ote_client import get_official_exchange_rate
    from config import get_config
    from energy_utils import (
        get_entsoe_area_code,
        delivery_date_to_entsoe_period,
        handle_dst_transition,
        format_price_table,
        get_cache_path,
        CET,
    )
    import cache_layer

load_dotenv()

logger = logging.getLogger(__name__)


class Pandas2EntsoeWrapper:
    """
    Wraps EntsoePandasClient to bypass the pandas 2.0+ timezone inference bug.
    Forces start/end parameters to UTC before querying, preventing the 'Inferred 
    time zone not equal to passed time zone' error, and restores the original 
    timezone (CET/Europe/Berlin) on the returned data.
    """

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if not callable(attr) or not name.startswith('query_'):
            return attr

        def wrapper(*args, **kwargs):
            new_args = list(args)
            orig_tz = None

            # Intercept kwargs
            if 'start' in kwargs and hasattr(kwargs['start'], 'tz'):
                orig_tz = kwargs['start'].tz
                kwargs['start'] = kwargs['start'].tz_convert('UTC')
            if 'end' in kwargs and hasattr(kwargs['end'], 'tz'):
                orig_tz = orig_tz or kwargs['end'].tz
                kwargs['end'] = kwargs['end'].tz_convert('UTC')

            # Intercept positional args
            for i, val in enumerate(new_args):
                if hasattr(val, 'tz') and isinstance(val, pd.Timestamp):
                    orig_tz = orig_tz or val.tz
                    new_args[i] = val.tz_convert('UTC')

            # Make the API call using UTC bounds
            result = attr(*new_args, **kwargs)

            # Re-localize index to original timezone
            if result is not None and hasattr(result, 'index') and isinstance(result.index, pd.DatetimeIndex):
                if result.index.tz is not None and orig_tz is not None:
                    result = result.tz_convert(orig_tz)

            return result
        return wrapper


_client = None


def _get_client() -> EntsoePandasClient:
    """Create and return an ENTSO-E client with the configured API key and retry logic."""
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("ENTSOE_API_KEY")
    if not api_key:
        config = get_config()
        api_key = config.get("entsoe_api_key")

    if not api_key:
        raise ValueError(
            "ENTSOE_API_KEY not found in environment or config. "
            "Set ENTSOE_API_KEY env var or 'entsoe_api_key' in config."
        )

    # Inject a retry session to perfectly handle ENTSO-E 503 Rate Limits
    cache_session = requests_cache.CachedSession('.entsoe_cache', expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.5)

    base_client = EntsoePandasClient(api_key=api_key, session=retry_session)
    # Wrap the client to fix pandas 2.0+ timezone crash
    _client = Pandas2EntsoeWrapper(base_client)
    return _client


def _drop_zero_wind_for_cz(df: pd.DataFrame, market_area: str) -> pd.DataFrame:
    """Drops Wind-related columns if they are entirely zero for the CZ market."""
    if df is not None and not df.empty and market_area.upper() == 'CZ':
        cols_to_drop = [col for col in df.columns if 'Wind' in col and (df[col] == 0).all()]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)
    return df


def _format_index(df: pd.DataFrame, resample_hourly: bool = True) -> pd.DataFrame:
    """Format DatetimeIndex, resample to save LLM tokens, and calculate variance metrics."""
    if df is not None and not df.empty and isinstance(df.index, pd.DatetimeIndex):
        if resample_hourly:
            agg_dict = {}
            for col in df.columns:
                # Selectively apply variance only to volatile financial/system metrics
                if any(k in col for k in ['Price', 'Imbalance']):
                    agg_dict[col] = ['mean', 'std', ('Range', lambda x: x.max() - x.min())]
                else:
                    # For Load, Generation, and Flows, the mean anchor is sufficient
                    agg_dict[col] = ['mean']

            resampled = df.resample('1h').agg(agg_dict)

            # Flatten the MultiIndex columns
            new_cols = []
            for col, agg_func in resampled.columns:
                if agg_func == 'mean':
                    new_cols.append(col)
                elif agg_func == 'std':
                    new_cols.append(f"{col} StdDev")
                elif agg_func == 'Range':
                    new_cols.append(f"{col} Range")

            resampled.columns = new_cols
            df = resampled

        df = df.round(3)  # Round to 3 decimals for cleaner display
        df.index = df.index.strftime('%H:%M')
        df.index.name = "Hour"
    return df


# ─────────────────────────────────────────────
# PRICE DATA
# ─────────────────────────────────────────────


def query_day_ahead_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch day-ahead auction prices for a given date and bidding zone."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)
        try:
            series = client.query_day_ahead_prices(area_code, start=start, end=end)
            if isinstance(series, pd.Series):
                df = series.to_frame(name="Price EUR/MWh")
            else:
                df = pd.DataFrame(series)
                df.columns = ["Price EUR/MWh"]

            df.index.name = "Delivery Hour (CET)"
            return handle_dst_transition(df)
        except NoMatchingDataError:
            logger.warning(f"No day-ahead prices for {market_area} on {delivery_date}")
            return pd.DataFrame(columns=["Price EUR/MWh"])

    df = cache_layer._load_or_fetch("entsoe", "day_ahead_prices", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No day-ahead prices available for {market_area} on {delivery_date}")
        return f"# No day-ahead prices available for {market_area} on {delivery_date}"

    df = _format_index(df.copy())
    header = f"# Day-Ahead Prices for {market_area} on {delivery_date}\n# Source: ENTSO-E Transparency Platform\n# Unit: EUR/MWh\n\n"
    return header + df.to_csv()


def query_intraday_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
    auction_sequence: Annotated[Optional[int], "Intraday auction number: 1, 2, or 3. None for all."] = None,
) -> str:
    """Fetch intraday auction prices (XBID/CIDAR) for a given date and zone."""
    # return "Intraday prices are currently unavailable due to ENTSO-E API changes. This will be re-enabled in Phase 2 after we implement the new API endpoints and data parsing logic."

    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)

        if auction_sequence is not None:
            try:
                series = client.query_intraday_prices(area_code, start=start, end=end, sequence=auction_sequence)
                df = series.to_frame(
                    name=f"IDA{auction_sequence} Price EUR/MWh") if isinstance(series, pd.Series) else pd.DataFrame(series)
                df.index.name = "Delivery Hour (CET)"
                return handle_dst_transition(df)
            except NoMatchingDataError:
                logger.warning(
                    f"No intraday prices for sequence {auction_sequence} in {market_area} on {delivery_date}")
                return pd.DataFrame()

        all_auctions = {}
        for seq in [1, 2, 3]:
            try:
                series = client.query_intraday_prices(area_code, start=start, end=end, sequence=seq)
                if not series.empty:
                    all_auctions[f"IDA{seq}"] = series
            except (NoMatchingDataError, InvalidBusinessParameterError):
                logger.warning(f"No intraday prices for sequence {seq} in {market_area} on {delivery_date}")
                continue

        if not all_auctions:
            logger.warning(f"No intraday prices available for {market_area} on {delivery_date}")
            return pd.DataFrame()

        df = pd.DataFrame(all_auctions)
        df.index.name = "Delivery Hour (CET)"
        return handle_dst_transition(df)

    df = cache_layer._load_or_fetch("entsoe", "intraday_prices", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No intraday prices available for {market_area} on {delivery_date}")
        return f"# No intraday prices available for {market_area} on {delivery_date}"

    df = _format_index(df.copy())
    header = f"# Intraday Auction Prices for {market_area} on {delivery_date}\n# Source: ENTSO-E (XBID)\n# Unit: EUR/MWh\n\n"
    return header + df.to_csv()


# ─────────────────────────────────────────────
# GENERATION FORECASTS (wind, solar)
# ─────────────────────────────────────────────

def query_solar_forecast(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch day-ahead wind and solar generation forecasts."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)
        try:
            df = client.query_wind_and_solar_forecast(area_code, start=start, end=end)
            if df.empty:
                logger.warning(f"No wind/solar forecast data for {market_area} on {delivery_date}")
                return pd.DataFrame()

            if isinstance(df, pd.Series):
                df = df.to_frame(name=df.name or "Total Renewable")

            df = df.copy()
            wind_on = df["Wind Onshore"].fillna(0) if "Wind Onshore" in df.columns else pd.Series(0, index=df.index)
            wind_off = df["Wind Offshore"].fillna(0) if "Wind Offshore" in df.columns else pd.Series(0, index=df.index)
            solar = df["Solar"].fillna(0) if "Solar" in df.columns else pd.Series(0, index=df.index)

            df["Wind Total MW"] = wind_on + wind_off
            df["Solar MW"] = solar
            # df["Total Renewable MW"] = df["Wind Total MW"] + df["Solar MW"]

            # Keep only the aggregated columns to save LLM tokens as requested by Phase 1
            df = df[["Wind Total MW", "Solar MW"]]
            df.index.name = "Hour (CET)"
            return handle_dst_transition(df)
        except NoMatchingDataError:
            logger.warning(f"No wind/solar forecast found for {market_area} on {delivery_date}")
            return pd.DataFrame()

    df = cache_layer._load_or_fetch("entsoe", "wind_solar_forecast", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No wind/solar forecast available for {market_area} on {delivery_date}")
        return f"# No wind/solar forecast available for {market_area} on {delivery_date}"

    # Drop wind columns if they are fully zero for CZ
    df = _drop_zero_wind_for_cz(df, market_area)

    df = _format_index(df.copy())
    header = f"# Solar Day-Ahead Forecast for {market_area} on {delivery_date}\n# Source: ENTSO-E (TSO forecasts)\n# Unit: MW\n\n"
    return header + df.to_csv()


def query_actual_generation(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch actual generation by production type for a given date."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)
        try:
            df = client.query_generation(area_code, start=start, end=end, psr_type=None)
            if df.empty:
                logger.warning(f"No actual generation data for {market_area} on {delivery_date}")
                return pd.DataFrame()

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [
                    f"{col[0]} (Consumption)" if col[1] == "Actual Consumption" else f"{col[0]}"
                    for col in df.columns
                ]

            df = df.fillna(0)
            df.index.name = "Hour (CET)"
            return handle_dst_transition(df)
        except NoMatchingDataError:
            logger.warning(f"No actual generation found for {market_area} on {delivery_date}")
            return pd.DataFrame()

    df = cache_layer._load_or_fetch("entsoe", "actual_generation", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No generation data available for {market_area} on {delivery_date}")
        return f"# No generation data available for {market_area} on {delivery_date}"

    # Safe to call here too; actual wind won't be zero, but protects against future flat days
    df = _drop_zero_wind_for_cz(df, market_area)

    df = _format_index(df.copy())
    header = f"# Actual Generation by Type for {market_area} on {delivery_date}\n# Source: ENTSO-E\n# Unit: MW\n\n"
    return header + df.to_csv()


def query_generation_forecast_updates(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch updated (intraday) wind and solar forecasts and compute deltas."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)

        # Fetch Day-Ahead baseline
        try:
            da_raw = client.query_wind_and_solar_forecast(area_code, start=start, end=end)
            da_forecast = da_raw.to_frame(name="Total Generation") if isinstance(da_raw, pd.Series) else da_raw
        except NoMatchingDataError:
            logger.warning(f"No day-ahead generation forecast found for {market_area} on {delivery_date}")
            da_forecast = pd.DataFrame()

        # CRITICAL FIX: Use the specific Intraday Wind & Solar endpoint
        try:
            id_raw = client.query_intraday_wind_and_solar_forecast(area_code, start=start, end=end)
            id_forecast = id_raw.to_frame(name="Total Generation") if isinstance(id_raw, pd.Series) else id_raw
        except (NoMatchingDataError, InvalidBusinessParameterError, AttributeError):
            logger.warning(f"No intraday generation forecast found for {market_area} on {delivery_date}")
            id_forecast = pd.DataFrame()

        if da_forecast.empty and id_forecast.empty:
            logger.warning(f"No generation forecast data (day-ahead or intraday) for {market_area} on {delivery_date}")
            return pd.DataFrame()

        result = pd.DataFrame(index=da_forecast.index if not da_forecast.empty else id_forecast.index)
        result.index.name = "Hour (CET)"

        # Safely map Day-Ahead columns
        result["DA Wind Onshore"] = da_forecast.get("Wind Onshore", pd.Series(
            dtype=float)) if not da_forecast.empty else pd.Series(dtype=float)
        result["DA Wind Offshore"] = da_forecast.get("Wind Offshore", pd.Series(
            dtype=float)) if not da_forecast.empty else pd.Series(dtype=float)
        result["DA Solar"] = da_forecast.get("Solar", pd.Series(
            dtype=float)) if not da_forecast.empty else pd.Series(dtype=float)

        # Safely map Intraday columns
        if not id_forecast.empty:
            result["ID Wind Onshore"] = id_forecast.get("Wind Onshore", result["DA Wind Onshore"])
            result["ID Wind Offshore"] = id_forecast.get("Wind Offshore", result["DA Wind Offshore"])
            result["ID Solar"] = id_forecast.get("Solar", result["DA Solar"])
        else:
            logger.warning(
                f"Intraday forecast missing for {market_area} on {delivery_date}. Using Day-Ahead as fallback.")
            result["ID Wind Onshore"] = result["DA Wind Onshore"]
            result["ID Wind Offshore"] = result["DA Wind Offshore"]
            result["ID Solar"] = result["DA Solar"]

        # If Intraday has NaNs for specific hours, fallback to Day-Ahead for those exact hours
        result["ID Wind Onshore"] = result["ID Wind Onshore"].fillna(result["DA Wind Onshore"])
        result["ID Wind Offshore"] = result["ID Wind Offshore"].fillna(result["DA Wind Offshore"])
        result["ID Solar"] = result["ID Solar"].fillna(result["DA Solar"])

        # Now it is safe to fill any remaining absolute gaps with 0
        result = result.fillna(0)

        result["Wind Delta"] = (result["ID Wind Onshore"] + result["ID Wind Offshore"]) - \
                               (result["DA Wind Onshore"] + result["DA Wind Offshore"])
        result["Solar Delta"] = result["ID Solar"] - result["DA Solar"]

        # Token saving logic: Check if all deltas are exactly zero
        is_fallback = (result["Wind Delta"] == 0).all() and (result["Solar Delta"] == 0).all()

        if is_fallback:
            logger.warning(
                f"Intraday forecast updates for {market_area} on {delivery_date} are identical to Day-Ahead forecasts. This likely indicates missing intraday data, and the deltas are all zero. Displaying Day-Ahead baseline only.")
            # Drop the redundant Intraday and Delta columns to save LLM tokens
            cols_to_drop = ["ID Wind Onshore", "ID Wind Offshore", "ID Solar", "Wind Delta", "Solar Delta"]
            result = result.drop(columns=[c for c in cols_to_drop if c in result.columns])

        return handle_dst_transition(result)

    df = cache_layer._load_or_fetch("entsoe", "generation_forecast_updates", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No forecast updates available for {market_area} on {delivery_date}")
        return f"# No forecast updates available for {market_area} on {delivery_date}"

    # Determine if it was a fallback based on the cached/returned df columns BEFORE cleaning wind
    is_fallback_df = "Wind Delta" not in df.columns

    # Drop wind columns if they are fully zero for CZ
    df = _drop_zero_wind_for_cz(df, market_area)

    df = _format_index(df.copy())
    header = f"# Forecast Updates for {market_area} on {delivery_date}\n# Source: ENTSO-E\n"

    if is_fallback_df:
        header += "# WARNING: Intraday forecast updates unavailable. Displaying Day-Ahead baseline only.\n# Unit: MW\n\n"
    else:
        header += "# Unit: MW (delta = intraday_forecast - day_ahead_forecast)\n\n"

    return header + df.to_csv()
# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────


def query_load_forecast(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch day-ahead load (demand) forecast."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)
        try:
            series = client.query_load_forecast(area_code, start=start, end=end)
            if isinstance(series, pd.Series):
                df = series.to_frame(name="Load Forecast MW")
            elif isinstance(series, pd.DataFrame):
                df = series.rename(columns={series.columns[0]: "Load Forecast MW"})
            else:
                df = pd.DataFrame({"Load Forecast MW": [series]}, index=[start])

            df.index.name = "Hour (CET)"
            return handle_dst_transition(df)
        except NoMatchingDataError:
            logger.warning(f"No load forecast found for {market_area} on {delivery_date}")
            return pd.DataFrame(columns=["Load Forecast MW"])

    df = cache_layer._load_or_fetch("entsoe", "load_forecast", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No load forecast available for {market_area} on {delivery_date}")
        return f"# No load forecast available for {market_area} on {delivery_date}"

    df = _format_index(df.copy())
    header = f"# Load Forecast for {market_area} on {delivery_date}\n# Source: ENTSO-E\n# Unit: MW\n\n"
    return header + df.to_csv()


def query_actual_load(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch actual total load."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)
        try:
            series = client.query_load(area_code, start=start, end=end)
            if isinstance(series, pd.Series):
                df = series.to_frame(name="Actual Load MW")
            elif isinstance(series, pd.DataFrame):
                df = series.rename(columns={series.columns[0]: "Actual Load MW"})
            else:
                df = pd.DataFrame({"Actual Load MW": [series]}, index=[start])

            df.index.name = "Hour (CET)"
            return handle_dst_transition(df)
        except NoMatchingDataError:
            logger.warning(f"No actual load data found for {market_area} on {delivery_date}")
            return pd.DataFrame(columns=["Actual Load MW"])

    df = cache_layer._load_or_fetch("entsoe", "actual_load", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No actual load data available for {market_area} on {delivery_date}")
        return f"# No actual load data available for {market_area} on {delivery_date}"

    df = _format_index(df.copy())
    header = f"# Actual Load for {market_area} on {delivery_date}\n# Source: ENTSO-E\n# Unit: MW\n\n"
    return header + df.to_csv()


# ─────────────────────────────────────────────
# CROSS-BORDER FLOWS
# ─────────────────────────────────────────────

_NEIGHBOR_MAP = {
    "DE-LU": ["AT", "FR", "NL", "PL", "CZ", "DK1", "DK2", "CH"],
    "CZ": ["DE-LU", "AT", "PL", "SK"],
    "AT": ["DE-LU", "CZ", "IT", "SI", "CH"],
    "PL": ["DE-LU", "CZ", "SE", "LT"],
}


def query_crossborder_flows(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch cross-border physical flows for a bidding zone."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)

        neighbors = _NEIGHBOR_MAP.get(market_area, [])
        result_data = {}

        for neighbor in neighbors:
            try:
                neighbor_code = get_entsoe_area_code(neighbor)

                # Fetch actual physical flows
                flows = client.query_crossborder_flows(area_code, neighbor_code, start=start, end=end)

                # Fetch maximum allowed capacity (NTC)
                has_ntc = False
                try:
                    ntc = client.query_net_transfer_capacity_dayahead(area_code, neighbor_code, start=start, end=end)
                    has_ntc = True
                except NoMatchingDataError:
                    # In Flow-Based Market Coupling regions (like CZ/DE), bilateral NTC is not published.
                    logger.debug(f"No bilateral NTC data for {market_area}-{neighbor}. Skipping congestion calc.")

                if not flows.empty:
                    border_df = pd.DataFrame({f"{neighbor} Flow": flows})

                    if has_ntc:
                        border_df[f"{neighbor} Capacity"] = ntc
                        capacity_safe = border_df[f"{neighbor} Capacity"].replace(0, pd.NA)
                        border_df[f"{neighbor} Congestion %"] = (
                            border_df[f"{neighbor} Flow"].abs() / capacity_safe) * 100
                    else:
                        logger.debug(f"No NTC data for {market_area}-{neighbor}. Congestion % will not be calculated.")

                    # Fill NaNs back to 0, but only for existing columns
                    border_df = border_df.fillna(0).round(1)
                    result_data[neighbor] = border_df
                else:
                    logger.warning(f"No flow data between {market_area} and {neighbor} on {delivery_date}")

            except (NoMatchingDataError, InvalidBusinessParameterError):
                logger.warning(f"No cross-border flow data between {market_area} and {neighbor} on {delivery_date}")
                continue

        if not result_data:
            logger.warning(f"No cross-border flow data for {market_area} on {delivery_date}")
            return pd.DataFrame()

        # Combine all the individual border DataFrames
        result_df = pd.concat(result_data.values(), axis=1)

        # Ffill propagates lower-resolution data to match higher-resolution data
        result_df = result_df.ffill().fillna(0)

        # Calculate the total Net Import based only on the Flow columns
        flow_cols = [col for col in result_df.columns if "Flow" in col]
        result_df["Net Import MW"] = result_df[flow_cols].sum(axis=1)
        result_df.index.name = "Hour (CET)"

        return handle_dst_transition(result_df)

    df = cache_layer._load_or_fetch("entsoe", "crossborder_flows", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No cross-border flow data available for {market_area} on {delivery_date}")
        return f"# No cross-border flow data for {market_area} on {delivery_date}"

    df = _format_index(df.copy())
    header = f"# Cross-Border Flows for {market_area} on {delivery_date}\n# Source: ENTSO-E\n# Positive = import into {market_area}, Negative = export\n# Unit: MW\n\n"
    return header + df.to_csv()


# ─────────────────────────────────────────────
# OUTAGES (REMIT UMMs)
# ─────────────────────────────────────────────

def query_outages(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch generation unit unavailabilities (planned and unplanned outages)."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)
        try:
            df = client.query_unavailability_of_generation_units(area_code, start=start, end=end)
            if df.empty:
                logger.warning(f"No outage data for {market_area} on {delivery_date}")
                return pd.DataFrame()
            return df
        except NoMatchingDataError:
            logger.warning(f"No outage data found for {market_area} on {delivery_date}")
            return pd.DataFrame()

    df = cache_layer._load_or_fetch("entsoe", "outages", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No outage data available for {market_area} on {delivery_date}")
        return f"# No outage data for {market_area} on {delivery_date}"

    # Move the index (created_doc_time) into a regular column to track when the market was notified
    if df.index.name == 'created_doc_time' or isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index(names=['published_time'])

    # Include the high-value columns for the Energy News & System State Analysts
    cols_to_keep = [
        'published_time', 'plant_type', 'production_resource_name',
        'businesstype', 'docstatus',
        'nominal_power', 'avail_qty', 'start', 'end'
    ]
    avail_cols = [c for c in cols_to_keep if c in df.columns]
    df_clean = df[avail_cols].copy()

    # Filter out cancelled outages - false signals destroy intraday strategies
    if 'docstatus' in df_clean.columns:
        df_clean = df_clean[df_clean['docstatus'] != 'Cancelled']
        df_clean = df_clean.drop(columns=['docstatus'])

    # Deduplicate using the UNIT name (psr_name) rather than the whole plant name
    dedup_subset = [c for c in ['production_resource_psr_name', 'start', 'end'] if c in df_clean.columns]
    if len(dedup_subset) == 3:
        # Sort by published_time first so we keep the newest revision if there are duplicates
        if 'published_time' in df_clean.columns:
            df_clean = df_clean.sort_values('published_time', ascending=False)
        df_clean = df_clean.drop_duplicates(subset=dedup_subset)

    # Safely convert returned localized timestamps to CET string formats
    for time_col in ['published_time', 'start', 'end']:
        if time_col in df_clean.columns:
            df_clean[time_col] = pd.to_datetime(df_clean[time_col], utc=True).dt.tz_convert(
                'Europe/Berlin').dt.strftime('%Y-%m-%d %H:%M')

    # Calculate the unavailable MW
    if "avail_qty" in df_clean.columns and "nominal_power" in df_clean.columns:
        # CRITICAL FIX: Force string fields into numeric types before subtraction
        df_clean["nominal_power"] = pd.to_numeric(df_clean["nominal_power"], errors="coerce")
        df_clean["avail_qty"] = pd.to_numeric(df_clean["avail_qty"], errors="coerce")

        df_clean["unavailable_MW"] = df_clean["nominal_power"].fillna(0) - df_clean["avail_qty"].fillna(0)
        df_clean = df_clean[df_clean["unavailable_MW"] > 0]

        # Rename the columns for a much cleaner output table
        rename_dict = {
            "nominal_power": "nominal_capacity",
            "avail_qty": "available_capacity",
            "businesstype": "outage_type",
            "production_resource_name": "plant_name",
        }
        df_clean = df_clean.rename(columns=rename_dict)

    # --- FORMAT OUTPUT SPECIFICALLY FOR LLM AGENT CONSUMPTION ---

    summary = f"# Generation Outages (REMIT UMMs) for {market_area} on {delivery_date}\n\n"

    # 1. System State Analyst Pre-computations (Saves LLM tokens and math errors)
    if "unavailable_MW" in df_clean.columns and "outage_type" in df_clean.columns:
        total_planned = df_clean[df_clean['outage_type'] == 'Planned maintenance']['unavailable_MW'].sum()
        total_unplanned = df_clean[df_clean['outage_type'] == 'Unplanned outage']['unavailable_MW'].sum()

        summary += f"## System State Summary\n"
        summary += f"* Total Unavailable Capacity: {total_planned + total_unplanned:.0f} MW\n"
        summary += f"  - Planned Maintenance (Priced into DA): {total_planned:.0f} MW\n"
        summary += f"  - Unplanned Outages (Intraday Shocks): {total_unplanned:.0f} MW\n\n"

        if "plant_type" in df_clean.columns:
            plant_summary = df_clean.groupby('plant_type')['unavailable_MW'].sum().sort_values(ascending=False)
            summary += "## Offline Capacity by Plant Type\n"
            for plant, mw in plant_summary.items():
                summary += f"* {plant}: {mw:.0f} MW\n"
            summary += "\n"

    # 2. Energy News Analyst Feed (Sorted by publication time to highlight new information)
    if "published_time" in df_clean.columns:
        df_clean = df_clean.sort_values(by="published_time", ascending=False)
    elif "start" in df_clean.columns:
        df_clean = df_clean.sort_values(by="start", ascending=False)

    # Push bulky EIC codes to the far right so the LLM reads the critical text fields first
    if 'eic_code' in df_clean.columns:
        cols = [c for c in df_clean.columns if c != 'eic_code'] + ['eic_code']
        df_clean = df_clean[cols]

    summary += "## Detailed REMIT Messages (Sorted by Newest Publication First)\n"
    summary += df_clean.to_string(index=False)

    return summary
# ─────────────────────────────────────────────
# IMBALANCE / BALANCING
# ─────────────────────────────────────────────


def query_imbalance_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch imbalance (balancing energy) prices and volumes."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)

        # 1. Fetch Imbalance Prices
        try:
            price_df = client.query_imbalance_prices(area_code, start=start, end=end)
        except NoMatchingDataError:
            logger.warning(f"No imbalance price data found for {market_area} on {delivery_date}")
            price_df = pd.DataFrame()

        # 2. Fetch Imbalance Volumes (Physical system state indicator)
        try:
            vol_df = client.query_imbalance_volumes(area_code, start=start, end=end)

            # CRITICAL FIX: Convert Series to DataFrame safely before checking columns
            if isinstance(vol_df, pd.Series):
                vol_df = vol_df.to_frame(name="Imbalance Volume MW")

            # Flatten multi-index if ENTSO-E returns one for volumes
            if not vol_df.empty and isinstance(vol_df.columns, pd.MultiIndex):
                vol_df.columns = [f"{col[0]} {col[1]}" for col in vol_df.columns]
        except (NoMatchingDataError, InvalidBusinessParameterError):
            logger.warning(f"No imbalance volume data found for {market_area} on {delivery_date}")
            vol_df = pd.DataFrame()

        if price_df.empty and vol_df.empty:
            logger.warning(f"No imbalance price or volume data for {market_area} on {delivery_date}")
            return pd.DataFrame()

        # 3. Combine Prices and Volumes safely on the DatetimeIndex
        df = pd.concat([price_df, vol_df], axis=1)

        # 4. Clean up single-imbalance pricing markets (like CZ)
        # Round first to kill microscopic floating-point noise before comparing
        df = df.round(3)
        if "Long" in df.columns and "Short" in df.columns:
            if df["Long"].equals(df["Short"]):
                df["Imbalance Price EUR/MWh"] = df["Long"]
                df = df.drop(columns=["Long", "Short"])

        df.index.name = "Hour (CET)"
        return handle_dst_transition(df)

    # Note: Changed cache key to 'imbalance_data' since it now holds both price and volume
    df = cache_layer._load_or_fetch("entsoe", "imbalance_data", market_area, delivery_date, fetch)
    if df is None or df.empty:
        logger.warning(f"No imbalance data available for {market_area} on {delivery_date}")
        return f"# No imbalance data for {market_area} on {delivery_date}"

    # Currency conversion for CZ
    exchange_rate = None
    if market_area.upper() == "CZ" and not df.empty:
        exchange_rate = get_official_exchange_rate(delivery_date)
        for col in df.columns:
            if "Price" in col or "Cost" in col or "EUR" in col:
                df[col] = (df[col] / exchange_rate).round(3)

    df = _format_index(df.copy())

    header = f"# Imbalance Prices and Volumes for {market_area} on {delivery_date}\n# Source: ENTSO-E\n# Unit: EUR/MWh (Prices), MW (Volumes)\n"
    if exchange_rate is not None:
        header += f"# Note: Financial values converted from CZK to EUR at official rate of {exchange_rate} CZK/EUR\n"
    header += "\n"

    return header + df.to_csv()


# ─────────────────────────────────────────────
# RESIDUAL LOAD
# ─────────────────────────────────────────────

def query_residual_load(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
    use_actuals: Annotated[bool, "Use actual load instead of day-ahead forecast for live trading"] = True,
) -> str:
    """Fetch residual load forecast or actuals."""
    def fetch():
        client = _get_client()
        area_code = get_entsoe_area_code(market_area)
        start, end = delivery_date_to_entsoe_period(delivery_date)

        # 1. Fetch either actual load or forecasted load based on the toggle
        try:
            if use_actuals:
                load = client.query_load(area_code, start=start, end=end)
                load_col_name = "Actual Load MW"
            else:
                load = client.query_load_forecast(area_code, start=start, end=end)
                load_col_name = "Load Forecast MW"

            if isinstance(load, pd.DataFrame):
                load = load.iloc[:, 0]
        except (NoMatchingDataError, Exception) as e:
            logger.warning(f"Residual Load - Failed to fetch load: {e}")
            load = pd.Series(dtype=float)
            load_col_name = "Actual Load MW" if use_actuals else "Load Forecast MW"

        # 2. Fetch wind and solar forecasts (these remain forecasts as they dictate expected renewable generation)
        try:
            wind_solar = client.query_wind_and_solar_forecast(area_code, start=start, end=end)
        except (NoMatchingDataError, Exception) as e:
            logger.warning(f"Residual Load - Failed to fetch wind/solar: {e}")
            wind_solar = pd.DataFrame()

        if load.empty:
            logger.warning(f"No load data for {market_area} on {delivery_date}, cannot compute residual load")
            return pd.DataFrame()

        result = pd.DataFrame(index=load.index)
        result[load_col_name] = load

        if not wind_solar.empty:
            wind_total = pd.Series(0, index=wind_solar.index)
            if "Wind Onshore" in wind_solar.columns:
                wind_total += wind_solar["Wind Onshore"].fillna(0)
            if "Wind Offshore" in wind_solar.columns:
                wind_total += wind_solar["Wind Offshore"].fillna(0)

            solar = wind_solar["Solar"].fillna(
                0) if "Solar" in wind_solar.columns else pd.Series(0, index=wind_solar.index)

            # Forward fill renewables to match load resolution if necessary
            wind_total = wind_total.reindex(load.index, method='ffill')
            solar = solar.reindex(load.index, method='ffill')

            # FIX 1: Explicitly label columns as forecasts to prevent LLM hallucination
            result["Wind Forecast MW"] = wind_total
            result["Solar Forecast MW"] = solar

            # FIX 2: Restored the previously commented out calculation
            result["Residual Load MW"] = result[load_col_name] - wind_total - solar
        else:
            result["Residual Load MW"] = result[load_col_name]

        result.index.name = "Hour (CET)"
        return handle_dst_transition(result)

    # Use a separate cache key to prevent overwriting forecast data with actuals
    cache_key = "residual_load_actual" if use_actuals else "residual_load"
    df = cache_layer._load_or_fetch("entsoe", cache_key, market_area, delivery_date, fetch)

    if df is None or df.empty:
        logger.warning(f"No residual load data available for {market_area} on {delivery_date}")
        return f"# No residual load data for {market_area} on {delivery_date}"

    # Drop wind columns if they are fully zero for CZ
    df = _drop_zero_wind_for_cz(df, market_area)

    df = _format_index(df.copy())

    type_str = "Actual" if use_actuals else "Forecast"
    # FIX 3: Updated header documentation to reflect the exact mathematical inputs
    header = f"# Residual Load {type_str} for {market_area} on {delivery_date}\n# Source: ENTSO-E (calculated: Load - Wind Forecast - Solar Forecast)\n# Unit: MW\n\n"

    return header + df.to_csv()


if __name__ == "__main__":
    import sys
    import os
    from dotenv import load_dotenv

    load_dotenv()

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-28"
    market_area = sys.argv[2] if len(sys.argv) > 2 else "CZ"

    print(f"Testing ENTSO-E for date: {date}, market: {market_area}")
    print(f"ENTSOE_API_KEY set: {'ENTSOE_API_KEY' in os.environ}")

    if "ENTSOE_API_KEY" not in os.environ:
        print("ERROR: ENTSOE_API_KEY not set. Set it in .env or environment.")
        sys.exit(1)

    try:
        deleted_count = cache_layer.clear_cache(source="entsoe")
        print(f"Deleted {deleted_count} parquet files from the ENTSO-E cache.")
    except Exception as e:
        logger.warning(f"Error clearing cache: {e}")
        pass

    print("\n=== query_day_ahead_prices ===")
    print(query_day_ahead_prices(date, market_area))

    print("\n=== query_intraday_prices ===")
    print(query_intraday_prices(date, market_area))

    print("\n=== query_wind_solar_forecast ===")
    print(query_solar_forecast(date, market_area))

    print("\n=== query_actual_generation ===")
    print(query_actual_generation(date, market_area))

    print("\n=== query_generation_forecast_updates ===")
    print(query_generation_forecast_updates(date, market_area))

    print("\n=== query_load_forecast ===")
    print(query_load_forecast(date, market_area))

    print("\n=== query_actual_load ===")
    print(query_actual_load(date, market_area))

    print("\n=== query_crossborder_flows ===")
    print(query_crossborder_flows(date, market_area))

    print("\n=== query_outages ===")
    print(query_outages(date, market_area))

    print("\n=== query_imbalance_prices ===")
    print(query_imbalance_prices(date, market_area))

    print("\n=== query_residual_load ===")
    print(query_residual_load(date, market_area))

    try:
        deleted_count = cache_layer.clear_cache(source="entsoe")
        print(f"Deleted {deleted_count} parquet files from the ENTSO-E cache.")
    except Exception as e:
        logger.warning(f"Error clearing cache: {e}")
        pass

"""
Reference output
=== query_day_ahead_prices ===
# Day-Ahead Prices for CZ on 2026-04-28
# Source: ENTSO-E Transparency Platform
# Unit: EUR/MWh

Hour,Price EUR/MWh,Price EUR/MWh StdDev,Price EUR/MWh Range
00:00,116.028,4.094,9.54
01:00,111.445,2.348,5.46
02:00,107.975,0.354,0.81
03:00,108.068,0.849,1.92
04:00,110.608,3.477,7.81
05:00,117.18,6.141,13.68
06:00,127.9,3.472,7.9
07:00,126.185,11.947,26.9
08:00,114.608,16.932,38.5
09:00,77.895,37.53,87.23
10:00,29.58,23.688,52.64
11:00,-0.04,0.457,1.05
12:00,-3.802,2.512,5.81
13:00,-14.195,3.898,9.33
14:00,-11.235,3.885,9.16
15:00,8.358,8.685,21.0
16:00,42.168,33.609,78.19
17:00,60.69,37.035,88.04
18:00,96.2,22.189,47.46
19:00,123.477,14.449,33.83
20:00,140.27,3.982,7.99
21:00,121.49,8.395,18.08
22:00,115.8,6.312,14.83
23:00,106.41,3.659,8.75
00:00,100.89,,0.0


=== query_intraday_prices ===
Intraday prices are currently unavailable due to ENTSO-E API changes. This will be re-enabled in Phase 2 after we implement the new API endpoints and data parsing logic.

=== query_wind_solar_forecast ===
# Solar Day-Ahead Forecast for CZ on 2026-04-28
# Source: ENTSO-E (TSO forecasts)
# Unit: MW

Hour,Solar MW
00:00,0.0
01:00,0.0
02:00,0.0
03:00,0.0
04:00,0.0
05:00,18.0
06:00,176.75
07:00,649.75
08:00,1386.0
09:00,2100.0
10:00,2600.5
11:00,2871.5
12:00,2942.0
13:00,2873.5
14:00,2629.25
15:00,2249.25
16:00,1745.25
17:00,1102.5
18:00,499.25
19:00,140.5
20:00,14.75
21:00,0.0
22:00,0.0
23:00,0.0


=== query_actual_generation ===
# Actual Generation by Type for CZ on 2026-04-28
# Source: ENTSO-E
# Unit: MW

Hour,Biomass,Fossil Brown coal/Lignite,Fossil Coal-derived gas,Fossil Gas,Fossil Hard coal,Fossil Oil,Hydro Pumped Storage,Hydro Pumped Storage (Consumption),Hydro Run-of-river and poundage,Hydro Water Reservoir,Nuclear,Other,Other renewable,Solar,Waste,Wind Onshore
00:00,296.515,2584.862,0.0,355.56,80.96,3.082,262.428,0.0,89.727,40.068,3517.698,68.775,270.403,0.0,32.08,39.88
01:00,294.222,2566.555,0.0,144.985,82.375,3.08,68.025,0.0,90.738,28.13,3519.655,68.995,269.645,0.0,31.96,37.365
02:00,292.347,2512.515,0.0,142.728,83.29,3.07,0.0,0.0,90.088,21.968,3523.07,69.348,268.925,0.0,32.405,38.368
03:00,291.285,2534.39,0.0,144.54,83.932,3.072,0.0,0.0,89.158,22.218,3525.83,69.345,268.645,0.0,32.492,41.445
04:00,293.775,2546.498,0.0,155.922,83.628,3.082,0.0,0.0,87.612,27.498,3526.728,68.22,269.865,5.455,32.118,43.425
05:00,295.025,2570.505,0.0,177.835,81.152,3.1,128.495,0.0,89.032,29.47,3525.978,66.61,274.188,50.295,32.265,43.485
06:00,298.068,2626.68,0.0,226.568,80.582,3.14,611.352,0.0,83.025,237.445,3524.478,60.382,284.028,219.88,32.505,43.68
07:00,298.39,2614.232,0.0,218.572,83.418,3.14,605.037,0.0,79.502,360.222,3525.635,60.94,282.805,758.025,32.458,36.54
08:00,299.072,2515.472,0.0,199.288,82.065,3.118,407.25,0.0,78.125,40.945,3527.078,63.132,277.768,1603.478,32.347,29.16
09:00,290.422,1883.832,0.0,162.71,79.048,3.058,108.01,15.892,84.095,16.34,3523.985,66.642,268.98,2410.81,32.08,27.735
10:00,283.062,1298.775,0.0,137.615,68.878,3.002,0.0,596.48,85.015,13.56,3520.745,68.105,261.988,2906.415,31.232,32.705
11:00,283.153,1226.338,0.0,132.795,68.252,2.985,0.0,1085.545,84.36,11.562,3515.44,68.545,260.81,3098.568,31.528,36.992
12:00,280.128,1223.22,0.0,131.392,68.16,2.982,0.0,1107.23,84.695,11.035,3510.175,68.67,259.488,3191.69,31.41,40.982
13:00,279.358,1244.192,0.0,127.972,67.545,2.98,0.0,1098.288,84.43,10.325,3514.552,68.868,259.678,3108.24,31.285,46.365
14:00,281.79,1249.862,0.0,130.51,67.06,2.99,0.0,1088.9,81.4,10.575,3513.645,68.912,261.207,2905.44,31.662,53.19
15:00,282.225,1262.898,0.0,133.602,69.402,2.99,0.0,860.838,81.102,12.335,3510.49,68.615,262.975,2624.365,31.66,63.537
16:00,283.388,1232.058,0.0,137.305,72.778,3.0,0.0,446.448,77.76,55.02,3508.278,67.95,264.205,2146.248,31.482,81.12
17:00,287.968,1442.792,0.0,149.46,75.822,3.035,0.0,0.0,84.428,12.668,3506.662,66.722,268.985,1390.403,32.078,97.77
18:00,299.698,2197.967,0.0,189.28,77.01,3.105,111.778,0.0,83.93,18.842,3506.302,63.502,279.14,606.062,32.52,97.685
19:00,302.795,2474.322,0.0,214.818,77.125,3.138,725.532,0.0,78.59,150.79,3508.125,60.522,283.635,170.875,33.065,107.012
20:00,305.248,2565.552,0.0,218.788,77.84,3.14,729.972,0.0,75.66,538.418,3508.118,60.45,283.735,68.258,33.268,121.288
21:00,301.255,2527.36,0.0,205.045,78.358,3.122,660.48,0.0,76.965,251.415,3512.07,62.388,280.135,0.0,32.94,131.75
22:00,296.065,2482.062,0.0,161.418,79.185,3.08,432.162,0.0,81.305,121.32,3515.795,67.81,271.595,0.0,32.532,126.08
23:00,294.08,2450.668,0.0,147.31,78.65,3.08,179.23,0.0,90.328,18.578,3517.698,68.588,270.588,0.0,32.63,111.93


=== query_generation_forecast_updates ===
# Forecast Updates for CZ on 2026-04-28
# Source: ENTSO-E
# Unit: MW (delta = intraday_forecast - day_ahead_forecast)

Hour,DA Solar,ID Solar,Solar Delta
00:00,0.0,0.0,0.0
01:00,0.0,0.0,0.0
02:00,0.0,0.0,0.0
03:00,0.0,0.0,0.0
04:00,0.0,0.0,0.0
05:00,18.0,16.75,-1.25
06:00,176.75,175.0,-1.75
07:00,649.75,687.25,37.5
08:00,1386.0,1455.5,69.5
09:00,2100.0,2194.0,94.0
10:00,2600.5,2709.75,109.25
11:00,2871.5,3026.5,155.0
12:00,2942.0,3133.0,191.0
13:00,2873.5,3071.0,197.5
14:00,2629.25,2831.0,201.75
15:00,2249.25,2418.75,169.5
16:00,1745.25,1868.25,123.0
17:00,1102.5,1188.25,85.75
18:00,499.25,537.0,37.75
19:00,140.5,150.0,9.5
20:00,14.75,16.0,1.25
21:00,0.0,0.0,0.0
22:00,0.0,0.0,0.0
23:00,0.0,0.0,0.0


=== query_load_forecast ===
# Load Forecast for CZ on 2026-04-28
# Source: ENTSO-E
# Unit: MW

Hour,Load Forecast MW
00:00,5952.0
01:00,5940.0
02:00,5833.0
03:00,5799.5
04:00,5954.75
05:00,6482.75
06:00,7410.25
07:00,7993.25
08:00,8277.25
09:00,8526.75
10:00,8475.25
11:00,8506.25
12:00,8530.0
13:00,8386.75
14:00,8027.25
15:00,7757.5
16:00,7516.25
17:00,7340.5
18:00,7228.0
19:00,7339.0
20:00,7409.5
21:00,7077.5
22:00,6724.0
23:00,6350.5


=== query_actual_load ===
# Actual Load for CZ on 2026-04-28
# Source: ENTSO-E
# Unit: MW

Hour,Actual Load MW
00:00,6041.692
01:00,6000.142
02:00,5869.858
03:00,5863.173
04:00,6060.003
05:00,6614.232
06:00,7621.21
07:00,8108.565
08:00,8409.92
09:00,8675.038
10:00,8634.968
11:00,8510.48
12:00,8517.128
13:00,8467.405
14:00,8074.382
15:00,7957.855
16:00,7673.938
17:00,7461.455
18:00,7263.845
19:00,7430.09
20:00,7463.558
21:00,7050.997
22:00,6722.61
23:00,6392.468


=== query_crossborder_flows ===
# Cross-Border Flows for CZ on 2026-04-28
# Source: ENTSO-E
# Positive = import into CZ, Negative = export
# Unit: MW

Hour,DE-LU Flow,AT Flow,PL Flow,SK Flow,Net Import MW
00:00,637.425,1253.6,0.0,1578.3,3469.325
01:00,811.825,1445.5,0.0,1182.025,3439.35
02:00,861.775,1545.7,0.0,1166.4,3573.875
03:00,785.225,1483.9,0.0,1312.3,3581.425
04:00,690.375,1243.5,0.0,1449.0,3382.875
05:00,609.975,1223.6,0.0,1710.675,3544.25
06:00,605.925,1407.5,0.0,1377.575,3391.0
07:00,746.95,1589.3,0.0,420.2,2756.45
08:00,822.825,2132.8,0.0,10.275,2965.9
09:00,781.2,2270.0,0.0,0.0,3051.2
10:00,464.45,1696.6,0.0,0.0,2161.05
11:00,29.975,1240.8,0.0,58.75,1329.525
12:00,0.0,787.7,0.0,291.1,1078.8
13:00,0.0,551.9,0.0,491.3,1043.2
14:00,0.0,631.2,0.0,547.425,1178.625
15:00,1.525,872.2,0.0,578.85,1452.575
16:00,17.9,1112.6,0.0,882.25,2012.75
17:00,0.0,955.3,0.0,1844.15,2799.45
18:00,0.0,1008.2,0.0,2109.05,3117.25
19:00,0.0,878.9,0.0,2017.775,2896.675
20:00,0.0,599.1,16.525,1836.05,2451.675
21:00,33.575,634.8,0.0,1643.525,2311.9
22:00,54.925,998.1,0.0,2208.55,3261.575
23:00,59.775,999.8,0.0,2058.975,3118.55


=== query_outages ===
# Generation Outages (REMIT UMMs) for CZ on 2026-04-28

## System State Summary
* Total Unavailable Capacity: 3418 MW
  - Planned Maintenance (Priced into DA): 3218 MW
  - Unplanned Outages (Intraday Shocks): 200 MW

## Offline Capacity by Plant Type
* Fossil Brown coal/Lignite: 2377 MW
* Nuclear: 530 MW
* Hydro Pumped Storage: 325 MW
* Fossil Gas: 186 MW

## Detailed REMIT Messages (Sorted by Newest Publication First)
  published_time                plant_type  plant_name         outage_type  nominal_capacity  available_capacity            start              end  unavailable_MW
2026-05-04 17:48 Fossil Brown coal/Lignite EECK_______ Planned maintenance             139.0               102.0 2026-04-10 11:00 2026-05-07 00:00            37.0
2026-04-30 14:34 Fossil Brown coal/Lignite EPC1_______ Planned maintenance             205.0                 0.0 2026-04-27 00:00 2026-04-30 14:30           205.0
2026-04-30 14:34 Fossil Brown coal/Lignite EPC1_______ Planned maintenance             205.0                 0.0 2026-04-27 00:00 2026-04-30 14:30           205.0
2026-04-29 10:13 Fossil Brown coal/Lignite EECK_______ Planned maintenance             135.0               100.0 2026-04-14 00:00 2026-04-29 10:15            35.0
2026-04-29 10:05 Fossil Brown coal/Lignite ELED_______ Planned maintenance             660.0               423.0 2026-04-28 06:00 2026-04-29 18:00           237.0
2026-04-28 17:02 Fossil Brown coal/Lignite EPC1_______    Unplanned outage             200.0                 0.0 2026-04-28 17:00 2026-04-28 20:00           200.0
2026-04-28 08:58      Hydro Pumped Storage EDST_______ Planned maintenance             325.0                 0.0 2026-04-28 08:15 2026-04-28 10:00           325.0
2026-04-27 07:36 Fossil Brown coal/Lignite ELED_______ Planned maintenance             660.0               432.2 2026-04-28 00:00 2026-05-02 00:00           227.8
2026-04-21 08:16 Fossil Brown coal/Lignite ECHV_______ Planned maintenance             205.0                 0.0 2026-04-24 23:45 2026-05-23 00:00           205.0
2026-04-17 20:06 Fossil Brown coal/Lignite ECHV_______ Planned maintenance             205.0                 0.0 2026-04-18 00:00 2026-06-29 00:00           205.0
2026-04-16 13:26                Fossil Gas EPVR_______ Planned maintenance             186.0                 0.0 2026-04-28 00:00 2026-04-29 00:00           186.0
2026-04-02 00:48 Fossil Brown coal/Lignite ECHV_______ Planned maintenance             205.0                 0.0 2026-04-02 00:15 2026-05-09 00:00           205.0
2026-03-31 08:18 Fossil Brown coal/Lignite ETI2_______ Planned maintenance             105.0               100.0 2026-04-28 00:00 2026-04-29 00:00             5.0
2026-02-06 08:57                   Nuclear EDUK_______ Planned maintenance             530.0                 0.0 2026-04-17 20:00 2026-07-01 20:00           530.0
2025-10-08 08:32 Fossil Brown coal/Lignite ETU2_______ Planned maintenance             200.0                 0.0 2026-04-04 00:00 2026-05-14 00:00           200.0
2025-10-08 07:25 Fossil Brown coal/Lignite ECHV_______ Planned maintenance             205.0                 0.0 2026-04-18 00:00 2026-06-29 00:00           205.0
2025-10-08 07:25 Fossil Brown coal/Lignite ECHV_______ Planned maintenance             205.0                 0.0 2026-04-06 00:00 2026-06-20 00:00           205.0

=== query_imbalance_prices ===
# Imbalance Prices and Volumes for CZ on 2026-04-28
# Source: ENTSO-E
# Unit: EUR/MWh (Prices), MW (Volumes)
# Note: Financial values converted from CZK to EUR at official rate of 24.37 CZK/EUR

Hour,Imbalance Volume MW,Imbalance Volume MW StdDev,Imbalance Volume MW Range,Imbalance Price EUR/MWh,Imbalance Price EUR/MWh StdDev,Imbalance Price EUR/MWh Range
00:00,-3.12,9.129,17.35,55.454,64.038,111.948
01:00,-8.123,9.317,20.93,110.203,0.673,1.616
02:00,-14.982,6.217,13.59,106.454,0.577,1.215
03:00,-9.848,0.959,2.31,106.89,0.556,1.162
04:00,-7.665,2.614,5.42,110.66,0.435,1.032
05:00,-13.945,6.666,15.86,114.19,1.803,4.035
06:00,-0.84,3.738,8.52,89.387,59.593,119.546
07:00,3.192,3.944,8.38,30.004,60.009,120.018
08:00,1.898,10.969,23.13,65.656,51.717,112.634
09:00,27.428,2.439,5.7,-1.905,3.81,7.62
10:00,66.355,7.046,15.74,-15.926,4.49,9.518
11:00,36.802,12.247,24.04,-19.476,9.09,19.289
12:00,34.238,10.42,22.89,-22.497,1.425,3.325
13:00,15.278,12.97,31.02,-6.318,33.528,67.335
14:00,33.59,14.591,31.98,-17.373,2.852,6.045
15:00,19.865,6.378,15.34,-23.716,21.921,48.923
16:00,35.395,9.674,23.45,-15.982,12.979,27.64
17:00,28.355,22.733,53.82,-1.168,2.335,4.67
18:00,-21.178,18.905,45.48,102.859,71.787,164.255
19:00,-18.935,6.07,13.25,124.748,1.657,3.998
20:00,-4.373,3.065,6.78,142.068,3.668,8.081
21:00,1.128,2.51,6.07,32.198,64.396,128.792
22:00,-4.698,3.013,6.38,124.9,12.471,25.587
23:00,-12.878,9.568,21.01,78.734,52.525,107.619


=== query_residual_load ===
# Residual Load Actual for CZ on 2026-04-28
# Source: ENTSO-E
# Unit: MW

Hour,Actual Load MW,Solar MW
00:00,6041.692,0.0
01:00,6000.142,0.0
02:00,5869.858,0.0
03:00,5863.173,0.0
04:00,6060.003,0.0
05:00,6614.232,18.0
06:00,7621.21,176.75
07:00,8108.565,649.75
08:00,8409.92,1386.0
09:00,8675.038,2100.0
10:00,8634.968,2600.5
11:00,8510.48,2871.5
12:00,8517.128,2942.0
13:00,8467.405,2873.5
14:00,8074.382,2629.25
15:00,7957.855,2249.25
16:00,7673.938,1745.25
17:00,7461.455,1102.5
18:00,7263.845,499.25
19:00,7430.09,140.5
20:00,7463.558,14.75
21:00,7050.997,0.0
22:00,6722.61,0.0
23:00,6392.468,0.0
"""
