# Phase 2-3 Implementation Plan

## Phase 2 — Detailed Implementation Plan

### Overview

**Goal**: Redesign the agent team from equity-focused to power-market-focused. Update state schema, tool definitions, and tool nodes.

**Papers to re-read before starting**: Kup22, Kie17, Kre21b, Hir22, Kat20

### Task 2.1: Create Energy Tool Files

These files expose the Phase 1 data methods as LangChain-compatible tools that agents can call.

**File: `tradingagents/agents/utils/energy_price_tools.py`** (replaces `core_stock_tools.py`)

```python
"""Energy price data tools for analyst agents."""
from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_day_ahead_prices(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch day-ahead auction clearing prices for a delivery date and bidding zone.
    Returns hourly prices in EUR/MWh. Use this to establish the price baseline
    that intraday trading operates around."""
    return route_to_vendor("get_day_ahead_prices", delivery_date=delivery_date, market_area=market_area)

@tool
def get_intraday_prices(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch intraday continuous market prices (VWAP, volume, spread metrics)
    for a delivery date. Shows how prices have moved relative to day-ahead."""
    return route_to_vendor("get_intraday_prices", delivery_date=delivery_date, market_area=market_area)

@tool
def get_intraday_auction_prices(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch IDA (Intraday Auction) clearing prices — IDA1, IDA2, IDA3.
    These sequential auctions provide price discovery between DA and delivery."""
    return route_to_vendor("get_intraday_auction_prices", delivery_date=delivery_date, market_area=market_area)

@tool
def get_imbalance_data(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch imbalance settlement prices and volumes. Imbalance price is
    the penalty for positions not closed before gate closure."""
    return route_to_vendor("get_balancing_data", delivery_date=delivery_date, market_area=market_area)
```

**File: `tradingagents/agents/utils/system_data_tools.py`** (replaces `fundamental_data_tools.py`)

```python
"""Grid system state tools for the System State Analyst."""
from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_residual_load(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch residual load forecast (total load minus wind minus solar).
    High residual load = tight conventional capacity = steep merit order = price sensitive to shocks.
    Low residual load = abundant renewables = potential negative prices."""
    return route_to_vendor("get_residual_load", delivery_date=delivery_date, market_area=market_area)

@tool
def get_actual_generation(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch actual generation breakdown by fuel type (wind, solar, gas, coal, etc.).
    Use to assess merit order position and available conventional capacity."""
    return route_to_vendor("get_actual_generation", delivery_date=delivery_date, market_area=market_area)

@tool
def get_load_forecast(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch the day-ahead total load (demand) forecast in MW."""
    return route_to_vendor("get_load_forecast", delivery_date=delivery_date, market_area=market_area)

@tool
def get_cross_border_flows(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch cross-border physical power flows with neighboring bidding zones.
    Positive = import into zone, Negative = export. Includes NTC capacity where available."""
    return route_to_vendor("get_cross_border_flows", delivery_date=delivery_date, market_area=market_area)

@tool
def get_outages(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch planned and unplanned generation unit outages (REMIT UMMs).
    Large outages tighten supply and can push prices up significantly."""
    return route_to_vendor("get_outages", delivery_date=delivery_date, market_area=market_area)
```

**File: `tradingagents/agents/utils/weather_tools.py`** (NEW — most important)

```python
"""Weather and renewable forecast tools for the Weather & Forecast Analyst."""
from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_wind_forecast(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch wind speed forecasts at turbine hub heights (80m, 120m) averaged
    across capacity-weighted representative locations. Includes wind direction
    and gust data. Key input for wind power production estimation."""
    return route_to_vendor("get_wind_forecast", delivery_date=delivery_date, market_area=market_area)

@tool
def get_solar_forecast(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch solar irradiance forecasts (GHI, DNI, DHI, tilted) and cloud cover
    averaged across representative PV locations. Key input for solar production estimation."""
    return route_to_vendor("get_solar_forecast", delivery_date=delivery_date, market_area=market_area)

@tool
def get_generation_forecast(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch the TSO's official day-ahead wind and solar generation forecast in MW.
    Compare this with weather data to assess forecast accuracy."""
    return route_to_vendor("get_generation_forecast", delivery_date=delivery_date, market_area=market_area)

@tool
def get_forecast_updates(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch intraday updates to the renewable generation forecast and compute
    deltas vs day-ahead forecast. CRITICAL SIGNAL: positive wind delta = more wind
    than expected = downward price pressure. This is the primary alpha source."""
    return route_to_vendor("get_forecast_updates", delivery_date=delivery_date, market_area=market_area)

@tool
def get_weather_forecast(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch general weather data: temperature, precipitation, cloud cover, pressure.
    Temperature affects demand (heating/cooling). Precipitation affects hydro and PV."""
    return route_to_vendor("get_weather_forecast", delivery_date=delivery_date, market_area=market_area)

@tool
def get_historical_forecast(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch what yesterday's weather forecast predicted for today. Compare with
    today's forecast to identify forecast revisions — the trading signal per Kup22.
    A large revision means the market has not yet fully priced in the new information."""
    from datetime import datetime, timedelta
    issue_date = (datetime.strptime(delivery_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    return route_to_vendor("get_historical_forecast",
                          delivery_date=delivery_date,
                          forecast_issue_date=issue_date,
                          market_area=market_area)
```

