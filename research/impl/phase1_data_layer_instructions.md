# Phase 1: Data Layer — Implementation Instructions

## Overview

You are implementing the data layer for an energy market trading agent system. This system currently fetches US stock data (via `yfinance` and `alpha_vantage`). Your job is to **replace** the stock data backend with European electricity market data from four free APIs, while preserving the same vendor-routing architecture.

**Do NOT delete the existing stock modules** — leave `y_finance.py`, `alpha_vantage.py`, etc. in place. You are adding new files alongside them and updating `interface.py` and `default_config.py` to route to them.

---

## Architecture Context

### How the existing system works

The system has a vendor-routing layer in `tradingagents/dataflows/interface.py`. It works like this:

1. `TOOLS_CATEGORIES` — a dict mapping category names to lists of tool method names
2. `VENDOR_METHODS` — a dict mapping each tool method name to a dict of `{vendor_name: function_reference}`
3. `route_to_vendor(method, *args, **kwargs)` — looks up the configured vendor for a method (from `default_config.py`), calls the implementation, and falls back to other vendors on error
4. `get_vendor(category, method)` — reads `default_config.py` to decide which vendor to use for a given category/method
5. `get_config()` from `tradingagents/dataflows/config.py` — returns the current config dict

The config is a flat dict in `tradingagents/default_config.py` (variable `DEFAULT_CONFIG`). Key current entries:

```python
"data_vendors": {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
},
```

### How data functions return values

**Critical**: All data functions return **plain strings**. The downstream LLM agents consume these strings as tool outputs. They do NOT receive DataFrames or dicts. Format your return values as readable text with clear headers, like the existing functions do. Example from `y_finance.py`:

```python
header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
header += f"# Total records: {len(data)}\n\n"
return header + csv_string
```

Follow this pattern: a header comment block describing what the data is, then a human/LLM-readable text representation of the data (CSV, formatted tables, or structured text).

### Function signatures

All existing functions use `typing.Annotated` for their parameters with string descriptions. Continue this pattern. Example:

```python
def get_day_ahead_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
```

---

## Files to Create

You need to create **7 new files** in `tradingagents/dataflows/`:

### File 1: `energy_utils.py` — Shared Utilities

**Purpose**: Timezone handling, delivery period parsing, data alignment, common constants.

**What to implement**:

```python
"""Shared utilities for energy market data modules."""

import pytz
from datetime import datetime, timedelta
from typing import Optional, Tuple
import pandas as pd

# Constants
CET = pytz.timezone("Europe/Berlin")  # CET/CEST automatic
UTC = pytz.UTC

# Bidding zone codes used by ENTSO-E
BIDDING_ZONES = {
    "DE-LU": "10Y1001A1001A82H",  # Germany-Luxembourg
    "CZ": "10YCZ-CEPS-----N",     # Czech Republic
    "AT": "10YAT-APG------L",     # Austria
    "PL": "10YPL-AREA-----S",     # Poland
    "SK": "10YSK-SEPS-----K",     # Slovakia
    "FR": "10YFR-RTE------C",     # France
    "NL": "10YNL----------L",     # Netherlands
    "DK1": "10YDK-1--------W",    # Denmark West
    "DK2": "10YDK-2--------M",    # Denmark East
    "CH": "10YCH-SWISSGRIDZ",    # Switzerland
}

def get_entsoe_area_code(market_area: str) -> str:
    """Convert a human-readable market area code to the ENTSO-E EIC code.
    
    Args:
        market_area: e.g. "DE-LU", "CZ"
    
    Returns:
        The ENTSO-E EIC area code string
        
    Raises:
        ValueError if market_area is not recognized
    """
    # TODO: Implement lookup from BIDDING_ZONES, raise ValueError if not found
    pass

def parse_delivery_period(delivery_period: str) -> Tuple[datetime, datetime]:
    """Parse a delivery period string into (start, end) datetimes in CET.
    
    Delivery periods come as ISO datetime strings, e.g.:
    - "2024-06-15T14:00" for hourly: represents 14:00-15:00 CET
    - "2024-06-15T14:00/PT15M" for quarter-hourly: represents 14:00-14:15 CET
    - "2024-06-15T14:00/PT60M" for hourly (explicit): 14:00-15:00 CET
    
    If no duration suffix, assume 60min.
    
    Args:
        delivery_period: ISO datetime string, optionally with /PTxxM suffix
        
    Returns:
        Tuple of (start_cet, end_cet) as timezone-aware datetimes
    """
    # TODO: Parse the string, handle duration suffix, localize to CET
    pass

def delivery_date_to_entsoe_period(date_str: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Convert a date string to the (start, end) pd.Timestamp range needed by entsoe-py.
    
    entsoe-py expects timezone-aware pd.Timestamps for start/end.
    For a full day: start = date 00:00 CET, end = date+1 00:00 CET.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        
    Returns:
        Tuple of (start, end) pd.Timestamps with CET timezone
    """
    # TODO: Implement
    pass

def handle_dst_transition(df: pd.DataFrame, method: str = "ffill") -> pd.DataFrame:
    """Handle daylight saving time transitions in a DataFrame with CET-indexed data.
    
    In spring (CET->CEST): hour 2 is missing. Back-fill or forward-fill.
    In autumn (CEST->CET): hour 2 appears twice. Average the duplicate.
    
    This is standard practice in electricity price forecasting literature
    (see Hir23, Section 3: "we adjust the daylight saving times by (back-)filling
    the missing hour in spring and averaging the double hour in autumn").
    
    Args:
        df: DataFrame with timezone-aware CET/CEST DatetimeIndex
        method: "ffill" to forward-fill spring gaps, "bfill" for back-fill
        
    Returns:
        Cleaned DataFrame
    """
    # TODO: Implement DST handling
    pass

def format_price_table(df: pd.DataFrame, title: str, market_area: str) -> str:
    """Format a price DataFrame as a readable string for LLM consumption.
    
    Args:
        df: DataFrame with prices (and possibly volumes)
        title: Description header, e.g. "Day-Ahead Prices"
        market_area: e.g. "DE-LU"
    
    Returns:
        Formatted string with header and CSV-like table
    """
    # TODO: Implement — add header comment block, then df.to_csv() or df.to_string()
    pass

def get_cache_path(source: str, query_type: str, market_area: str, 
                   date_str: str, cache_dir: str) -> str:
    """Build a cache file path for storing/loading cached API responses.
    
    Convention: {cache_dir}/{source}/{market_area}/{query_type}/{date_str}.parquet
    
    Args:
        source: e.g. "entsoe", "ote", "smard", "openmeteo"
        query_type: e.g. "day_ahead_prices", "wind_forecast"
        market_area: e.g. "DE-LU", "CZ"
        date_str: e.g. "2024-06-15"
        cache_dir: base cache directory from config
        
    Returns:
        Full path string
    """
    # TODO: Implement, create directories if they don't exist
    pass
```

**Notes**:
- The DST handling is critical. Europe switches clocks on last Sunday of March and October.
- The `entsoe-py` library expects `pd.Timestamp` with `tz='Europe/Berlin'` — use that, not raw datetimes.
- `pytz` is standard; also consider `zoneinfo` (Python 3.9+).

---

### File 2: `entsoe_client.py` — ENTSO-E Transparency Platform Client

**Purpose**: Wrap the `entsoe-py` library to fetch all system/fundamental data for DE and CZ.

