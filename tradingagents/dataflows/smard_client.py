"""SMARD (Strommarktdaten) client for German electricity data.

SMARD is the German Federal Network Agency's data platform.
It provides detailed generation by type, total load, and residual load.

Base URL: https://www.smard.de/app/chart_data
No authentication required.
No official API docs — reverse-engineered from the website.

The API pattern is:
GET {base_url}/{filter_id}/{resolution}/{timestamp_ms}.json

Where:
filter_id: identifies the data series (see FILTER_IDS below)
resolution: "hour" or "quarterhour"
timestamp_ms: start of the week (Monday 00:00 CET) as Unix timestamp in milliseconds
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional, Dict, List
import pandas as pd
try:
    from .energy_utils import CET, format_price_table, get_cache_path
    from .config import get_config
    from . import cache_layer
except ImportError:
    from energy_utils import CET, format_price_table, get_cache_path
    from config import get_config
    import cache_layer

logger = logging.getLogger(__name__)

SMARD_BASE_URL = "https://www.smard.de/app/chart_data"

# SMARD filter IDs for electricity generation by type
FILTER_IDS = {
    # Generation by source
    "generation_biomass": 4066,
    "generation_hydro": 1226,
    "generation_wind_offshore": 1225,
    "generation_wind_onshore": 4067,
    "generation_solar": 4068,
    "generation_nuclear": 1224,  # Germany finalized its nuclear phase-out in April 2023
    "generation_lignite": 1223,
    "generation_hard_coal": 4069,
    "generation_gas": 4071,
    "generation_pumped_storage": 4070,
    "generation_other": 1227,

    # Consumption / load
    "total_load": 410,
    "residual_load": 4359,
    "forecast_load": 411,        # CORRECTED: 411 is Prognostizierter Stromverbrauch
    "actual_load": 715,

    # Prices (Day-Ahead)
    "price_de_lu": 4169,
    "price_at": 4170,
    "price_fr": 254,
    "price_nl": 256,
    "price_pl": 257,
    "price_cz": 261,
    "price_dk1": 252,
    "price_dk2": 253,
    "price_ch": 259,

    # Forecasts
    "forecast_generation_total": 122,
    "forecast_wind_onshore": 123,
    "forecast_wind_offshore": 124,
    "forecast_solar": 125,
    "forecast_generation_wind_solar": 5097,  # CORRECTED: 5097 is Prognostizierte Erzeugung Wind und Photovoltaik
}

_session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def _get_week_start_timestamp(date_str: str) -> int:
    """Get the Unix timestamp (ms) for the Monday 00:00 CET of the week containing the date."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")

    monday = dt - timedelta(days=dt.weekday())
    monday_cet = CET.localize(datetime(monday.year, monday.month, monday.day, 0, 0, 0))

    return int(monday_cet.timestamp() * 1000)


def _fetch_smard_series(filter_id: int, resolution: str, date_str: str, region: str = "DE") -> pd.DataFrame:
    """Fetch a single SMARD data series."""
    ts_ms = _get_week_start_timestamp(date_str)
    url = f"{SMARD_BASE_URL}/{filter_id}/{region}/{filter_id}_{region}_{resolution}_{ts_ms}.json"

    try:
        response = _get_session().get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "series" not in data or not data["series"]:
            logger.warning(f"No data series found in SMARD response for filter {filter_id} on {date_str}")
            return pd.DataFrame()

        series_data = data["series"]
        if not series_data or len(series_data) < 2:
            logger.warning(f"Unexpected data format in SMARD response for filter {filter_id} on {date_str}")
            return pd.DataFrame()

        records = []
        from datetime import timezone
        for point in series_data:
            if point is None:
                logger.warning(f"Encountered null data point in SMARD series {filter_id} for date {date_str}")
                continue
            if isinstance(point, list) and len(point) >= 2:
                ts = datetime.fromtimestamp(point[0] / 1000, tz=timezone.utc).astimezone(CET)
                value = point[1]
                records.append({"timestamp": ts, "value": value})

        if not records:
            logger.warning(f"No valid data points found in SMARD series {filter_id} for date {date_str}")
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df.set_index("timestamp", inplace=True)
        df.index.name = "CET"

        return df
    except Exception as e:
        logger.warning(f"Failed to fetch SMARD filter {filter_id}: {e}")
        return pd.DataFrame()