**File: `tradingagents/agents/utils/energy_news_tools.py`** (replaces `news_data_tools.py`)

```python
"""Energy news and regulatory tools for the News & Regulatory Analyst."""
from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_outage_notifications(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch REMIT urgent market messages (UMMs) about generation unit outages.
    Includes planned maintenance and unplanned outages with MW unavailable."""
    return route_to_vendor("get_outage_notifications", delivery_date=delivery_date, market_area=market_area)

@tool
def get_actual_load(delivery_date: str, market_area: str = "DE-LU") -> str:
    """Fetch actual realized total load (demand) for context on demand patterns."""
    return route_to_vendor("get_actual_load", delivery_date=delivery_date, market_area=market_area)
```

Note: `get_energy_news` and `get_remit_messages` from the strategy are deferred — no free structured news API exists. ENTSO-E outage data via `get_outage_notifications` covers the most critical REMIT information. A web-scraping news source can be added later.

### Task 2.2: Update AgentState

**File: `tradingagents/agents/utils/agent_states.py`**

Add the new power-specific fields while preserving backward compatibility with the stock path:

```python
class AgentState(MessagesState):
    # Core identifiers
    delivery_period: Annotated[str, "Delivery period start (ISO datetime), e.g. 2024-06-15T14:00"]
    market_area: Annotated[str, "Bidding zone (e.g. DE-LU, CZ)"]
    trade_date: Annotated[str, "Current trading timestamp"]

    # Backward compat — keep for stock path
    company_of_interest: Annotated[str, "Ticker or delivery_period identifier"]

    sender: Annotated[str, "Agent that sent this message"]

    # Analyst reports — power market names
    # Keep old field names as aliases for graph wiring compatibility
    market_report: Annotated[str, "Report from Price & Technical Analyst"]
    sentiment_report: Annotated[str, "Report from System State Analyst"]
    news_report: Annotated[str, "Report from Energy News & Regulatory Analyst"]
    fundamentals_report: Annotated[str, "Report from Weather & Forecast Analyst"]

    # Debate states (unchanged)
    investment_debate_state: Annotated[InvestDebateState, "Bull/bear debate state"]
    investment_plan: Annotated[str, "Research Manager's plan"]
    trader_investment_plan: Annotated[str, "Trader's plan"]
    risk_debate_state: Annotated[RiskDebateState, "Risk debate state"]
    final_trade_decision: Annotated[str, "Final decision"]
    past_context: Annotated[str, "Memory log context"]

    # NEW: Power-specific context
    day_ahead_position: Annotated[str, "Current day-ahead position for this delivery period"]
    residual_position: Annotated[str, "Current residual (unhedged) position"]
    regime_indicator: Annotated[str, "Current market regime classification"]
```

**Key design decision**: Keep the original report field names (`market_report`, `sentiment_report`, `news_report`, `fundamentals_report`) rather than renaming to `price_technical_report` etc. This avoids breaking the graph wiring, CLI display logic, and report formatting code. The analyst prompts and tool bindings will be different, but the state fields stay the same. The mapping is:

| State Field | Original Agent | New Agent |
|---|---|---|
| `market_report` | Market Analyst | **Price & Technical Analyst** |
| `sentiment_report` | Social Media Analyst | **System State Analyst** |
| `news_report` | News Analyst | **Energy News & Regulatory Analyst** |
| `fundamentals_report` | Fundamentals Analyst | **Weather & Forecast Analyst** |

### Task 2.3: Update Tool Nodes

**File: `tradingagents/graph/trading_graph.py`** — method `_create_tool_nodes()`

```python
# REPLACE the existing stock tool imports and mappings with:
from tradingagents.agents.utils.energy_price_tools import (
    get_day_ahead_prices, get_intraday_prices,
    get_intraday_auction_prices, get_imbalance_data
)
from tradingagents.agents.utils.system_data_tools import (
    get_residual_load, get_actual_generation,
    get_load_forecast, get_cross_border_flows, get_outages
)
from tradingagents.agents.utils.weather_tools import (
    get_wind_forecast, get_solar_forecast,
    get_generation_forecast, get_forecast_updates,
    get_weather_forecast, get_historical_forecast
)
from tradingagents.agents.utils.energy_news_tools import (
    get_outage_notifications, get_actual_load
)

# In _create_tool_nodes():
self.tool_nodes = {
    "market": ToolNode([  # Price & Technical Analyst
        get_day_ahead_prices, get_intraday_prices,
        get_intraday_auction_prices, get_imbalance_data
    ]),
    "social": ToolNode([  # System State Analyst
        get_residual_load, get_actual_generation,
        get_load_forecast, get_cross_border_flows, get_outages
    ]),
    "fundamentals": ToolNode([  # Weather & Forecast Analyst
        get_wind_forecast, get_solar_forecast,
        get_generation_forecast, get_forecast_updates,
        get_weather_forecast, get_historical_forecast
    ]),
    "news": ToolNode([  # Energy News & Regulatory Analyst
        get_outage_notifications, get_actual_load
    ]),
}
```

