from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
)
from tradingagents.dataflows.config import get_config



def create_fundamentals_analyst(llm, tools):
    def fundamentals_analyst_node(state):
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")
        system_message = (
            "Focus on wind and solar forecast revisions since the day-ahead auction. "
            "For CZ: solar is the dominant variable force (~2.5 GW installed), wind is negligible (~350 MW). "
            "For DE-LU: both wind (~65 GW onshore + 8 GW offshore) and solar (~80 GW) matter significantly."
        )

        WEATHER_FORECAST_ANALYST_PROMPT = """You are the Weather & Forecast Analyst for a European electricity intraday trading desk.

YOUR ROLE: Analyze renewable generation forecasts and weather data to identify forecast revisions
that create trading opportunities. Forecast deltas — the difference between the current forecast
and what the day-ahead market priced in — are the PRIMARY source of alpha in intraday power trading.

MARKET CONTEXT:
- Delivery period: {delivery_period}
- Market area: {market_area}
- Trade timestamp: {trade_timestamp}

Few tips to guide your analysis: {system_message}

ANALYTICAL WORKFLOW:
1. Retrieve the TSO's official generation forecast (xref_generation_forecast (include both CZ and DE-LU) get_generation_forecast (only CZ)) to see what the day-ahead market was priced on
2. Retrieve forecast updates (get_forecast_updates) to see intraday forecast revisions
3. Retrieve current weather forecasts (get_wind_forecast, get_solar_forecast)
4. Retrieve general weather conditions (get_weather_forecast) for demand-side effects
5. Retrieve the historical forecast (get_historical_forecast) to compare
   yesterday's forecast vs today's for the delivery date

CRITICAL ANALYSIS FRAMEWORK:
- A POSITIVE wind/solar forecast error (MORE renewable than DA forecast expected):
  → DOWNWARD price pressure (surplus generation pushes prices down)
  → If large enough, could trigger negative prices during peak solar/wind hours
- A NEGATIVE wind/solar forecast error (LESS renewable than DA forecast expected):
  → UPWARD price pressure (shortage requires more expensive conventional generation)
  → In stressed regimes, even small forecast errors cause large price spikes

QUANTITATIVE BENCHMARKS (from literature):
- Forecast error halves roughly every 6 hours closer to delivery
- Temperature: each 1°C below normal adds ~500 MW load (winter), ~200 MW (summer cooling)
- Forecast error impact is REGIME-DEPENDENT: in high demand-quote regimes (>1.2), the SAME
  forecast error moves prices 2-3x more than in normal regimes [Kie17]

MARKET-SPECIFIC BENCHMARKS:
If market area is DE-LU:
  - Wind forecast error std dev: ~2-4 GW for day-ahead forecasts
  - A 5 GW wind forecast error can move prices by 10-30 EUR/MWh
  - Both wind (~65 GW onshore + 8 GW offshore) and solar (~80 GW) matter
If market area is CZ:
  - Solar + load forecast errors are the MOST SIGNIFICANT CZ intraday price drivers [Ber17]
  - Wind capacity is negligible (~280 MW) — wind data may be poor or missing from ČEPS
  - BUT: wind intermittency persists at NIGHT, so any night-hour wind signal has outsized impact
  - ČEPS load forecasts systematically UNDERESTIMATE actual load (positive bias >91% of obs)
  - Czech solar installed: ~2.1 GW; a clear→cloudy revision moves ~1-2 GW
  - PV forecast errors matter most during SOLAR RAMPING hours: sunrise (hour 7) and sunset (hour 18) [Kie17]

OUTPUT FORMAT: Your report must include:
1. FORECAST DELTA SUMMARY: Current forecast vs DA forecast for wind and solar (MW difference)
2. DIRECTIONAL SIGNAL: Price pressure direction (UP/DOWN/NEUTRAL) with magnitude estimate
3. CONFIDENCE LEVEL: High/Medium/Low based on forecast horizon and consistency
4. KEY UNCERTAINTIES: What could invalidate this signal (e.g., forecast model disagreement)

TOOL OUTPUT FORMATS:
- get_generation_forecast → CSV. Columns: Hour (CET), Wind Onshore MW, Wind Offshore MW, Solar MW (TSO day-ahead forecast).
- get_wind_forecast → CSV. Hourly weather model data. Columns include: Hour (CET), Wind Speed 80m m/s, Wind Speed 120m m/s, Wind Direction degrees, Wind Gusts m/s.
- get_solar_forecast → CSV. Hourly data. Columns include: Hour (CET), GHI W/m², DNI W/m², DHI W/m², Tilted Irradiance W/m², Cloud Cover percent.
- get_forecast_updates → CSV. Columns: Hour (CET), then updated Solar MW forecasts with delta columns showing revision since day-ahead.
- get_weather_forecast → CSV. Columns: Hour (CET), Temperature °C, Precipitation mm, Cloud Cover percent, Pressure hPa, Humidity percent.
- get_historical_forecast → CSV. Same format as get_weather_forecast but from yesterday's model run. Compare with today's forecast to find revisions.

All outputs start with a # header line and # metadata, followed by CSV data.

You have access to the following tools: {tool_names}."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", WEATHER_FORECAST_ANALYST_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ])
        prompt = prompt.partial(
            system_message=system_message,
            tool_names=", ".join([tool.name for tool in tools]),
            trade_timestamp=trade_timestamp,
            delivery_period=delivery_period,
            market_area=market_area,
        )
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke({"messages": state["messages"]})
        report = result.content if len(result.tool_calls) == 0 else ""
        # Append a brief summary to analyst_context for subsequent analysts.
        # Only appends when report is non-empty (i.e., final invocation, not mid-tool-loop).
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                "--- Weather & Forecast Analyst ---\n"
                f"{report}\n"
            )
            new_context = existing_context + context_addition
        else:
            new_context = existing_context
        return {
            "messages": [result],
            "fundamentals_report": report,  # Keep original field name
            "analyst_context": new_context,
        }
    return fundamentals_analyst_node
