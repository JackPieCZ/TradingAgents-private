import logging
from typing import Annotated

# Energy data imports
from .entsoe_client import (
    query_day_ahead_prices as entsoe_da_prices,
    query_intraday_prices as entsoe_id_prices,
    query_solar_forecast as entsoe_wind_solar_forecast,
    query_actual_generation as entsoe_actual_generation,
    query_generation_forecast_updates as entsoe_forecast_updates,
    query_load_forecast as entsoe_load_forecast,
    query_actual_load as entsoe_actual_load,
    query_crossborder_flows as entsoe_crossborder,
    query_outages as entsoe_outages,
    query_imbalance_prices as entsoe_imbalance,
    query_residual_load as entsoe_residual_load,
)
from .ote_client import (
    get_dam_prices as ote_da_prices,
    get_intraday_prices as ote_id_prices,
    get_ida_prices as ote_ida_prices,
    get_imbalance_settlement as ote_imbalance,
)
from .smard_client import (
    get_german_generation as smard_generation,
    get_german_residual_load as smard_residual_load,
    get_german_total_load as smard_total_load,
    get_smard_prices as dayahead_market_prices,
    get_german_generation_forecast as smard_generation_forecast,
    get_german_load_forecast as smard_load_forecast,
)
from .weather_client import (
    get_wind_forecast as openmeteo_wind,
    get_solar_forecast as openmeteo_solar,
    get_weather_forecast as openmeteo_weather,
    get_historical_forecast as openmeteo_historical,
)
from .mock_energy import (
    generate_day_ahead_prices as mock_da_prices,
    generate_intraday_prices as mock_id_prices,
    generate_wind_solar_forecast as mock_wind_solar,
    generate_load_forecast as mock_load,
    generate_residual_load as mock_residual_load,
    generate_weather_forecast as mock_weather,
)

# Configuration and routing logic
from .config import get_config
logger = logging.getLogger(__name__)

# Tools organized by category
TOOLS_CATEGORIES = {
    # Energy market data categories
    "price_data": {
        "description": "Electricity price data (day-ahead, intraday continuous, intraday auction)",
        "tools": [
            "get_day_ahead_prices",
            "get_intraday_prices",
            "get_intraday_auction_prices",
        ]
    },
    "system_data": {
        "description": "Grid system state data",
        "tools": [
            "get_generation_forecast",
            "get_actual_generation",
            "get_load_forecast",
            "get_actual_load",
            "get_cross_border_flows",
            "get_outage_notifications",
            "get_balancing_data",
            "get_residual_load",
        ]
    },
    "weather_data": {
        "description": "Weather and renewable forecast data",
        "tools": [
            "get_weather_forecast",
            "get_solar_forecast",
            "get_wind_forecast",
            "get_forecast_updates",
            "get_historical_forecast",
        ]
    },
    "market_fundamentals": {
        "description": "Market structure data",
        "tools": [
            "get_residual_load",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    "entsoe",
    "ote",
    "smard",
    "openmeteo",
    "mock",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # price_data (energy)
    "get_day_ahead_prices": {
        "entsoe": entsoe_da_prices,
        "ote": ote_da_prices,
        "smard": dayahead_market_prices,
        # "mock": mock_da_prices,
    },
    "get_intraday_prices": {
        # "entsoe": entsoe_id_prices,
        "ote": ote_id_prices,
        # "mock": mock_id_prices,
    },
    "get_intraday_auction_prices": {
        # "entsoe": entsoe_id_prices,
        "ote": ote_ida_prices,
    },

    # system_data (energy)
    "get_generation_forecast": {
        "entsoe": entsoe_wind_solar_forecast,
        "smard": smard_generation_forecast,
        # "mock": mock_wind_solar,
    },
    "get_actual_generation": {
        "entsoe": entsoe_actual_generation,
        "smard": smard_generation,
    },
    "get_load_forecast": {
        "entsoe": entsoe_load_forecast,
        "smard": smard_load_forecast,
        # "mock": mock_load,
    },
    "get_actual_load": {
        "entsoe": entsoe_actual_load,
        "smard": smard_total_load,
    },
    "get_cross_border_flows": {
        "entsoe": entsoe_crossborder,
    },
    "get_outage_notifications": {
        "entsoe": entsoe_outages,
    },
    "get_balancing_data": {
        "entsoe": entsoe_imbalance,
        "ote": ote_imbalance,
    },
    "get_residual_load": {
        "entsoe": entsoe_residual_load,
        "smard": smard_residual_load,
        # "mock": mock_residual_load,
    },

    # weather_data (energy)
    "get_weather_forecast": {
        "openmeteo": openmeteo_weather,
        # "mock": mock_weather,
    },
    "get_solar_forecast": {
        "openmeteo": openmeteo_solar,
    },
    "get_wind_forecast": {
        "openmeteo": openmeteo_wind,
    },
    "get_forecast_updates": {
        "entsoe": entsoe_forecast_updates,
    },
    "get_historical_forecast": {
        "openmeteo": openmeteo_historical,
    },
}


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None, market_area: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Handles market-area-specific routing (e.g., DE-LU goes to entsoe, CZ goes to ote).
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    vendor_config = config.get("data_vendors", {}).get(category, "default")

    # If vendor_config is a dict (market-area routing), look up the area
    if isinstance(vendor_config, dict) and market_area:
        return vendor_config.get(market_area, list(vendor_config.values())[0])

    return vendor_config if isinstance(vendor_config, str) else "default"


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    logger.info(f"Executing tool call: {method} | args: {args} | kwargs: {kwargs}")

    category = get_category_for_method(method)

    # Try to extract market_area from kwargs to support market-aware routing
    market_area = kwargs.get("market_area", None)

    vendor_config = get_vendor(category, method, market_area)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        logger.error(f"Method '{method}' is not defined in VENDOR_METHODS")
        raise ValueError(f"Method '{method}' not supported")

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            logger.warning(f"Vendor '{vendor}' does not support method '{method}'. Skipping.")
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Vendor {vendor} failed for '{method}': {str(e)}. Falling back.")
            continue  # Catch generic energy API failures and trigger fallback

    raise RuntimeError(f"No available vendor for '{method}'")


def route_to_all_vendors(method: str, *args, **kwargs) -> str:
    """Call a tool method against ALL available vendors and return merged results.

    Each vendor's output is labeled with the vendor name. If a vendor fails,
    its section shows the error message instead of data. This is used for
    cross-referencing — analysts can compare data from multiple sources to
    detect discrepancies, validate signals, and improve confidence.

    Returns:
        A string with labeled sections for each vendor's response.
    """
    logger.info(f"Cross-referencing all vendors for: {method} | args: {args} | kwargs: {kwargs}")

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    available_vendors = VENDOR_METHODS[method]
    results_parts = []

    for vendor_name, vendor_impl in available_vendors.items():
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
        try:
            result = impl_func(*args, **kwargs)
            results_parts.append(
                f"# Source: {vendor_name.upper()}\n{result}"
            )
        except Exception as e:
            results_parts.append(
                f"# Source: {vendor_name.upper()}\n# ERROR: {str(e)}"
            )
            logger.warning(f"Vendor {vendor_name} failed for '{method}': {e}")

    if not results_parts:
        return f"# No vendors available for {method}"

    header = f"# Cross-reference: {method} ({len(results_parts)} sources)\n"
    return header + "\n\n".join(results_parts)