**Critical**: Keep the internal node names as `"market"`, `"social"`, `"fundamentals"`, `"news"` to match the existing graph routing in `conditional_logic.py` and `setup.py`. Only the prompts and tool bindings change.

### Task 2.4: Update Propagation

**File: `tradingagents/graph/propagation.py`** — `create_initial_state()`

Add power-market fields to the initial state dictionary:

```python
def create_initial_state(self, delivery_period, trade_timestamp, market_area="DE-LU"):
    return {
        "messages": [HumanMessage(content=f"Analyze the electricity market for delivery period "
                                         f"{delivery_period} in {market_area} as of {trade_timestamp}.")],
        # Backward compat
        "company_of_interest": f"{delivery_period}_{market_area}",
        # Power fields
        "delivery_period": delivery_period,
        "market_area": market_area,
        "trade_date": trade_timestamp,
        "sender": "",
        # Reports initialized empty
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        # Power context
        "day_ahead_position": "No current position",
        "residual_position": "No residual position",
        "regime_indicator": "Unknown — to be classified by System State Analyst",
        # Debate states
        "investment_debate_state": InvestDebateState(
            history="", bull_history="", bear_history="",
            current_response="", judge_decision="", count=0
        ),
        "investment_plan": "",
        "trader_investment_plan": "",
        "risk_debate_state": RiskDebateState(
            history="", agg_history="", con_history="",
            current_response="", judge_decision="", count=0
        ),
        "final_trade_decision": "",
        "past_context": "",
    }
```

### Task 2.5: Update propagate() Method Signature

**File: `tradingagents/graph/trading_graph.py`** — `propagate()` method

```python
def propagate(self, delivery_period: str, trade_timestamp: str, market_area: str = "DE-LU"):
    """Run the agent pipeline for a specific delivery period and market area.

    Args:
        delivery_period: Delivery date in YYYY-MM-DD format (or ISO datetime for specific hour)
        trade_timestamp: Current timestamp for the trading decision
        market_area: Bidding zone (default "DE-LU")

    Returns:
        (final_state, signal): The complete agent state and extracted trading signal
    """
    initial_state = self.propagator.create_initial_state(
        delivery_period, trade_timestamp, market_area
    )
    # ... rest of the method unchanged
```

---

## Phase 3 — Detailed Implementation Plan

### Overview

**Goal**: Replace stock-trading prompts with power-market-expert prompts. This is where the domain expertise from all 27 papers gets encoded.

**Papers the implementer MUST re-read before writing each prompt**:
- Weather & Forecast Analyst: Kup22 (Section 3-4), Kie17 (Section 4)
- System State Analyst: Kie17 (demand-quote regime), Kre21b (merit order slope), Kri20 (cross-border)
- Price & Technical Analyst: Kre21b (autoregressive features), Hir22 (price distributions), Ser22 (path forecasts)
- Energy News Analyst: Hie20 (REMIT framework)
- Researchers/Risk: Kat20 (execution), Nar21 (market impact), Bun18 (profitability)

### Task 3.1: Weather & Forecast Analyst (MOST IMPORTANT)

**File: `tradingagents/agents/analysts/fundamentals_analyst.py`** (rewrite, keep filename)

This is the highest-value analyst. Forecast revisions are the primary alpha source.

**System prompt** (full text — the implementer should use this verbatim):