**Dependencies**: `entsoe-py` is already installed in the conda env. Import with `from entsoe import EntsoePandasClient`.

**API key**: Read from `os.environ.get("ENTSOE_API_KEY")` or from `get_config().get("entsoe_api_key")`.

**Critical implementation detail**: `entsoe-py` returns `pandas.DataFrame` or `pandas.Series` objects. You must convert these to formatted strings before returning. All public functions must return `str`.

**What to implement**:

```python
"""ENTSO-E Transparency Platform data client.

Uses the entsoe-py library (already installed).
API docs: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
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

from entsoe import EntsoePandasClient

from .config import get_config
from .energy_utils import (
    get_entsoe_area_code,
    delivery_date_to_entsoe_period,
    handle_dst_transition,
    format_price_table,
    get_cache_path,
    CET,
)

logger = logging.getLogger(__name__)


def _get_client() -> EntsoePandasClient:
    """Create and return an ENTSO-E client with the configured API key.
    
    Reads key from ENTSOE_API_KEY env var, falling back to config.
    Raises ValueError if no key is available.
    """
    # TODO: Implement
    pass


def _load_or_fetch(source, query_type, market_area, date_str, fetch_fn):
    """Generic cache wrapper: check cache first, call fetch_fn on miss, save result.
    
    Args:
        source: "entsoe"
        query_type: e.g. "day_ahead_prices"
        market_area: e.g. "DE-LU"
        date_str: "YYYY-MM-DD"
        fetch_fn: callable that returns a pd.DataFrame
        
    Returns:
        pd.DataFrame (from cache or freshly fetched)
    """
    # TODO: Implement using get_cache_path and parquet read/write
    # On cache miss, call fetch_fn(), save to parquet, return result
    # On any cache error, fall through to fetch
    pass


# ─────────────────────────────────────────────
# PRICE DATA
# ─────────────────────────────────────────────

def query_day_ahead_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch day-ahead auction prices for a given date and bidding zone.
    
    Returns hourly marginal clearing prices in EUR/MWh.
    This is the anchor price against which intraday deviations are measured.
    
    Uses: client.query_day_ahead_prices(country_code, start, end)
    The entsoe-py method returns a pd.Series indexed by CET timestamps.
    
    Output format example:
        # Day-Ahead Prices for DE-LU on 2024-06-15
        # Source: ENTSO-E Transparency Platform
        # Unit: EUR/MWh
        
        Delivery Hour (CET),Price EUR/MWh
        2024-06-15 00:00,45.23
        2024-06-15 01:00,42.10
        ...
        2024-06-15 23:00,55.80
    """
    # TODO: 
    # 1. Convert market_area to ENTSO-E code via get_entsoe_area_code()
    # 2. Convert delivery_date to start/end pd.Timestamps via delivery_date_to_entsoe_period()
    # 3. Call _get_client().query_day_ahead_prices(country_code, start=start, end=end)
    # 4. Handle DST transitions
    # 5. Format as string with header + CSV
    # 6. Wrap in _load_or_fetch for caching
    pass


# ─────────────────────────────────────────────
# GENERATION FORECASTS (wind, solar)
# ─────────────────────────────────────────────

def query_wind_solar_forecast(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch day-ahead wind and solar generation forecasts.
    
    Returns forecasted generation in MW for wind (onshore + offshore) and solar PV.
    These are the DAY-AHEAD forecasts, typically available by 11:00 the day before.
    
    Uses: client.query_wind_and_solar_forecast(country_code, start, end)
    Returns a DataFrame with columns like 'Wind Onshore', 'Wind Offshore', 'Solar'.
    
    IMPORTANT: This function provides the BASE forecast. The INTRADAY UPDATES
    (which are the primary trading signal per Kup22) come from comparing 
    newer forecasts against this base. See query_generation_forecast_updates().
    
    Output format:
        # Wind & Solar Day-Ahead Forecast for DE-LU on 2024-06-15
        # Source: ENTSO-E (TSO forecasts)
        # Unit: MW
        
        Hour (CET),Wind Onshore MW,Wind Offshore MW,Solar MW,Total Renewable MW
        00:00,12500,3200,0,15700
        01:00,12800,3100,0,15900
        ...
    """
    # TODO:
    # 1. Get area code, create time range
    # 2. Call client.query_wind_and_solar_forecast(country_code, start, end)
    # 3. Some zones don't have offshore — handle missing columns gracefully
    # 4. Add a "Total Renewable" sum column
    # 5. Format and return string
    pass


def query_actual_generation(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch actual generation by production type for a given date.
    
    Returns actual generation in MW broken down by type (wind onshore, wind offshore,
    solar, gas, coal, lignite, nuclear, hydro, biomass, etc.)
    
    This data is needed to:
    - Compute forecast errors: actual_wind - forecast_wind (the key alpha signal per Kup22, Kie17)
    - Estimate merit order steepness (how much conventional capacity is running) per Kre21b
    - Detect regime (is the system renewable-heavy or conventional-heavy?) per Kie17
    
    Uses: client.query_generation(country_code, start, end, psr_type=None)
    Returns DataFrame with columns for each generation type.
    
    Output format:
        # Actual Generation by Type for DE-LU on 2024-06-15
        # Source: ENTSO-E
        # Unit: MW
        
        Hour (CET),Wind Onshore,Wind Offshore,Solar,Gas,Hard Coal,Lignite,Nuclear,...
        00:00,11800,3050,0,5200,3100,8500,4000,...
        ...
    """
    # TODO:
    # 1. Call client.query_generation(country_code, start, end, psr_type=None)
    # 2. Returns DataFrame with many columns — keep all, they're useful
    # 3. Format as string
    pass


def query_generation_forecast_updates(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch updated (intraday) wind and solar forecasts and compute deltas.
    
    THIS IS THE MOST IMPORTANT DATA FUNCTION FOR TRADING.
    
    Per Kup22 (the core trading strategy paper), the PRIMARY alpha signal is the 
    DIFFERENCE between the latest intraday forecast and the day-ahead forecast:
    
        forecast_delta = intraday_forecast - day_ahead_forecast
    
    A positive wind delta means MORE wind than expected → prices should DROP.
    A negative wind delta means LESS wind than expected → prices should RISE.
    The same logic applies to solar.
    
    Per Kup22, these forecast signals are defined as:
        ε_t^s = (F_intraday^s - F_dayahead^s)   for each product s at time t
    where F is the renewable production forecast.
    
    Kup22 used forecasts at offsets of 8h, 5h, 3h before delivery, and the 
    "best" (latest) intraday forecast. For our purposes, we use what ENTSO-E
    provides, which is typically the latest available generation forecast.
    
    Uses: 
    - client.query_wind_and_solar_forecast(country_code, start, end)  [day-ahead]
    - client.query_generation_forecast(country_code, start, end)       [intraday updates]
    
    Note: ENTSO-E's intraday forecast update availability varies by TSO. 
    German TSOs provide frequent updates; others may not. If the intraday 
    forecast is not available, return the day-ahead forecast with delta=0.
    
    Output format:
        # Forecast Updates for DE-LU on 2024-06-15
        # Source: ENTSO-E
        # Unit: MW (delta = intraday_forecast - day_ahead_forecast)
        
        Hour,DA Wind,ID Wind,Wind Delta,DA Solar,ID Solar,Solar Delta
        00:00,12500,11800,-700,0,0,0
        01:00,12800,12200,-600,0,0,0
        ...
    """
    # TODO:
    # 1. Fetch day-ahead forecast (query_wind_and_solar_forecast internally)
    # 2. Fetch intraday/updated forecast if available:
    #    Try: client.query_generation_forecast(country_code, start, end)
    #    This may or may not have wind/solar breakdowns depending on TSO
    # 3. Compute delta columns
    # 4. Format as string showing both forecasts and the delta
    # NOTE: If intraday forecast is unavailable, set delta=0 and note it in the header
    pass


# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────

def query_load_forecast(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch day-ahead load (demand) forecast.
    
    Load forecast is needed to compute RESIDUAL LOAD:
        residual_load = load_forecast - wind_forecast - solar_forecast
    
    Residual load is a key variable because it determines WHERE on the merit order
    curve the market clears. Per Kie17, the "demand quote" (demand / planned conventional)
    determines the market regime.
    
    Uses: client.query_load_forecast(country_code, start, end)
    
    Output format:
        # Load Forecast for DE-LU on 2024-06-15
        # Source: ENTSO-E
        # Unit: MW
        
        Hour (CET),Forecasted Load MW
        00:00,52000
        ...
    """
    # TODO: Implement similarly to other query functions
    pass


def query_actual_load(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch actual total load.
    
    Uses: client.query_load(country_code, start, end)
    """
    # TODO: Implement
    pass


# ─────────────────────────────────────────────
# CROSS-BORDER FLOWS
# ─────────────────────────────────────────────

def query_crossborder_flows(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch cross-border physical flows for a bidding zone.
    
    Cross-border flows matter because they affect the effective supply/demand balance.
    Per Kri20 and Kat19, coupling effects between markets are significant.
    
    Uses: client.query_crossborder_flows(country_code_from, country_code_to, start, end)
    You need to query flows from/to all neighboring zones.
    
    For DE-LU, neighbors are: AT, FR, NL, PL, CZ, DK1, DK2, CH
    For CZ, neighbors are: DE-LU, AT, PL, SK
    
    Output format:
        # Cross-Border Flows for DE-LU on 2024-06-15
        # Source: ENTSO-E
        # Positive = import into DE-LU, Negative = export from DE-LU
        # Unit: MW
        
        Hour,AT,FR,NL,PL,CZ,DK1,DK2,CH,Net Import
        00:00,500,-1200,300,-400,800,...
        ...
    """
    # TODO:
    # 1. Define neighbor map
    # 2. Query both directions (from/to) for each neighbor
    # 3. Compute net flow (import = from_neighbor - to_neighbor)
    # 4. Sum all for net import
    # 5. Format as string
    # NOTE: This makes many API calls. Cache aggressively. Consider querying
    #   only the most important neighbors first (AT, FR, CZ for DE).
    #   Some calls may fail for less-reported borders — handle gracefully.
    pass


# ─────────────────────────────────────────────
# OUTAGES (REMIT UMMs)
# ─────────────────────────────────────────────

def query_outages(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch generation unit unavailabilities (planned and unplanned outages).
    
    Outage data is important for:
    - Estimating available conventional capacity (affects merit order steepness)
    - Detecting sudden unplanned outages that can cause price spikes
    - REMIT compliance (outage knowledge can be inside information per Hie20)
    
    Per Hir22, outage changes (delta_O_planned and delta_O_unplanned) are 
    significant features in intraday price models.
    
    Uses: client.query_unavailability_of_generation_units(country_code, start, end)
    Returns a DataFrame with columns like 'unavailable_MW', 'plant_type', etc.
    
    Output format:
        # Generation Outages for DE-LU on 2024-06-15
        # Source: ENTSO-E (REMIT UMMs)
        # Unit: MW unavailable
        
        Summary:
        Total planned unavailable: 8500 MW
        Total unplanned unavailable: 2100 MW
        
        Breakdown by type:
        Nuclear: 1200 MW planned, 0 MW unplanned
        Coal: 3500 MW planned, 800 MW unplanned
        Gas: 2800 MW planned, 1300 MW unplanned
        ...
    """
    # TODO:
    # 1. Call client.query_unavailability_of_generation_units(country_code, start, end)
    # 2. Parse the result — it's complex, with time ranges and MW amounts
    # 3. Aggregate by: planned vs unplanned, fuel type
    # 4. Provide both summary and detail
    # NOTE: This endpoint can return a LOT of data. Summarize sensibly.
    pass


# ─────────────────────────────────────────────
# IMBALANCE / BALANCING
# ─────────────────────────────────────────────

def query_imbalance_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch imbalance (balancing energy) prices.
    
    Imbalance prices are the penalty/reward for being short/long at delivery.
    They matter for risk assessment — per Nar22 and Bro22, imbalance exposure
    is a key risk dimension in power trading.
    
    Uses: client.query_imbalance_prices(country_code, start, end)
    
    Output format:
        # Imbalance Prices for DE-LU on 2024-06-15
        # Source: ENTSO-E
        # Unit: EUR/MWh
        
        Hour,Short Imbalance Price,Long Imbalance Price
        00:00,65.00,35.00
        ...
    """
    # TODO: Implement
    pass
```