def _load_or_fetch(source: str, query_type: str, market_area: str, date_str: str, fetch_fn):
    """Cache wrapper for SMARD data."""
    try:
        cached_df = cache_layer.load_cached(source, query_type, market_area, date_str)
        if cached_df is not None:
            logger.debug(f"Cache hit: {source}/{query_type}/{market_area}/{date_str}")
            return cached_df
    except Exception as e:
        logger.warning(f"Cache read error: {e}")

    try:
        df = fetch_fn()
        if df is not None and not df.empty:
            try:
                cache_layer.save_to_cache(df, source, query_type, market_area, date_str)
            except Exception as e:
                logger.warning(f"Cache write error: {e}")
        return df
    except Exception as e:
        logger.error(f"Fetch error for {source}/{query_type}/{market_area}/{date_str}: {e}")
        return pd.DataFrame()


def _format_index(df: pd.DataFrame) -> pd.DataFrame:
    """Format DatetimeIndex to save LLM tokens and standardize output."""
    if df is not None and not df.empty and isinstance(df.index, pd.DatetimeIndex):
        df = df.round(3)  # Round to 3 decimals for cleaner display
        df.index = df.index.strftime('%H:%M')
        df.index.name = "Hour"
    return df


def get_german_generation(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU'"] = "DE-LU",
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch German generation breakdown by type from SMARD."""
    if market_area.upper() != "DE-LU":
        logger.warning(f"SMARD generation client only supports DE-LU market area. Requested: {market_area} - Changed to DE-LU. Use it for cross-checking only, and be aware that the data WILL NOT be accurate for other market areas.")
        market_area = "DE-LU"

    def fetch():
        generation_types = [
            ("Wind Onshore", "generation_wind_onshore"),
            ("Wind Offshore", "generation_wind_offshore"),
            ("Solar", "generation_solar"),
            ("Nuclear", "generation_nuclear"),
            ("Lignite", "generation_lignite"),
            ("Hard Coal", "generation_hard_coal"),
            ("Gas", "generation_gas"),
            ("Pumped Storage", "generation_pumped_storage"),
            ("Hydro", "generation_hydro"),
            ("Biomass", "generation_biomass"),
            ("Other", "generation_other"),
        ]

        dfs = []
        for col_name, filter_name in generation_types:
            filter_id = FILTER_IDS.get(filter_name)
            if filter_id is None:
                continue

            df = _fetch_smard_series(filter_id, resolution, delivery_date)
            if not df.empty:
                df = df.rename(columns={"value": col_name})
                dfs.append(df)

        if not dfs:
            return pd.DataFrame()

        result = dfs[0]
        for df in dfs[1:]:
            result = result.join(df, how="outer")

        result = result.sort_index()

        date_dt = datetime.strptime(delivery_date, "%Y-%m-%d")
        start = CET.localize(date_dt)
        end = CET.localize(date_dt + timedelta(days=1))
        result = result[(result.index >= start) & (result.index < end)]

        result = result.fillna(0)
        result.insert(0, "Total", result.sum(axis=1))

        return result

    df = _load_or_fetch("smard", f"generation_{resolution}", market_area.upper(), delivery_date, fetch)

    if df is None or df.empty:
        return f"# No {market_area.upper()} generation data for {delivery_date}"

    df = _format_index(df.copy())
    header = f"# {market_area.upper()} Generation by Type on {delivery_date} ({resolution})\n"
    header += "# Source: SMARD (Bundesnetzagentur)\n"
    header += "# Unit: MW\n\n"

    return header + df.to_csv()


def get_german_residual_load(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU'"] = "DE-LU",
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch German residual load (total load minus wind and solar) from SMARD."""
    if market_area.upper() != "DE-LU":
        logger.warning(f"SMARD residual load client only supports DE-LU market area. Requested: {market_area} - Changed to DE-LU. Use it for cross-checking only, and be aware that the data WILL NOT be accurate for other market areas.")
        market_area = "DE-LU"

    def fetch():
        filter_id = FILTER_IDS.get("residual_load")
        if filter_id is None:
            return pd.DataFrame()

        df = _fetch_smard_series(filter_id, resolution, delivery_date)
        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={"value": "Residual Load MW"})
        df = df[["Residual Load MW"]]

        date_dt = datetime.strptime(delivery_date, "%Y-%m-%d")
        start = CET.localize(date_dt)
        end = CET.localize(date_dt + timedelta(days=1))
        df = df[(df.index >= start) & (df.index < end)]

        return df

    df = _load_or_fetch("smard", f"residual_load_{resolution}", market_area.upper(), delivery_date, fetch)

    if df is None or df.empty:
        return f"# No {market_area.upper()} residual load data for {delivery_date}"

    df = _format_index(df.copy())
    header = f"# {market_area.upper()} Residual Load on {delivery_date} ({resolution})\n"
    header += "# Source: SMARD (Bundesnetzagentur)\n"
    header += "# Unit: MW (Load - Wind - Solar)\n\n"

    return header + df.to_csv()