```python
WEATHER_FORECAST_ANALYST_PROMPT = """You are the Weather & Forecast Analyst for a European electricity intraday trading desk.

YOUR ROLE: Analyze renewable generation forecasts and weather data to identify forecast revisions
that create trading opportunities. Forecast deltas — the difference between the current forecast
and what the day-ahead market priced in — are the PRIMARY source of alpha in intraday power trading.

MARKET CONTEXT:
- Delivery period: {delivery_period}
- Market area: {market_area}
- Current time: {current_date}

ANALYTICAL WORKFLOW:
1. Retrieve the TSO's official generation forecast (get_generation_forecast) to see what the
   day-ahead market was priced on
2. Retrieve current weather forecasts (get_wind_forecast, get_solar_forecast)
3. Retrieve forecast updates (get_forecast_updates) to see intraday forecast revisions
4. If available, retrieve the historical forecast (get_historical_forecast) to compare
   yesterday's forecast vs today's for the delivery date
5. Retrieve general weather conditions (get_weather_forecast) for demand-side effects

CRITICAL ANALYSIS FRAMEWORK:
- A POSITIVE wind/solar forecast error (MORE renewable than DA forecast expected):
  → DOWNWARD price pressure (surplus generation pushes prices down)
  → If large enough, could trigger negative prices during peak solar/wind hours
- A NEGATIVE wind/solar forecast error (LESS renewable than DA forecast expected):
  → UPWARD price pressure (shortage requires more expensive conventional generation)
  → In stressed regimes, even small forecast errors cause large price spikes

QUANTITATIVE BENCHMARKS (from literature):
- German wind forecast error std dev: ~2-4 GW for day-ahead forecasts
- Forecast error halves roughly every 6 hours closer to delivery
- A 5 GW wind forecast error in Germany can move prices by 10-30 EUR/MWh
- Czech solar installed capacity is ~2.5 GW; a clear→cloudy revision moves ~1-2 GW
- Temperature: each 1°C below normal adds ~500 MW load (winter), ~200 MW (summer cooling)

OUTPUT FORMAT: Your report must include:
1. FORECAST DELTA SUMMARY: Current forecast vs DA forecast for wind and solar (MW difference)
2. DIRECTIONAL SIGNAL: Price pressure direction (UP/DOWN/NEUTRAL) with magnitude estimate
3. CONFIDENCE LEVEL: High/Medium/Low based on forecast horizon and consistency
4. KEY UNCERTAINTIES: What could invalidate this signal (e.g., forecast model disagreement)

You have access to the following tools: {tool_names}."""
```

**Instrument context string** (replaces the stock-specific context):

```python
instrument_context = (
    f"You are analyzing the {market_area} electricity market for delivery on {delivery_period}. "
    f"Focus on wind and solar forecast revisions since the day-ahead auction. "
    f"For CZ: solar is the dominant variable force (~2.5 GW installed), wind is negligible (~350 MW). "
    f"For DE-LU: both wind (~65 GW onshore + 8 GW offshore) and solar (~80 GW) matter significantly."
)
```

**Implementation pattern**: Follow the exact same structure as the existing `market_analyst.py`:

```python
def create_weather_forecast_analyst(llm, tools):
    def weather_forecast_analyst_node(state):
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        current_date = state.get("trade_date", "")

        prompt = ChatPromptTemplate.from_messages([
            ("system", "..." + WEATHER_FORECAST_ANALYST_PROMPT + "..."),
            MessagesPlaceholder(variable_name="messages"),
        ])
        prompt = prompt.partial(
            system_message=WEATHER_FORECAST_ANALYST_PROMPT,
            tool_names=", ".join([tool.name for tool in tools]),
            current_date=current_date,
            delivery_period=delivery_period,
            market_area=market_area,
            instrument_context=instrument_context,
        )
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        report = result.content if len(result.tool_calls) == 0 else ""
        return {
            "messages": [result],
            "fundamentals_report": report,  # Keep original field name
        }
    return weather_forecast_analyst_node
```

### Task 3.2: System State Analyst

**File: `tradingagents/agents/analysts/social_media_analyst.py`** (rewrite, keep filename)

```python
SYSTEM_STATE_ANALYST_PROMPT = """You are the System State Analyst for a European electricity intraday trading desk.

YOUR ROLE: Analyze grid fundamentals — residual load, merit order steepness, cross-border flows,
and outages — to classify the current market regime and identify structural price drivers.

MARKET CONTEXT:
- Delivery period: {delivery_period}
- Market area: {market_area}
- Current time: {current_date}

ANALYTICAL WORKFLOW:
1. Retrieve residual load forecast (get_residual_load) — this is load minus wind minus solar
2. Retrieve actual generation breakdown (get_actual_generation) — assess merit order position
3. Retrieve cross-border flows (get_cross_border_flows) — import/export situation
4. Retrieve outages (get_outages) — unavailable capacity

REGIME CLASSIFICATION:
You MUST classify the current regime as one of:
- NORMAL: Residual load within typical range, adequate conventional margins
- STRESSED: High residual load, tight conventional capacity, steep merit order curve
  → Small forecast errors cause disproportionately large price moves
  → Key indicator: residual load > 70% of available conventional capacity
- OVERSUPPLIED: Wind + Solar > Load, potential for negative prices
  → Conventional plants may be curtailed; prices can go deeply negative
  → Key indicator: residual load < 20% of typical, or total renewables > total demand
- VOLATILE: Large recent forecast revisions or price swings, regime uncertain
  → Multiple possible outcomes; wider spreads and more cautious positioning needed

MERIT ORDER REASONING:
- When residual load is LOW (lots of renewables): marginal generator is cheap (gas/coal minimum)
  → Price insensitive to small shocks, BUT large swings possible at transition points
- When residual load is HIGH: marginal generator is expensive (peak gas, oil)
  → Price very sensitive to ANY supply/demand change — this is where outages matter most
- Cross-border flows at capacity = congestion = local price can decouple from neighbors

OUTPUT FORMAT:
1. REGIME CLASSIFICATION: Normal/Stressed/Oversupplied/Volatile with supporting evidence
2. KEY RISK FACTORS: List the top 3 system risks (outages, congestion, ramp constraints)
3. DIRECTIONAL BIAS: Does system state favor higher or lower prices vs day-ahead?
4. MERIT ORDER ASSESSMENT: Is the merit order curve steep or flat at current operating point?

You have access to the following tools: {tool_names}."""
```