**Key entsoe-py usage notes**:
- All `query_*` methods take `country_code` (the EIC string), `start` (pd.Timestamp with tz), `end` (pd.Timestamp with tz)
- Country codes: use the EIC codes from `BIDDING_ZONES` in `energy_utils.py`
- The library handles pagination and XML parsing internally
- Rate limits: ENTSO-E allows ~400 requests/minute. Add a small sleep between calls if doing bulk fetches
- The API key goes in: `client = EntsoePandasClient(api_key=key)`
- Error handling: Wrap all calls in try/except. Common errors: `NoMatchingDataError` (no data for that period), `InvalidBusinessParameterError` (bad zone/date)

---

### File 3: `ote_client.py` — OTE Czech Market SOAP Client

**Purpose**: Fetch Czech electricity market data from the OTE SOAP API.

**Dependencies**: You need to install `zeep` — run `pip install zeep --break-system-packages`. Alternatively, you can use raw `requests` with XML POST bodies (examples below).

**Endpoint**: `http://www.ote-cr.cz/services/PublicDataService`
**WSDL**: `http://www.ote-cr.cz/services/PublicDataService/wsdl`
**No authentication required.**
**XML namespace**: `xmlns:pub="http://www.ote-cr.cz/schema/service/public"`

**What to implement**:

```python
"""OTE Czech Republic electricity market SOAP client.

OTE (Operátor trhu s elektřinou) operates the Czech electricity market.
This client fetches day-ahead prices, intraday continuous VWAP prices,
IDA auction results, and imbalance settlement data.

SOAP endpoint: http://www.ote-cr.cz/services/PublicDataService
WSDL: http://www.ote-cr.cz/services/PublicDataService/wsdl
No authentication required.

Reference: uzivatelskymanual_webove_sluzby_ote_g.pdf in project knowledge.
"""

import logging
import requests
from xml.etree import ElementTree as ET
from datetime import datetime
from typing import Annotated, Optional, List, Dict
import pandas as pd

from .config import get_config
from .energy_utils import format_price_table, get_cache_path

logger = logging.getLogger(__name__)

OTE_NAMESPACE = "http://www.ote-cr.cz/schema/service/public"
OTE_SOAP_URL = "http://www.ote-cr.cz/services/PublicDataService"


def _soap_request(method_name: str, params: Dict[str, str]) -> ET.Element:
    """Send a SOAP request to the OTE API and return the parsed XML response.
    
    Args:
        method_name: e.g. "GetDamPriceE", "GetImPricePeriodE"
        params: dict of XML element name -> value, e.g. 
                {"StartDate": "2024-06-15", "EndDate": "2024-06-15", "InEur": "true"}
    
    Returns:
        The parsed XML root Element of the response body
        
    Raises:
        requests.RequestException on network errors
        ValueError if response is not valid SOAP XML
    """
    # Build the SOAP envelope. Example for GetDamPriceE:
    #
    # <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" 
    #                   xmlns:pub="http://www.ote-cr.cz/schema/service/public">
    #   <soapenv:Header/>
    #   <soapenv:Body>
    #     <pub:GetDamPriceE>
    #       <pub:StartDate>2025-01-01</pub:StartDate>
    #       <pub:EndDate>2025-01-01</pub:EndDate>
    #       <pub:InEur>true</pub:InEur>
    #     </pub:GetDamPriceE>
    #   </soapenv:Body>
    # </soapenv:Envelope>
    
    # TODO: Build XML string, POST to OTE_SOAP_URL with 
    # headers={"Content-Type": "text/xml; charset=utf-8"}
    # Parse response XML, extract the body content
    # Handle HTTP errors and SOAP faults
    pass


def _parse_items(root: ET.Element, response_tag: str) -> List[Dict[str, str]]:
    """Parse <Item> elements from an OTE SOAP response.
    
    OTE responses have structure:
    <{response_tag}Response>
      <Result>
        <Item>
          <Date>2024-06-15</Date>
          <Hour>1</Hour>
          <Price>45.00</Price>
          <Volume>2500.0</Volume>
        </Item>
        ...
      </Result>
    </{response_tag}Response>
    
    Args:
        root: The parsed XML root
        response_tag: e.g. "GetDamPriceE"
        
    Returns:
        List of dicts, each representing one Item with tag->text mappings
    """
    # TODO: Navigate XML tree, find all Item elements, extract child text
    # Watch out for namespace handling — OTE uses the namespace in responses
    # Use namespace map: ns = {"pub": OTE_NAMESPACE} or iterate without namespace
    pass


# ─────────────────────────────────────────────
# DAY-AHEAD MARKET
# ─────────────────────────────────────────────

def get_dam_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    in_eur: Annotated[bool, "Return prices in EUR (True) or CZK (False)"] = True,
) -> str:
    """Fetch Czech day-ahead hourly prices and volumes.
    
    OTE SOAP method: GetDamPriceE
    Parameters: StartDate, EndDate, StartHour (opt), EndHour (opt), InEur (opt)
    
    Response fields per Item: Date, Hour, Price, Volume, Emerg (optional)
    - Hour: 1-24 (or 25 for DST autumn day)
    - Price: EUR/MWh or CZK/MWh depending on InEur
    - Volume: MWh traded for CZ in that hour
    - Emerg: 1 if emergency state declared (prices/volumes may be absent)
    
    Example SOAP request body:
        <pub:GetDamPriceE>
          <pub:StartDate>2025-01-01</pub:StartDate>
          <pub:EndDate>2025-01-01</pub:EndDate>
          <pub:InEur>true</pub:InEur>
        </pub:GetDamPriceE>
    
    Example response Item:
        <Item>
          <Date>2025-01-01</Date>
          <Hour>1</Hour>
          <Price>21.00</Price>
          <Volume>2935.0</Volume>
        </Item>
    """
    # TODO: Call _soap_request("GetDamPriceE", {StartDate, EndDate, InEur})
    # Parse items, format as string table
    pass


# ─────────────────────────────────────────────
# INTRADAY CONTINUOUS MARKET
# ─────────────────────────────────────────────

def get_intraday_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
) -> str:
    """Fetch Czech intraday continuous market hourly VWAP prices and volumes.
    
    OTE SOAP method: GetImPriceE
    Parameters: StartDate, EndDate, StartHour (opt), EndHour (opt)
    
    Response fields: Date, Hour, Price (VWAP in EUR/MWh), Volume (MWh)
    
    NOTE: This gives DAILY-LEVEL aggregation. For 15-min resolution, 
    use get_intraday_prices_period() instead.
    """
    # TODO: Call _soap_request("GetImPriceE", ...), parse, format
    pass


def get_intraday_prices_period(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
) -> str:
    """Fetch Czech intraday continuous market prices per 15-minute period.
    
    OTE SOAP method: GetImPricePeriodE
    Parameters: StartDate, EndDate, StartPeriod (opt), EndPeriod (opt)
    
    Response fields: Date, PeriodResolution (PT15M), PeriodIndex (1-96),
                     Price (VWAP EUR/MWh), Volume (MWh)
    
    PeriodIndex 1 = 00:00-00:15, PeriodIndex 2 = 00:15-00:30, etc.
    
    Example SOAP request:
        <pub:GetImPricePeriodE>
          <pub:StartDate>2024-07-01</pub:StartDate>
          <pub:EndDate>2024-07-01</pub:EndDate>
        </pub:GetImPricePeriodE>
    
    Example response:
        <Item>
          <Date>2024-07-01</Date>
          <PeriodResolution>PT15M</PeriodResolution>
          <PeriodIndex>1</PeriodIndex>
          <Price>95.30</Price>
          <Volume>62.221</Volume>
        </Item>
    """
    # TODO: Implement
    pass


# ─────────────────────────────────────────────
# INTRADAY AUCTIONS (IDA)
# ─────────────────────────────────────────────

def get_ida_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    auction: Annotated[Optional[str], "Auction type: 'IDA1', 'IDA2', or 'IDA3'. None for all."] = None,
) -> str:
    """Fetch IDA (Intraday Auction) results for Czech market.
    
    OTE SOAP method: GetIDAPriceE (hourly) or GetIDAPricePeriodE (per period)
    
    There are three intraday auctions: IDA1, IDA2, IDA3.
    
    For GetIDAPricePeriodE:
    Parameters: StartDate, EndDate, Auction (IDA1/IDA2/IDA3), InEur (opt),
                StartHour (opt), EndHour (opt)
    
    Response fields: Date, Hour, PriceCZ, VolumeCZ, ImportCZ, ExportCZ, SaldoCZ, Emerg
    
    Example request:
        <pub:GetIDAAllE>
          <pub:StartDate>2024-06-25</pub:StartDate>
          <pub:EndDate>2024-06-25</pub:EndDate>
          <pub:Auction>IDA1</pub:Auction>
          <pub:InEur>true</pub:InEur>
        </pub:GetIDAAllE>
    """
    # TODO: Implement — call GetIDAPriceE or GetIDAPricePeriodE
    pass


# ─────────────────────────────────────────────
# IMBALANCE SETTLEMENT
# ─────────────────────────────────────────────

def get_imbalance_settlement(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    version: Annotated[int, "Settlement version: 0=daily, 1=monthly, 2=final"] = 0,
) -> str:
    """Fetch Czech imbalance settlement data.
    
    OTE SOAP method: GetImbalanceSettlementE
    Parameters: Version (0/1/2), StartDate, EndDate, StartHour (opt), EndHour (opt)
    
    Version 0 = daily preliminary settlement
    Version 1 = monthly settlement  
    Version 2 = final monthly settlement
    
    NOTE: Data is available up to delivery date 30.6.2024 as of the manual.
    """
    # TODO: Implement
    pass
```