def get_german_total_load(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU'"] = "DE-LU",
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch German total load from SMARD."""
    if market_area.upper() != "DE-LU":
        logger.warning(f"SMARD total load client only supports DE-LU market area. Requested: {market_area} - Changed to DE-LU. Use it for cross-checking only, and be aware that the data WILL NOT be accurate for other market areas.")
        market_area = "DE-LU"

    def fetch():
        filter_id = FILTER_IDS.get("total_load")
        if filter_id is None:
            return pd.DataFrame()

        df = _fetch_smard_series(filter_id, resolution, delivery_date)
        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={"value": "Total Load MW"})
        df = df[["Total Load MW"]]

        date_dt = datetime.strptime(delivery_date, "%Y-%m-%d")
        start = CET.localize(date_dt)
        end = CET.localize(date_dt + timedelta(days=1))
        df = df[(df.index >= start) & (df.index < end)]

        return df

    df = _load_or_fetch("smard", f"total_load_{resolution}", market_area.upper(), delivery_date, fetch)

    if df is None or df.empty:
        return f"# No {market_area.upper()} total load data for {delivery_date}"

    df = _format_index(df.copy())
    header = f"# {market_area.upper()} Total Load on {delivery_date} ({resolution})\n"
    header += "# Source: SMARD (Bundesnetzagentur)\n"
    header += "# Unit: MW\n\n"

    return header + df.to_csv()


def get_smard_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone (e.g., 'DE-LU', 'AT', 'FR', 'CZ')"] = "CZ",
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch Day-Ahead Market prices for a specific region from SMARD."""
    def fetch():
        area_map = {
            "DE-LU": "price_de_lu", "AT": "price_at", "FR": "price_fr",
            "NL": "price_nl", "PL": "price_pl", "CZ": "price_cz",
            "DK1": "price_dk1", "DK2": "price_dk2", "CH": "price_ch"
        }
        filter_name = area_map.get(market_area.upper())
        if not filter_name:
            return pd.DataFrame()

        filter_id = FILTER_IDS.get(filter_name)

        df = _fetch_smard_series(filter_id, resolution, delivery_date, region="DE")

        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={"value": "Price EUR/MWh"})

        date_dt = datetime.strptime(delivery_date, "%Y-%m-%d")
        start = CET.localize(date_dt)
        end = CET.localize(date_dt + timedelta(days=1))
        df = df[(df.index >= start) & (df.index < end)]

        return df

    df = _load_or_fetch("smard", f"prices_{market_area.upper()}_{resolution}",
                        market_area.upper(), delivery_date, fetch)

    if df is None or df.empty:
        return f"# No SMARD price data for {market_area.upper()} on {delivery_date}"

    df = _format_index(df.copy())
    header = f"# Day-Ahead Prices for {market_area.upper()} on {delivery_date} ({resolution})\n"
    header += "# Source: SMARD (Bundesnetzagentur)\n"
    header += "# Unit: EUR/MWh\n\n"

    return header + df.to_csv()