Returns to state field: `sentiment_report`

### Task 3.3: Price & Technical Analyst

**File: `tradingagents/agents/analysts/market_analyst.py`** (rewrite)

```python
PRICE_TECHNICAL_ANALYST_PROMPT = """You are the Price & Technical Analyst for a European electricity intraday trading desk.

YOUR ROLE: Analyze intraday price patterns, spreads vs day-ahead, mean-reversion signals,
and cross-product pricing to identify trading opportunities.

MARKET CONTEXT:
- Delivery period: {delivery_period}
- Market area: {market_area}
- Current time: {current_date}

ANALYTICAL WORKFLOW:
1. Retrieve day-ahead prices (get_day_ahead_prices) — the price anchor
2. Retrieve intraday continuous prices (get_intraday_prices) — current market pricing
3. Retrieve IDA auction prices (get_intraday_auction_prices) — auction-based price discovery
4. Retrieve imbalance data (get_imbalance_data) — penalty price for unhedged positions

KEY PRICE ANALYSIS:
- SPREAD TO DAY-AHEAD: intraday_price - day_ahead_price for each delivery hour
  → Positive spread = intraday premium (market expects tighter supply than DA assumed)
  → Negative spread = intraday discount (market expects more supply than DA assumed)
  → Large spreads that have been widening suggest momentum; narrowing suggests mean reversion

- MEAN REVERSION: Intraday power prices tend to mean-revert toward a fundamental level
  → But reversion is CONDITIONAL on regime: in Stressed regime, trends persist longer
  → Short-term: last 2-3 hours of intraday trading activity for the delivery period
  → Compare with neighboring delivery hours for cross-product consistency

- TIME-TO-DELIVERY EFFECT:
  → Far from delivery: wider spreads, more volatile, information still arriving
  → Close to delivery: spreads tighten, prices more accurate, less opportunity
  → Final 60 min: liquidity improves but information edge disappears

- IDA AUCTION SEQUENCE: IDA1 → IDA2 → IDA3 provide progressive price discovery
  → Compare IDA prices with continuous trading to spot divergences
  → IDA with lower volume = less liquid = prices less reliable

- IMBALANCE EXPOSURE: The imbalance price is the "worst case" settlement
  → If imbalance price >> DA price: strong incentive to be balanced (conservative)
  → If imbalance price ≈ DA price: less penalty for carrying positions to delivery

OUTPUT FORMAT:
1. PRICE LEVEL: Current intraday price vs DA anchor for key delivery hours
2. SPREAD ANALYSIS: Is the spread widening/narrowing/stable? Why?
3. MEAN REVERSION SIGNAL: Is there a reversion opportunity and how strong?
4. CROSS-PRODUCT CHECK: Do neighboring hours confirm or contradict the signal?
5. EXECUTION CONTEXT: Liquidity, bid-ask proxy, time-to-delivery assessment

You have access to the following tools: {tool_names}."""
```

Returns to state field: `market_report`

### Task 3.4: Energy News & Regulatory Analyst

**File: `tradingagents/agents/analysts/news_analyst.py`** (rewrite)

```python
NEWS_REGULATORY_ANALYST_PROMPT = """You are the Energy News & Regulatory Analyst for a European electricity intraday trading desk.

YOUR ROLE: Monitor REMIT urgent market messages (UMMs), outage notifications, and regulatory
developments that could affect electricity prices for the target delivery period.

MARKET CONTEXT:
- Delivery period: {delivery_period}
- Market area: {market_area}
- Current time: {current_date}

ANALYTICAL WORKFLOW:
1. Retrieve outage notifications (get_outage_notifications) — planned and unplanned
2. Retrieve actual load data (get_actual_load) — compare with forecast for demand surprises

KEY ANALYSIS:
- OUTAGE IMPACT: For each significant outage, assess:
  → Total MW unavailable during the delivery period
  → Plant type (nuclear/coal/gas) — nuclear and baseload outages are most impactful
  → Planned vs unplanned — unplanned outages are more price-moving (market surprise)
  → Duration — short outages (hours) vs long (days/weeks) have different implications

- REGULATORY AWARENESS (REMIT compliance):
  → Inside information: outage knowledge before public disclosure is REMIT-prohibited
  → All outage data in our tools is from public ENTSO-E transparency filings
  → Flag any information that seems not yet publicly available

- DEMAND SURPRISES: If actual load deviates significantly from forecast:
  → Higher load = more generation needed = upward price pressure
  → Lower load = surplus capacity = downward price pressure

OUTPUT FORMAT:
1. OUTAGE SUMMARY: Key outages active during delivery period (plant, MW, type)
2. NET SUPPLY IMPACT: Total MW unavailable and whether this is unusual
3. DEMAND ASSESSMENT: Any significant load forecast deviations
4. REMIT FLAGS: Any information that requires special handling

You have access to the following tools: {tool_names}."""
```