**SOAP request template for reference** (copy this pattern for all methods):

```xml
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" 
                  xmlns:pub="http://www.ote-cr.cz/schema/service/public">
  <soapenv:Header/>
  <soapenv:Body>
    <pub:{METHOD_NAME}>
      <pub:StartDate>{YYYY-MM-DD}</pub:StartDate>
      <pub:EndDate>{YYYY-MM-DD}</pub:EndDate>
      <!-- Optional parameters as needed -->
    </pub:{METHOD_NAME}>
  </soapenv:Body>
</soapenv:Envelope>
```

**Important notes**:
- Hour indices are 1-25 (hour 25 is the extra hour in autumn DST changeover)
- Period indices are 1-96 for 15-min resolution (or 1-100 on DST autumn day)
- Decimal separator in responses is a dot (.)
- Always request `InEur=true` when the parameter is available
- During emergency state (Emerg=1), price/volume fields may be missing in the response
- The endpoint uses HTTP (not HTTPS) — this is correct and intentional

---

### File 4: `smard_client.py` — SMARD German Data Client

**Purpose**: Fetch detailed German generation, load, and residual load data from SMARD.

**Dependencies**: Only `requests` (already available).

**Base URL**: `https://www.smard.de/app/chart_data`

**What to implement**:

```python
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

The response is JSON:
  {
    "meta_data": {...},
    "series": [[timestamp_ms, value], [timestamp_ms, value], ...]
  }
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional, Dict, List
import pandas as pd

from .energy_utils import CET, format_price_table, get_cache_path
from .config import get_config

logger = logging.getLogger(__name__)

SMARD_BASE_URL = "https://www.smard.de/app/chart_data"

# SMARD filter IDs for electricity generation by type
FILTER_IDS = {
    # Generation by source
    "generation_total": 410,
    "generation_biomass": 4169,
    "generation_hydro": 1226,
    "generation_wind_offshore": 1225,
    "generation_wind_onshore": 4067,
    "generation_solar": 4068,
    "generation_nuclear": 1224,
    "generation_lignite": 1223,
    "generation_hard_coal": 4069,
    "generation_gas": 4071,
    "generation_pumped_storage": 4070,
    "generation_other": 1227,
    # Consumption / load
    "total_load": 410,
    "residual_load": 5097,
    # Prices
    "day_ahead_price": 4169,  # verify this
}

def _get_week_start_timestamp(date_str: str) -> int:
    """Get the Unix timestamp (ms) for the Monday 00:00 CET of the week containing the date.
    
    SMARD organizes data in weekly chunks starting Monday.
    """
    # TODO: Parse date, find preceding Monday, convert to CET, return ms timestamp
    pass


def _fetch_smard_series(filter_id: int, resolution: str, date_str: str) -> pd.DataFrame:
    """Fetch a single SMARD data series.
    
    Args:
        filter_id: SMARD filter identifier
        resolution: "hour" or "quarterhour"
        date_str: any date in YYYY-MM-DD format
    
    Returns:
        DataFrame with DatetimeIndex (CET) and one value column
    """
    # TODO:
    # 1. Calculate week start timestamp
    # 2. Build URL: f"{SMARD_BASE_URL}/{filter_id}/{resolution}/{ts_ms}.json"
    # 3. GET request
    # 4. Parse JSON, extract "series" array
    # 5. Convert [[ts_ms, value], ...] to DataFrame
    # 6. Filter to just the requested date
    # 7. Handle None/null values in the series
    pass


def get_german_generation(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch German generation breakdown by type from SMARD.
    
    Returns generation in MW for each source type.
    Useful for computing merit order steepness (per Kre21b):
    the ratio of residual load to total conventional capacity indicates
    how steep the merit order curve is at the current operating point.
    
    Output format:
        # German Generation by Type on 2024-06-15 (hourly)
        # Source: SMARD (Bundesnetzagentur)
        # Unit: MW
        
        Hour,Wind On,Wind Off,Solar,Nuclear,Lignite,Hard Coal,Gas,Hydro,Biomass,Other
        00:00,12000,3500,0,4000,8500,3200,5100,1800,5000,300
        ...
    """
    # TODO: Fetch each generation type, merge into one DataFrame, format
    # Consider fetching in parallel or caching each series separately
    pass


def get_german_residual_load(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    resolution: Annotated[str, "Resolution: 'hour' or 'quarterhour'"] = "hour",
) -> str:
    """Fetch German residual load (total load minus wind and solar) from SMARD.
    
    Residual load = Total Load - Wind Onshore - Wind Offshore - Solar
    
    This is a KEY variable. Per Kie17 and Kre21b:
    - Low residual load → flat merit order → low price sensitivity to shocks
    - High residual load → steep merit order → high price sensitivity to shocks
    - The "demand quote" = Load_forecast / Planned_conventional_capacity
    
    SMARD provides a pre-computed residual load series (filter 5097).
    """
    # TODO: Fetch residual load series, format as string
    pass
```

**Notes on SMARD API quirks**:
- Data is organized in weekly chunks. The timestamp in the URL must be the Monday of the week.
- Response `series` values can be `null` for missing data points.
- Timestamps in the response are Unix ms in UTC. Convert to CET for display.
- The filter IDs above need verification — they may change. Test each one.
- As an alternative to reverse-engineering, check if the Python package `de-smard` works: `pip install de-smard --break-system-packages`

---

### File 5: `weather_client.py` — Open-Meteo Weather Client

**Purpose**: Fetch weather data (wind speed, solar radiation, temperature) for energy trading.

**Dependencies**: `openmeteo-requests`, `requests-cache`, `retry-requests` are all installed.

**What to implement**:

```python
"""Open-Meteo weather data client for energy trading.

Open-Meteo provides free weather data including:
- Historical weather observations
- Weather forecasts (up to 16 days)
- Historical forecasts (what the forecast was at a past date — critical for backtesting)

The "Historical Forecast" API is especially important: it lets you reconstruct
what the weather forecast looked like at a specific past date, which is needed
to simulate forecast-update trading strategies (Kup22) without look-ahead bias.

APIs used:
- Historical: https://archive-api.open-meteo.com/v1/archive
- Forecast: https://api.open-meteo.com/v1/forecast  
- Historical Forecast: https://historical-forecast-api.open-meteo.com/v1/forecast

No API key required. Free tier allows 10,000 requests/day.
"""

import logging
from datetime import datetime, date
from typing import Annotated, Optional, List
import pandas as pd

import openmeteo_requests
import requests_cache
from retry_requests import retry

from .config import get_config
from .energy_utils import CET, get_cache_path

logger = logging.getLogger(__name__)

# Representative coordinates for aggregated wind/solar forecasting
# These approximate the center-of-mass of installed capacity per zone
WEATHER_LOCATIONS = {
    "DE-LU": {
        "wind": [
            {"name": "North Sea Coast", "lat": 54.0, "lon": 8.5},    # Offshore/coastal
            {"name": "North Germany", "lat": 53.5, "lon": 10.0},     # Onshore north
            {"name": "Central Germany", "lat": 51.0, "lon": 10.0},   # Onshore central
        ],
        "solar": [
            {"name": "South Germany", "lat": 48.5, "lon": 11.5},     # Bavaria
            {"name": "East Germany", "lat": 51.5, "lon": 13.0},      # Saxony/Brandenburg
            {"name": "Central Germany", "lat": 50.0, "lon": 9.0},    # Hesse/Thuringia
        ],
    },
    "CZ": {
        "wind": [
            {"name": "North Moravia", "lat": 49.8, "lon": 17.5},
            {"name": "Central Bohemia", "lat": 50.0, "lon": 14.5},
        ],
        "solar": [
            {"name": "South Moravia", "lat": 49.0, "lon": 16.5},
            {"name": "Central Bohemia", "lat": 50.0, "lon": 14.5},
        ],
    },
}


def _get_session():
    """Create a cached, retry-enabled requests session for Open-Meteo.
    
    Uses requests-cache (SQLite backend) and retry-requests.
    """
    cache_session = requests_cache.CachedSession('.openmeteo_cache', expire_after=3600)
    retry_session = retry(cache_session, retries=3, backoff_factor=0.2)
    return openmeteo_requests.Client(session=retry_session)


def get_wind_forecast(
    delivery_date: Annotated[str, "Delivery date YYYY-MM-DD"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch wind speed data at hub heights relevant for wind turbines.
    
    Queries wind speed at 10m, 80m, and 120m for representative locations
    in the market area. These can be used to estimate wind power output.
    
    For actual wind power estimation:
        P_wind ≈ 0.5 * rho * A * Cp * v^3 (simplified)
    But in practice, just providing the raw wind speeds is sufficient
    for the LLM agents to interpret qualitatively.
    
    Variables requested: 
    - wind_speed_10m, wind_speed_80m, wind_speed_120m
    - wind_direction_80m
    - wind_gusts_10m
    
    Uses: Open-Meteo Forecast API or Historical API depending on date
    """
    # TODO:
    # 1. Determine if date is past (use Historical API) or future (use Forecast API)
    # 2. Get location list from WEATHER_LOCATIONS[market_area]["wind"]
    # 3. For each location, query wind data
    # 4. Aggregate (average or capacity-weighted average across locations)
    # 5. Format as string
    pass


def get_solar_forecast(
    delivery_date: Annotated[str, "Delivery date YYYY-MM-DD"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch solar irradiance data for PV output estimation.
    
    Variables requested:
    - shortwave_radiation (W/m²) — total solar radiation
    - direct_radiation (W/m²) — direct beam
    - diffuse_radiation (W/m²) — diffuse/scattered
    - sunshine_duration (seconds per hour)
    - cloud_cover (%)
    
    Uses representative solar locations for the market area.
    """
    # TODO: Similar to wind — query, aggregate, format
    pass


def get_weather_forecast(
    delivery_date: Annotated[str, "Delivery date YYYY-MM-DD"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch general weather data (temperature, precipitation, cloud cover).
    
    Temperature affects load (heating in winter, cooling in summer).
    Cloud cover affects solar output.
    Precipitation and storms can affect wind patterns.
    
    Variables: temperature_2m, apparent_temperature, precipitation, 
              cloud_cover, pressure_msl
    """
    # TODO: Implement
    pass


def get_historical_forecast(
    delivery_date: Annotated[str, "Delivery date YYYY-MM-DD"],
    forecast_issue_date: Annotated[str, "Date the forecast was issued YYYY-MM-DD"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
) -> str:
    """Fetch what the weather forecast WAS on a specific past date.
    
    THIS IS CRITICAL FOR BACKTESTING without look-ahead bias.
    
    Example: To backtest trading on June 15, 2024, you need to know what the
    weather forecast looked like on June 14 (day-ahead forecast) and on June 15 
    morning (intraday forecast update).
    
    Uses: Historical Forecast API
    URL: https://historical-forecast-api.open-meteo.com/v1/forecast
    Extra params: &start_date={delivery_date}&end_date={delivery_date}
                  &past_days=0 (or calculate difference)
    
    The historical forecast API returns the forecast that was available
    at forecast_issue_date for the delivery_date.
    
    NOTE: This is different from the Historical API (which returns ACTUALS).
    """
    # TODO: 
    # 1. Calculate the horizon: delivery_date - forecast_issue_date in days
    # 2. Query historical-forecast API with appropriate parameters
    # 3. Return wind + solar + temperature data as string
    pass
```

**Open-Meteo API usage notes**:
- The Historical Forecast API URL: `https://historical-forecast-api.open-meteo.com/v1/forecast`
- Historical data API URL: `https://archive-api.open-meteo.com/v1/archive`
- Regular forecast API URL: `https://api.open-meteo.com/v1/forecast`
- All APIs take `latitude`, `longitude`, `hourly` (comma-separated variable names), `start_date`, `end_date`
- The `openmeteo_requests` library returns objects with `.Hourly()` methods that give numpy arrays
- Rate limit: 10,000 requests/day on the free tier. Cache aggressively.

---

### File 6: `cache_layer.py` — Data Caching Layer

**Purpose**: Parquet-based local cache for API responses to avoid re-fetching during backtesting.

```python
"""Local caching layer for energy data API responses.

Uses parquet files organized by:
  {cache_dir}/{source}/{market_area}/{query_type}/{date}.parquet

Design principles:
- Cache by (source, query_type, market_area, date) tuple
- Parquet format for efficient storage of DataFrames
- String responses are cached as single-column DataFrames
- Cache never expires automatically — data is historical and immutable
- Provide a clear_cache() function for manual cache invalidation
"""

import os
import logging
from typing import Optional, Callable
import pandas as pd

from .config import get_config

logger = logging.getLogger(__name__)


def get_cache_dir() -> str:
    """Get the cache directory from config, creating it if needed."""
    config = get_config()
    cache_dir = config.get("data_cache_dir", os.path.expanduser("~/.tradingagents/cache"))
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def cache_key_path(source: str, query_type: str, market_area: str, date_str: str) -> str:
    """Build the full file path for a cache entry.
    
    Returns: e.g. /home/user/.tradingagents/cache/entsoe/DE-LU/day_ahead_prices/2024-06-15.parquet
    """
    # TODO: Implement, create intermediate directories
    pass


def load_cached(source: str, query_type: str, market_area: str, date_str: str) -> Optional[pd.DataFrame]:
    """Load a cached DataFrame if it exists, otherwise return None."""
    # TODO: Check if parquet file exists at cache_key_path, read and return it
    pass


def save_to_cache(df: pd.DataFrame, source: str, query_type: str, market_area: str, date_str: str) -> None:
    """Save a DataFrame to the cache."""
    # TODO: Save df to parquet at cache_key_path
    pass


def cached_fetch(source: str, query_type: str, market_area: str, date_str: str,
                 fetch_fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """Generic cache-or-fetch wrapper.
    
    Checks cache first. On miss, calls fetch_fn(), caches result, returns it.
    On any cache read error, falls through to fetch_fn().
    """
    # TODO: Implement
    pass


def clear_cache(source: Optional[str] = None, market_area: Optional[str] = None) -> int:
    """Clear cached data. Returns number of files deleted.
    
    If source and/or market_area specified, only clear matching entries.
    """
    # TODO: Implement — walk cache directory tree, delete matching files
    pass
```

---

### File 7: `mock_energy.py` — Synthetic Data Generator

**Purpose**: Generate realistic synthetic energy market data for testing when API access is unavailable.

