"""Cross-reference tools that query ALL available vendors for a single method.

These tools are meant for high-confidence validation — when an analyst wants
to compare data from multiple sources (e.g., ENTSO-E vs SMARD generation data)
to detect discrepancies and increase signal confidence.
"""
from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_all_vendors


@tool
def xref_day_ahead_prices(delivery_date: str, market_area: str = "CZ") -> str:
    """Cross-reference day-ahead prices from ALL available sources (ENTSO-E, OTE, SMARD).
    Compare to detect data quality issues or pricing discrepancies."""
    return route_to_all_vendors("get_day_ahead_prices",
                                delivery_date=delivery_date, market_area=market_area)

@tool
def xref_generation_forecast(delivery_date: str, market_area: str = "CZ") -> str:
    """Cross-reference generation forecasts from ALL sources (ENTSO-E, SMARD).
    """
    return route_to_all_vendors("get_generation_forecast",
                                delivery_date=delivery_date, market_area=market_area)

@tool
def xref_actual_generation(delivery_date: str, market_area: str = "CZ") -> str:
    """Cross-reference actual generation data from ALL sources (ENTSO-E, SMARD).
    Compare fuel-type breakdowns and totals to validate generation mix."""
    return route_to_all_vendors("get_actual_generation",
                                delivery_date=delivery_date, market_area=market_area)

@tool
def xref_load_forecast(delivery_date: str, market_area: str = "CZ") -> str:
    """Cross-reference load (demand) forecasts from ALL sources (ENTSO-E, SMARD).
    Compare to assess forecast agreement and detect systematic bias."""
    return route_to_all_vendors("get_load_forecast",
                                delivery_date=delivery_date, market_area=market_area)

@tool
def xref_actual_load(delivery_date: str, market_area: str = "CZ") -> str:
    """Cross-reference actual load (demand) data from ALL sources (ENTSO-E, SMARD).
    Compare to validate observed demand levels and detect reporting issues."""
    return route_to_all_vendors("get_actual_load",
                                delivery_date=delivery_date, market_area=market_area)

@tool
def xref_residual_load(delivery_date: str, market_area: str = "CZ") -> str:
    """Cross-reference residual load from ALL sources (ENTSO-E, SMARD).
    Compare to validate the supply-demand balance assessment."""
    return route_to_all_vendors("get_residual_load",
                                delivery_date=delivery_date, market_area=market_area)

@tool
def xref_balancing_data(delivery_date: str, market_area: str = "CZ") -> str:
    """Cross-reference imbalance/balancing data from ALL sources (ENTSO-E, OTE).
    Compare settlement prices and volumes from different market operators."""
    return route_to_all_vendors("get_balancing_data",
                                delivery_date=delivery_date, market_area=market_area)