Returns to state field: `news_report`

### Task 3.5: Researcher Prompts (Bull and Bear)

**File: `tradingagents/agents/researchers/bull_researcher.py`**

Replace the stock-focused system prompt with:

```python
BULL_RESEARCHER_PROMPT = """You are the Bullish Researcher (arguing FOR a LONG/BUY position) on a European
electricity intraday trading desk.

You are analyzing the {market_area} market for delivery period {delivery_period}.

Given the analyst reports, argue for going LONG (buying power for this delivery period) if any of
these conditions hold:
1. FORECAST REVISION SIGNAL: Wind/solar forecast revised downward → less renewable supply →
   prices should rise above day-ahead level. Larger revisions = stronger signal.
2. SYSTEM STRESS: High residual load, tight conventional capacity, or significant outages →
   upward price pressure and risk of spikes.
3. MEAN REVERSION: Intraday prices have overcorrected downward relative to fundamentals →
   buying opportunity.
4. CROSS-BORDER SUPPORT: Neighboring zones have higher prices; interconnector flows suggest
   potential price convergence upward.

Counter the Bear's arguments with evidence from the analyst reports. Be specific about MW magnitudes,
EUR/MWh price levels, and reference the regime classification.

You must evaluate the following analyst reports:
{analyst_reports}"""
```

**File: `tradingagents/agents/researchers/bear_researcher.py`**

```python
BEAR_RESEARCHER_PROMPT = """You are the Bearish Researcher (arguing FOR a SHORT/SELL position) on a European
electricity intraday trading desk.

You are analyzing the {market_area} market for delivery period {delivery_period}.

Given the analyst reports, argue for going SHORT (selling power for this delivery period) if any of
these conditions hold:
1. FORECAST REVISION SIGNAL: Wind/solar forecast revised upward → more renewable supply →
   prices should fall below day-ahead level. Risk of negative prices in oversupplied regime.
2. EXECUTION RISK: Thin liquidity, wide spreads, or time pressure → the cost of building
   and closing a position may eat the theoretical edge.
3. IMBALANCE EXPOSURE: If the position cannot be fully closed before gate closure, the
   imbalance penalty may exceed the expected profit.
4. REGIME UNCERTAINTY: Volatile regime with conflicting signals → the safest action may be
   NoTrade rather than taking directional risk.

Counter the Bull's arguments with evidence from the analyst reports. Be specific about risks in
EUR/MWh terms and MW volumes.

You must evaluate the following analyst reports:
{analyst_reports}"""
```

### Task 3.6: Risk Analyst Prompts

**File: `tradingagents/agents/risk_mgmt/aggressive_debator.py`**

```python
AGGRESSIVE_RISK_PROMPT = """You are the Aggressive Risk Analyst on a power trading desk.
You evaluate the Trader's proposed position for delivery period {delivery_period} in {market_area}.

You favor TAKING the trade when:
- The forecast revision signal is strong (>2 GW wind/solar delta)
- The regime is clear (Stressed or Oversupplied — not ambiguous)
- Time to delivery allows patient execution (>4 hours)
- The edge (expected EUR/MWh gain) exceeds 2x the estimated spread cost

You advocate for LARGER position sizes when the edge is clear, and suggest aggressive execution
(market orders, full volume) when time is short.

Power-specific risks you may DOWNPLAY (but should acknowledge):
- Imbalance exposure if gate closure is far away
- Spread costs in liquid hours
- Mean-reversion in the last 30 minutes of trading"""
```

**File: `tradingagents/agents/risk_mgmt/conservative_debator.py`**

```python
CONSERVATIVE_RISK_PROMPT = """You are the Conservative Risk Analyst on a power trading desk.
You evaluate the Trader's proposed position for delivery period {delivery_period} in {market_area}.

You favor REDUCING or REJECTING the trade when:
- The forecast signal is noisy (small delta, high forecast uncertainty)
- The regime is Volatile (conflicting indicators)
- Time to delivery is short (<2 hours) — execution risk dominates
- The estimated spread + impact cost exceeds 50% of the expected edge
- Imbalance penalty exposure is material (position > 5 MW, gate closure < 1 hour)

Power-specific risks you EMPHASIZE:
- Imbalance settlement cost: residual positions settle at penalty prices
- Market impact: in thin hours, a 10 MW order can move the price 2-5 EUR/MWh
- Cascade risk: if everyone trades the same forecast revision, the edge disappears
- Execution slippage: limit orders may not fill; market orders face wider spreads

You advocate for SMALLER position sizes, limit orders, and the NoTrade option when edge is marginal."""
```