def get_german_generation_forecast(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU'"] = "DE-LU",
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch German forecasted generation (Total, Wind, Solar) from SMARD."""
    if market_area.upper() != "DE-LU":
        logger.warning(f"SMARD generation forecast client only supports DE-LU market area. Requested: {market_area} - Changed to DE-LU. Use it for cross-checking only, and be aware that the data WILL NOT be accurate for other market areas.")
        market_area = "DE-LU"

    def fetch():
        forecast_types = [
            ("Forecast Total", "forecast_generation_total"),
            ("Forecast Wind Onshore", "forecast_wind_onshore"),
            ("Forecast Wind Offshore", "forecast_wind_offshore"),
            ("Forecast Solar", "forecast_solar"),
            ("Forecast Combined Wind & Solar", "forecast_generation_wind_solar"),
        ]

        dfs = []
        for col_name, filter_name in forecast_types:
            filter_id = FILTER_IDS.get(filter_name)
            df = _fetch_smard_series(filter_id, resolution, delivery_date)
            if not df.empty:
                df = df.rename(columns={"value": col_name})
                dfs.append(df)

        if not dfs:
            return pd.DataFrame()

        result = dfs[0]
        for df in dfs[1:]:
            result = result.join(df, how="outer")

        result = result.sort_index()

        date_dt = datetime.strptime(delivery_date, "%Y-%m-%d")
        start = CET.localize(date_dt)
        end = CET.localize(date_dt + timedelta(days=1))
        result = result[(result.index >= start) & (result.index < end)]

        # Drop columns that failed to fetch instead of filling with misleading zeros
        result = result.dropna(axis=1, how='all').fillna(0)

        return result

    df = _load_or_fetch("smard", f"generation_forecast_{resolution}", market_area.upper(), delivery_date, fetch)

    if df is None or df.empty:
        return f"# No {market_area.upper()} generation forecast data for {delivery_date}"

    df = _format_index(df.copy())
    header = f"# {market_area.upper()} Generation Forecast on {delivery_date} ({resolution})\n"
    header += "# Source: SMARD (Bundesnetzagentur)\n"
    header += "# Unit: MW\n\n"

    return header + df.to_csv()


def get_german_load_forecast(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU'"] = "DE-LU",
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch German load forecast from SMARD."""
    if market_area.upper() != "DE-LU":
        logger.warning(f"SMARD load forecast client only supports DE-LU market area. Requested: {market_area} - Changed to DE-LU. Use it for cross-checking only, and be aware that the data WILL NOT be accurate for other market areas.")
        market_area = "DE-LU"

    def fetch():
        filter_id = FILTER_IDS.get("forecast_load")
        if filter_id is None:
            return pd.DataFrame()

        df = _fetch_smard_series(filter_id, resolution, delivery_date)
        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={"value": "Load Forecast MW"})
        df = df[["Load Forecast MW"]]

        date_dt = datetime.strptime(delivery_date, "%Y-%m-%d")
        start = CET.localize(date_dt)
        end = CET.localize(date_dt + timedelta(days=1))
        df = df[(df.index >= start) & (df.index < end)]

        return df

    df = _load_or_fetch("smard", f"forecast_load_{resolution}", market_area.upper(), delivery_date, fetch)

    if df is None or df.empty:
        return f"# No {market_area.upper()} load forecast data for {delivery_date}"

    df = _format_index(df.copy())
    header = f"# {market_area.upper()} Load Forecast on {delivery_date} ({resolution})\n"
    header += "# Source: SMARD (Bundesnetzagentur)\n"
    header += "# Unit: MW\n\n"

    return header + df.to_csv()


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-28"
    market_area = sys.argv[2] if len(sys.argv) > 2 else "CZ"

    try:
        deleted_count = cache_layer.clear_cache(source="smard")
        print(f"Deleted {deleted_count} parquet files from the cache.")
    except Exception as e:
        logger.warning(f"Error clearing cache: {e}")
        pass

    print("\n=== get_german_generation ===")
    print(get_german_generation(date, market_area=market_area, resolution="hour"))

    print("\n=== get_german_residual_load ===")
    print(get_german_residual_load(date, market_area=market_area, resolution="hour"))

    print("\n=== get_german_total_load ===")
    print(get_german_total_load(date, market_area=market_area, resolution="hour"))

    print("\n=== get_smard_prices ===")
    print(get_smard_prices(date, market_area="DE-LU", resolution="hour"))
    print(get_smard_prices(date, market_area="CZ", resolution="hour"))

    print("\n=== get_german_generation_forecast ===")
    print(get_german_generation_forecast(date, market_area=market_area, resolution="hour"))

    print("\n=== get_german_load_forecast ===")
    print(get_german_load_forecast(date, market_area=market_area, resolution="hour"))

    try:
        deleted_count = cache_layer.clear_cache(source="smard")
        print(f"Deleted {deleted_count} parquet files from the cache.")
    except Exception as e:
        logger.warning(f"Error clearing cache: {e}")
        pass