```python
"""Synthetic energy market data generator for testing and development.

Generates realistic-looking data that mimics the patterns found in real
European electricity markets:
- Day-ahead prices with daily patterns (peak/off-peak), weekly seasonality,
  occasional negative prices, and rare spikes
- Renewable generation with solar daily cycle and wind variability
- Load with daily pattern (low at night, peak midday/evening)
- Intraday price deviations from day-ahead

This is NOT for production use — it's for unit tests and development when
API access is unavailable (e.g., no network, no API key, CI pipeline).

Calibration targets (approximate, based on German 2020-2023 data):
- DA price mean: ~50-80 EUR/MWh, std: ~30 EUR/MWh
- Wind capacity: ~60 GW installed, capacity factor ~20-35%
- Solar capacity: ~60 GW installed, capacity factor ~10-15% (annual avg)
- Load: ~40-80 GW range
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Annotated, Optional

from .energy_utils import CET


def generate_day_ahead_prices(
    delivery_date: Annotated[str, "Date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone"] = "DE-LU",
    seed: Optional[int] = None,
) -> str:
    """Generate synthetic day-ahead prices for 24 hours.
    
    Features to include:
    - Daily shape: lower at night (hours 0-5), peak midday (10-14) and evening (18-20)
    - Weekend effect: lower prices on weekends
    - Random component with occasional negative prices (5% chance per hour)
    - Rare spikes (1% chance per hour, up to 5x normal)
    """
    # TODO: Implement with numpy random generation
    pass


def generate_wind_forecast(
    delivery_date: Annotated[str, "Date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone"] = "DE-LU",
    seed: Optional[int] = None,
) -> str:
    """Generate synthetic wind power forecast data.
    
    Features:
    - Base level with autocorrelation (wind doesn't change instantly)
    - Higher capacity factors in winter than summer
    - Some day/night pattern (slightly higher at night)
    - Capacity factor range: 5-90% of installed capacity
    """
    # TODO: Implement
    pass


def generate_solar_forecast(
    delivery_date: Annotated[str, "Date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone"] = "DE-LU",
    seed: Optional[int] = None,
) -> str:
    """Generate synthetic solar PV forecast data.
    
    Features:
    - Zero at night (sunrise/sunset varies by season)
    - Peak at solar noon
    - Seasonal variation (much higher in summer)
    - Cloud cover randomness
    """
    # TODO: Implement
    pass


def generate_load_forecast(
    delivery_date: Annotated[str, "Date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone"] = "DE-LU",
    seed: Optional[int] = None,
) -> str:
    """Generate synthetic load forecast.
    
    Features:
    - Daily pattern: low at night, ramp up 6-9am, plateau, evening peak
    - Weekend: lower and flatter than weekdays
    - Temperature dependency (not modeled here, just random variation)
    """
    # TODO: Implement
    pass
```

---

## Files to Modify

### Modify 1: `tradingagents/dataflows/interface.py`

**What to change**: Add the new energy tool categories, vendor mappings, and import the new client functions. Keep all existing stock code intact.

**Specifically**:

1. Add imports at the top (after existing imports):

```python
# Energy market client imports
from .entsoe_client import (
    query_day_ahead_prices as entsoe_day_ahead_prices,
    query_wind_solar_forecast as entsoe_wind_solar_forecast,
    query_actual_generation as entsoe_actual_generation,
    query_generation_forecast_updates as entsoe_forecast_updates,
    query_load_forecast as entsoe_load_forecast,
    query_actual_load as entsoe_actual_load,
    query_crossborder_flows as entsoe_crossborder_flows,
    query_outages as entsoe_outages,
    query_imbalance_prices as entsoe_imbalance_prices,
)
from .ote_client import (
    get_dam_prices as ote_dam_prices,
    get_intraday_prices as ote_intraday_prices,
    get_intraday_prices_period as ote_intraday_prices_period,
    get_ida_prices as ote_ida_prices,
    get_imbalance_settlement as ote_imbalance_settlement,
)
from .smard_client import (
    get_german_generation as smard_generation,
    get_german_residual_load as smard_residual_load,
)
from .weather_client import (
    get_wind_forecast as openmeteo_wind,
    get_solar_forecast as openmeteo_solar,
    get_weather_forecast as openmeteo_weather,
    get_historical_forecast as openmeteo_historical_forecast,
)
from .mock_energy import (
    generate_day_ahead_prices as mock_day_ahead,
    generate_wind_forecast as mock_wind,
    generate_solar_forecast as mock_solar,
    generate_load_forecast as mock_load,
)
```

2. Add new `TOOLS_CATEGORIES` entries (keep existing ones, add these):

```python
# ENERGY MARKET tool categories (used when market_type is "energy")
ENERGY_TOOLS_CATEGORIES = {
    "price_data": {
        "description": "Electricity price data (day-ahead, intraday continuous, intraday auction)",
        "tools": ["get_day_ahead_prices", "get_intraday_prices", "get_intraday_auction_prices"]
    },
    "system_data": {
        "description": "Grid system state data",
        "tools": ["get_generation_forecast", "get_actual_generation", "get_load_forecast",
                  "get_cross_border_flows", "get_outages", "get_balancing_data"]
    },
    "weather_data": {
        "description": "Weather and renewable forecast data",
        "tools": ["get_weather_forecast", "get_solar_forecast", "get_wind_forecast",
                  "get_forecast_updates"]
    },
    "market_fundamentals": {
        "description": "Market structure data",
        "tools": ["get_merit_order_proxy", "get_residual_load", "get_auction_curves"]
    },
    "news_data": {
        "description": "Energy market news and regulatory data",
        "tools": ["get_energy_news", "get_outage_notifications", "get_remit_messages"]
    }
}
```

3. Add new `VENDOR_METHODS` entries for energy tools:

```python
ENERGY_VENDOR_METHODS = {
    "get_day_ahead_prices": {
        "entsoe": entsoe_day_ahead_prices,
        "ote": ote_dam_prices,
        "mock": mock_day_ahead,
    },
    "get_intraday_prices": {
        "ote": ote_intraday_prices_period,
        # DE intraday is harder — ENTSO-E doesn't have continuous data
        # For DE, we'd need EPEX data (paid) or SMARD indices
    },
    "get_intraday_auction_prices": {
        "ote": ote_ida_prices,
    },
    "get_generation_forecast": {
        "entsoe": entsoe_wind_solar_forecast,
    },
    "get_actual_generation": {
        "entsoe": entsoe_actual_generation,
        "smard": smard_generation,
    },
    "get_load_forecast": {
        "entsoe": entsoe_load_forecast,
        "mock": mock_load,
    },
    "get_cross_border_flows": {
        "entsoe": entsoe_crossborder_flows,
    },
    "get_outages": {
        "entsoe": entsoe_outages,
    },
    "get_balancing_data": {
        "entsoe": entsoe_imbalance_prices,
        "ote": ote_imbalance_settlement,
    },
    "get_weather_forecast": {
        "open_meteo": openmeteo_weather,
    },
    "get_solar_forecast": {
        "open_meteo": openmeteo_solar,
        "mock": mock_solar,
    },
    "get_wind_forecast": {
        "open_meteo": openmeteo_wind,
        "mock": mock_wind,
    },
    "get_forecast_updates": {
        "entsoe": entsoe_forecast_updates,
    },
    "get_residual_load": {
        "smard": smard_residual_load,
    },
}
```

4. Add energy vendor list:

```python
ENERGY_VENDOR_LIST = [
    "entsoe",
    "ote",
    "smard",
    "open_meteo",
    "mock",
]
```