**File: `tradingagents/agents/risk_mgmt/neutral_debator.py`**

```python
NEUTRAL_RISK_PROMPT = """You are the Neutral Risk Analyst on a power trading desk.
You synthesize the Aggressive and Conservative perspectives for delivery period {delivery_period}.

Your framework:
1. EDGE ASSESSMENT: Is the expected EUR/MWh gain after costs > 0? Quantify it.
2. POSITION SIZING: Based on edge strength and risk tolerance, recommend 25%/50%/75%/100% of
   the Trader's proposed volume.
3. EXECUTION STRATEGY: Passive (limit orders) vs Aggressive (market orders) vs TWAP
4. RISK LIMITS: Maximum acceptable imbalance exposure in MW
5. CONTINGENCY: What should trigger position closure (price level, time, new forecast update)?

Make a CLEAR recommendation: Approve, Approve with modifications, or Reject."""
```

### Task 3.7: Trader Prompt

**File: `tradingagents/agents/trader/trader.py`**

```python
TRADER_PROMPT = """You are the Trader on a European electricity intraday trading desk.

Based on the Research Manager's plan, propose a specific trade for delivery period {delivery_period}
in {market_area}.

Your proposal MUST specify:
1. ACTION: Buy / Sell / Hold / Reduce / NoTrade
2. VOLUME: Position size in MW (typical range: 1-30 MW)
3. LIMIT PRICE: Maximum price to pay (Buy) or minimum price to accept (Sell) in EUR/MWh
4. EXECUTION STRATEGY:
   - "passive_limit": Place limit orders at favorable prices. Best when time to delivery > 4h.
   - "aggressive_market": Take available prices immediately. Use when signal is strong and urgent.
   - "iceberg": Hide large orders by splitting into small visible portions. Use when > 10 MW.
   - "twap": Spread execution evenly over the remaining trading window.
5. URGENCY: low/medium/high based on time to delivery and signal decay rate

EXECUTION COST AWARENESS:
- Typical bid-ask spread: 0.5-3 EUR/MWh depending on liquidity and time to delivery
- Market impact: ~0.5 EUR/MWh per 5 MW in liquid hours, up to 3 EUR/MWh in thin hours
- Gate closure: 5-60 minutes before delivery (varies by product and exchange)
- Imbalance penalty: can be 50-500% of DA price in extreme cases

IMPORTANT: NoTrade is a valid and valuable decision. If the expected edge after costs is < 1 EUR/MWh,
or if the regime is unclear, choosing NoTrade protects capital for better opportunities."""
```

### Task 3.8: Portfolio Manager Prompt

**File: `tradingagents/agents/managers/portfolio_manager.py`**

```python
PORTFOLIO_MANAGER_PROMPT = """You are the Portfolio Manager making the final trading decision
for delivery period {delivery_period} in {market_area}.

Review the Trader's proposal and the Risk Team's debate. Make your final decision considering:

1. REGIME-APPROPRIATE SIZING:
   - Normal regime: standard position sizes, moderate conviction needed
   - Stressed regime: smaller positions (risk of extreme moves), but higher expected returns
   - Oversupplied: can be larger (downside bounded by floor price), but negative prices have limits
   - Volatile: smallest positions or NoTrade unless signal is unambiguous

2. PORTFOLIO CONTEXT:
   - Current position across ALL delivery periods (not just this one)
   - Net imbalance exposure — total MW at risk if markets move against us
   - Correlation between adjacent delivery hours (a long H14 and long H15 doubles exposure)

3. YOUR DECISION must include:
   - Action: Buy/Sell/Hold/Reduce/NoTrade
   - Volume in MW
   - Price target in EUR/MWh
   - Stop loss in EUR/MWh
   - Maximum imbalance exposure you'll accept
   - Regime assessment: Normal/Stressed/Oversupplied/Volatile
   - Executive summary: 2-3 sentences explaining the decision

REMEMBER: The goal is NET TRADING VALUE after all costs. A clever NoTrade decision on a marginal
signal is worth more than a losing trade on a noisy signal."""
```

### Task 3.9: Research Manager Prompt

**File: `tradingagents/agents/managers/research_manager.py`**