"""
Reference output
=== get_german_generation ===
Failed to fetch SMARD filter 1224: 404 Client Error: Not Found for url: https://www.smard.de/app/chart_data/1224/DE/1224_DE_hour_1777240800000.json
# DE-LU Generation by Type on 2026-04-28 (hour)
# Source: SMARD (Bundesnetzagentur)
# Unit: MW

Hour,Total,Wind Onshore,Wind Offshore,Solar,Lignite,Hard Coal,Gas,Pumped Storage,Hydro,Biomass,Other
00:00,43650.37,15770.97,2344.41,0.0,7635.19,4003.27,5963.71,517.53,1356.7,4186.96,1871.63
01:00,43537.74,16012.09,2126.1,0.0,7640.42,3968.5,5804.67,641.11,1337.11,4146.37,1861.37
02:00,42759.51,15577.76,1917.42,0.0,7764.59,3871.05,5777.56,572.26,1326.09,4128.83,1823.95
03:00,42612.42,15323.79,1678.29,0.0,7935.84,3871.57,5883.08,664.6,1309.66,4120.14,1825.45
04:00,43172.35,15597.73,1706.6,0.0,8083.3,3870.3,6162.75,461.03,1299.04,4145.66,1845.94
05:00,45452.55,16207.26,2293.24,16.07,8222.99,3861.93,6305.59,1142.01,1303.84,4237.15,1862.47
06:00,49074.98,16551.72,2859.35,1680.36,8040.83,3894.56,6367.37,2048.64,1352.81,4414.77,1864.57
07:00,52845.35,13845.56,2594.85,8345.49,7554.47,3884.55,5889.42,2967.22,1379.46,4499.45,1884.88
08:00,55431.05,9049.73,2086.46,19783.22,6783.66,3245.9,4656.55,2060.2,1352.03,4483.53,1929.77
09:00,59425.2,6663.03,1934.99,33204.97,4409.91,2038.4,3014.08,451.26,1378.19,4407.9,1922.47
10:00,65926.22,6401.55,1906.49,43190.32,3386.94,1394.46,2143.15,70.63,1346.23,4288.72,1797.73
11:00,70896.26,7577.58,1126.6,48275.64,3215.2,1197.4,2025.69,145.9,1363.68,4170.1,1798.47
12:00,71435.96,8390.82,663.72,48890.47,3206.46,1157.34,2008.95,69.41,1182.6,4058.62,1807.57
13:00,71272.94,8836.52,429.27,48709.0,3192.67,1079.71,2004.19,32.35,1173.32,4030.73,1785.18
14:00,69327.94,8924.18,520.52,46482.75,3306.6,1068.81,2005.04,54.54,1150.51,4041.69,1773.3
15:00,68209.74,11607.01,775.22,42237.23,3404.79,1116.27,2042.27,37.62,1140.32,4076.71,1772.3
16:00,64516.19,14819.56,1010.76,34612.5,3455.91,1173.43,2141.94,90.6,1318.27,4117.6,1775.62
17:00,61771.25,19071.93,2485.44,24973.09,3569.73,1535.38,2665.94,66.23,1315.15,4274.28,1814.08
18:00,57867.54,21541.21,3320.67,12741.32,5657.98,2587.89,3805.5,491.51,1354.39,4480.78,1886.29
19:00,55152.13,21240.43,3729.69,4007.52,6675.7,3294.97,4913.76,3467.98,1342.72,4582.34,1897.02
20:00,53280.06,21235.8,3730.0,342.14,6350.25,3363.72,5138.99,5231.78,1368.47,4608.94,1909.97
21:00,54335.35,23660.34,3820.41,1.79,6777.43,3617.8,5281.08,3349.22,1370.13,4551.88,1905.27
22:00,53018.61,23835.27,3593.57,0.43,6800.55,3761.99,5139.5,2213.77,1333.32,4434.07,1906.14
23:00,50092.68,23698.75,3036.29,0.23,6796.61,3795.96,4758.17,489.04,1301.56,4321.56,1894.51


=== get_german_residual_load ===
# DE-LU Residual Load on 2026-04-28 (hour)
# Source: SMARD (Bundesnetzagentur)
# Unit: MW (Load - Wind - Solar)

Hour,Residual Load MW
00:00,26523.46
01:00,24721.39
02:00,24986.16
03:00,25553.62
04:00,26718.0
05:00,29422.69
06:00,33633.23
07:00,33653.46
08:00,29443.52
09:00,17926.88
10:00,8414.22
11:00,1261.08
12:00,-1127.38
13:00,-2764.79
14:00,-2227.21
15:00,-1807.35
16:00,1863.9
17:00,7013.27
18:00,18097.43
19:00,28475.15
20:00,30380.28
21:00,27591.28
22:00,24240.93
23:00,21787.64


=== get_german_total_load ===
# DE-LU Total Load on 2026-04-28 (hour)
# Source: SMARD (Bundesnetzagentur)
# Unit: MW

Hour,Total Load MW
00:00,44638.85
01:00,42859.58
02:00,42481.34
03:00,42555.71
04:00,44022.33
05:00,47939.26
06:00,54724.66
07:00,58439.36
08:00,60362.93
09:00,59729.87
10:00,59912.58
11:00,58240.9
12:00,56817.62
13:00,55210.0
14:00,53700.24
15:00,52812.11
16:00,52306.72
17:00,53543.73
18:00,55700.63
19:00,57452.8
20:00,55688.22
21:00,55073.82
22:00,51670.2
23:00,48522.91


=== get_smard_prices ===
# Day-Ahead Prices for DE-LU on 2026-04-28 (hour)
# Source: SMARD (Bundesnetzagentur)
# Unit: EUR/MWh

Hour,Price EUR/MWh
00:00,112.66
01:00,106.9
02:00,102.98
03:00,102.83
04:00,105.28
05:00,111.84
06:00,122.1
07:00,121.43
08:00,112.32
09:00,79.78
10:00,21.82
11:00,-1.09
12:00,-14.04
13:00,-29.0
14:00,-29.01
15:00,-17.33
16:00,-4.66
17:00,33.32
18:00,90.1
19:00,117.4
20:00,120.97
21:00,115.83
22:00,111.3
23:00,101.77

# Day-Ahead Prices for CZ on 2026-04-28 (hour)
# Source: SMARD (Bundesnetzagentur)
# Unit: EUR/MWh

Hour,Price EUR/MWh
00:00,116.03
01:00,111.45
02:00,107.98
03:00,108.07
04:00,110.61
05:00,117.18
06:00,127.9
07:00,126.19
08:00,114.61
09:00,77.9
10:00,29.58
11:00,-0.04
12:00,-3.8
13:00,-14.2
14:00,-11.24
15:00,8.36
16:00,42.17
17:00,60.69
18:00,96.2
19:00,123.48
20:00,140.27
21:00,121.49
22:00,115.8
23:00,106.41


=== get_german_generation_forecast ===
# DE-LU Generation Forecast on 2026-04-28 (hour)
# Source: SMARD (Bundesnetzagentur)
# Unit: MW

Hour,Forecast Total,Forecast Wind Onshore,Forecast Wind Offshore,Forecast Solar,Forecast Combined Wind & Solar
00:00,41354.96,13995.89,1667.17,0.0,15663.07
01:00,40074.06,14328.72,1743.35,0.0,16072.07
02:00,39332.94,14484.91,1704.37,0.0,16189.28
03:00,39473.01,14504.25,1625.5,0.0,16129.75
04:00,39866.06,14597.78,1630.35,0.0,16228.14
05:00,41434.48,14823.32,1782.01,31.04,16636.37
06:00,45610.18,15177.46,1970.95,1552.47,18700.88
07:00,51736.26,14315.76,2063.44,7510.28,23889.48
08:00,55684.21,10899.03,1983.53,17728.81,30611.37
09:00,59431.01,8388.34,1973.77,29235.99,39598.1
10:00,66842.2,8375.32,1897.61,38994.84,49267.77
11:00,73233.79,8813.78,716.84,45088.87,54619.49
12:00,74672.58,9551.2,647.22,47927.78,58126.2
13:00,74324.05,10334.25,598.29,48476.94,59409.48
14:00,71400.29,11264.08,603.59,46383.79,58251.46
15:00,68814.74,12570.78,655.09,41738.7,54964.57
16:00,65048.94,14538.18,838.22,34743.51,50119.91
17:00,61786.49,16883.61,2205.85,24829.72,43919.17
18:00,57309.71,18221.82,2854.2,13031.17,34107.19
19:00,52636.6,18894.72,3532.24,4085.04,26512.01
20:00,51504.47,20185.61,3804.43,409.72,24399.75
21:00,51694.12,21915.63,3706.9,0.0,25622.53
22:00,50222.63,22033.6,3377.99,0.0,25411.59
23:00,47984.28,21416.9,2949.27,0.0,24366.17


=== get_german_load_forecast ===
# DE-LU Load Forecast on 2026-04-28 (hour)
# Source: SMARD (Bundesnetzagentur)
# Unit: MW

Hour,Load Forecast MW
00:00,46733.09
01:00,45201.84
02:00,44720.54
03:00,44963.49
04:00,45946.88
05:00,49067.28
06:00,54223.5
07:00,58587.63
08:00,61394.69
09:00,62743.04
10:00,62997.79
11:00,62753.25
12:00,61964.48
13:00,60249.77
14:00,58658.69
15:00,57435.41
16:00,57311.66
17:00,57862.04
18:00,58997.89
19:00,59513.95
20:00,58236.21
21:00,55762.69
22:00,52609.37
23:00,49367.71
"""