5. Update `route_to_vendor` to handle market-area-aware routing: The energy config uses nested dicts for vendor selection (e.g., `"price_data": {"DE-LU": "entsoe", "CZ": "ote"}`). Update `get_vendor()` to handle this:

```python
def get_vendor(category: str, method: str = None, market_area: str = None) -> str:
    """Get the configured vendor. Handles market-area-specific routing."""
    config = get_config()
    
    # Check tool-level override
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    
    # Category-level
    vendor_config = config.get("data_vendors", {}).get(category, "default")
    
    # If vendor_config is a dict (market-area routing), look up the area
    if isinstance(vendor_config, dict) and market_area:
        return vendor_config.get(market_area, list(vendor_config.values())[0])
    
    return vendor_config if isinstance(vendor_config, str) else "default"
```

---

### Modify 2: `tradingagents/default_config.py`

**What to add** (keep all existing entries, add these new ones):

```python
# Energy market configuration
"market_type": "energy",                  # "stock" or "energy" — controls which tools/categories are active
"market_area": "DE-LU",                   # Primary bidding zone ("DE-LU" or "CZ")
"delivery_resolution": "60min",           # "60min" or "15min"
"trading_horizon": "intraday",            # "day_ahead" | "intraday" | "both"
"entsoe_api_key": os.environ.get("ENTSOE_API_KEY"),
"weather_provider": "open_meteo",
# Energy-specific vendor routing (used when market_type is "energy")
"energy_data_vendors": {
    "price_data": {
        "DE-LU": "entsoe",
        "CZ": "ote",
    },
    "system_data": "entsoe",
    "weather_data": "open_meteo",
    "market_fundamentals": {
        "DE-LU": "smard",
        "CZ": "entsoe",
    },
    "news_data": "entsoe",
},
# OTE-specific config
"ote_soap_url": "http://www.ote-cr.cz/services/PublicDataService",
# SMARD config
"smard_base_url": "https://www.smard.de/app/chart_data",
```

---

## Testing Plan

Create a file `tests/test_energy_data.py` with tests for each client. Use the mock client for tests that don't need network access. For integration tests (testing real API calls), use pytest markers:

```python
import pytest

# Unit tests (no network)
class TestEnergyUtils:
    def test_parse_delivery_period_hourly(self):
        start, end = parse_delivery_period("2024-06-15T14:00")
        assert end - start == timedelta(hours=1)
    
    def test_parse_delivery_period_quarter_hourly(self):
        start, end = parse_delivery_period("2024-06-15T14:00/PT15M")
        assert end - start == timedelta(minutes=15)
    
    def test_dst_spring(self):
        # March last Sunday: hour 2 should be handled
    
    def test_dst_autumn(self):
        # October last Sunday: double hour 2 should be averaged
    
    def test_bidding_zone_lookup(self):
        assert get_entsoe_area_code("DE-LU") == "10Y1001A1001A82H"

class TestMockEnergy:
    def test_mock_day_ahead_returns_string(self):
        result = generate_day_ahead_prices("2024-06-15")
        assert isinstance(result, str)
        assert "EUR/MWh" in result
    
    def test_mock_day_ahead_has_24_rows(self):
        result = generate_day_ahead_prices("2024-06-15")
        # Count data rows (lines that aren't comments)
        data_lines = [l for l in result.strip().split('\n') if not l.startswith('#') and l.strip()]
        assert len(data_lines) >= 24  # header + 24 hours

# Integration tests (need network + API key)
@pytest.mark.integration
class TestEntsoEIntegration:
    def test_day_ahead_prices(self):
        result = query_day_ahead_prices("2024-06-15", "DE-LU")
        assert isinstance(result, str)
        assert "EUR/MWh" in result

@pytest.mark.integration
class TestOTEIntegration:
    def test_dam_prices(self):
        result = get_dam_prices("2024-06-15")
        assert isinstance(result, str)
```

---

## Implementation Order

Follow this exact order to avoid dependency issues:

1. **`energy_utils.py`** — no external dependencies, everything else imports from it
2. **`cache_layer.py`** — depends only on energy_utils and config
3. **`mock_energy.py`** — depends only on energy_utils (for testing without network)
4. **`entsoe_client.py`** — depends on energy_utils, cache_layer, entsoe-py
5. **`ote_client.py`** — depends on energy_utils, cache_layer, requests
6. **`smard_client.py`** — depends on energy_utils, cache_layer, requests
7. **`weather_client.py`** — depends on energy_utils, cache_layer, openmeteo-requests
8. **Update `interface.py`** — imports from all new modules
9. **Update `default_config.py`** — add new config entries

---

## Critical Gotchas

1. **Timezone handling**: ALL energy data is in CET/CEST (Europe/Berlin). The entsoe-py library handles this correctly if you pass timezone-aware pd.Timestamps. NEVER use naive datetimes.

2. **DST transitions**: Spring forward (missing hour 2AM), Autumn back (duplicate hour 2AM). Every function must handle this. Standard practice: forward-fill in spring, average in autumn (Hir23 convention).

3. **Return type**: Every public function returns `str`. Not DataFrame, not dict. Strings formatted for LLM consumption.

4. **Caching**: Historical data doesn't change. Cache aggressively. The caching must be transparent — the caller shouldn't know or care whether data came from cache or API.

5. **No look-ahead bias**: When implementing `get_historical_forecast()`, make sure you're using the Historical FORECAST API (what was forecasted) not the Historical API (what actually happened). These are different endpoints.

6. **Error handling**: Wrap all API calls in try/except. Return a descriptive error string on failure (e.g., "Error fetching day-ahead prices for DE-LU on 2024-06-15: No data available"), not an exception. The LLM agents need to handle missing data gracefully.

7. **ENTSO-E rate limits**: Max ~400 requests/minute. If doing bulk fetches (e.g., cross-border flows for all neighbors), add `time.sleep(0.2)` between calls.

8. **OTE SOAP endpoint uses HTTP** (not HTTPS). This is correct and expected.

9. **SMARD data is weekly**: You fetch a whole week and then filter to the requested date. The week starts on Monday.

10. **Install `zeep` before implementing `ote_client.py`**: `pip install zeep --break-system-packages`. Alternatively, use raw XML with `requests` — the SOAP examples in this document show the exact XML templates.

---

## Validation Checklist

After implementation, verify:

- [ ] `energy_utils.py`: `parse_delivery_period("2024-06-15T14:00")` returns correct CET datetimes
- [ ] `energy_utils.py`: `get_entsoe_area_code("DE-LU")` returns `"10Y1001A1001A82H"`
- [ ] `mock_energy.py`: All `generate_*` functions return non-empty strings
- [ ] `mock_energy.py`: Generated prices have realistic ranges (not all zeros, not all 999)
- [ ] `cache_layer.py`: Write-then-read roundtrip preserves data exactly
- [ ] `entsoe_client.py`: `query_day_ahead_prices("2024-06-15", "DE-LU")` returns 24 hourly prices (requires API key and network)
- [ ] `ote_client.py`: `get_dam_prices("2024-06-15")` returns hourly prices for CZ (requires network, no key needed)
- [ ] `interface.py`: `ENERGY_TOOLS_CATEGORIES` is importable without errors
- [ ] `interface.py`: All functions referenced in `ENERGY_VENDOR_METHODS` are importable
- [ ] `default_config.py`: New config entries don't break existing stock trading flow
- [ ] No circular imports between any of the new modules