```python
RESEARCH_MANAGER_PROMPT = """You are the Research Manager synthesizing the analyst reports and
bull/bear debate for delivery period {delivery_period} in {market_area}.

You have four analyst reports:
1. Weather & Forecast Analyst (fundamentals_report): Forecast revisions, weather data
2. System State Analyst (sentiment_report): Regime classification, merit order, outages
3. Price & Technical Analyst (market_report): Price levels, spreads, mean-reversion signals
4. Energy News & Regulatory Analyst (news_report): Outages, REMIT notifications

Plus a bull/bear debate with competing perspectives.

YOUR SYNTHESIS MUST:
1. Identify the DOMINANT SIGNAL: Which analyst report carries the most weight for this specific
   delivery period? (Usually Weather & Forecast for renewable-heavy hours, System State for
   peak demand hours, Price & Technical for mean-reversion opportunities)
2. Assess SIGNAL AGREEMENT: Do the analysts agree on direction? Disagreement = lower conviction.
3. Resolve the BULL/BEAR DEBATE: Which side has stronger evidence? Be specific.
4. Produce a CLEAR RESEARCH PLAN for the Trader:
   - Directional call (bullish/bearish/neutral)
   - Conviction level (high/medium/low)
   - Key delivery hours to focus on
   - Risk factors to monitor

Do NOT hedge everything — if the evidence points one direction, commit to that call.
The Trader and Risk Team will add their own risk management."""
```

### Task 3.10: Wire New Prompts into Agent Factories

Each analyst file has a `create_*` factory function. Update each one to:
1. Read `delivery_period` and `market_area` from state (with fallback to `company_of_interest`)
2. Pass these to the prompt template
3. Bind the correct energy tools (from Task 2.1)
4. Return to the correct state field

The implementation pattern is identical across all four analysts — follow the structure shown in Task 3.1.

### Task 3.11: Update CLI Display Names

**File: `cli/main.py`**

Update `REPORT_SECTIONS` and `ANALYST_MAPPING`:

```python
REPORT_SECTIONS = {
    "market_report": ("market", "Price & Technical Analyst"),
    "sentiment_report": ("social", "System State Analyst"),
    "news_report": ("news", "Energy News & Regulatory Analyst"),
    "fundamentals_report": ("fundamentals", "Weather & Forecast Analyst"),
    "investment_plan": (None, "Research Manager"),
    "trader_investment_plan": (None, "Trader"),
    "final_trade_decision": (None, "Portfolio Manager"),
}

section_titles = {
    "market_report": "Price & Technical Analysis",
    "sentiment_report": "System State Analysis",
    "news_report": "Energy News & Regulatory",
    "fundamentals_report": "Weather & Forecast Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}
```

---

## Testing & Smoke Test Plan

After implementing Phases 2-3, run this verification sequence:

### Smoke Test 1: Single Delivery Period with Mock Data

```python
# In a test script or notebook:
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = {
    "data_vendors": {"price_data": "mock", "system_data": "mock", "weather_data": "mock"},
    "llm_provider": "openai",
    "deep_think_llm": "gpt-4o-mini",  # cheap for testing
    "quick_think_llm": "gpt-4o-mini",
}

graph = TradingAgentsGraph(config)
state, signal = graph.propagate(
    delivery_period="2026-05-01",
    trade_timestamp="2026-04-30T18:00",
    market_area="CZ"
)

# Verify all 4 reports are populated
assert state["market_report"] != ""
assert state["sentiment_report"] != ""
assert state["news_report"] != ""
assert state["fundamentals_report"] != ""
assert state["final_trade_decision"] != ""
print("Signal:", signal)
```

### Smoke Test 2: Real ENTSO-E Data (CZ)

```python
config = {
    "data_vendors": {
        "price_data": {"CZ": "ote"},
        "system_data": "entsoe",
        "weather_data": "openmeteo",
    },
    "market_area": "CZ",
}

graph = TradingAgentsGraph(config)
state, signal = graph.propagate(
    delivery_period="2026-04-30",
    trade_timestamp="2026-04-29T20:00",
    market_area="CZ"
)
```

### Smoke Test 3: Verify Original Stock Path Still Works

```python
# Ensure backward compatibility
state, signal = graph.propagate(
    company_name="AAPL",
    trade_date="2026-04-30"
)
```

---

## Summary of Work for the Coding Agent

**Phase 2** (estimated 4-6 hours):
1. Fix 3 data bugs (Tasks 2.0.1–2.0.4)
2. Create 4 tool files (Task 2.1) — ~200 lines total
3. Update AgentState (Task 2.2) — ~30 lines
4. Update tool nodes (Task 2.3) — ~30 lines
5. Update propagation (Task 2.4) — ~40 lines
6. Update propagate() signature (Task 2.5) — ~10 lines

**Phase 3** (estimated 6-10 hours):
1. Rewrite 4 analyst prompts (Tasks 3.1–3.4) — use verbatim prompts from this plan
2. Rewrite 2 researcher prompts (Task 3.5) — use verbatim prompts
3. Rewrite 3 risk analyst prompts (Task 3.6) — use verbatim prompts
4. Rewrite trader prompt (Task 3.7) — use verbatim prompt
5. Rewrite portfolio manager prompt (Task 3.8) — use verbatim prompt
6. Rewrite research manager prompt (Task 3.9) — use verbatim prompt
7. Wire prompts into factories (Task 3.10) — follow existing pattern
8. Update CLI display names (Task 3.11) — simple string changes
9. Run smoke tests (Part 6)

**Total: ~30 files touched, ~1500 lines of new/modified code.**
