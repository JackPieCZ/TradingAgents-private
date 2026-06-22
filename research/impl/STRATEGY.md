# STRATEGY.md — TradingAgents Energy Markets Fork: Implementation Plan

## Executive Summary

This plan converts TradingAgents from a US equity trading framework into a European electricity intraday trading system. The adaptation is not a superficial re-skin — power markets differ fundamentally from equity markets in price formation (forecast-driven, not order-flow-driven), time structure (sequential linked venues with delivery periods), risk profile (joint price-volume-imbalance exposure), and constraints (physical grid/plant feasibility). The plan is organized into 13 phases, each with specific actionable steps an AI coding agent can execute independently.

**Target markets**: German EPEX Spot (primary, best data availability), Czech OTE (secondary), via XBID/SIDC coupling.
**Target products**: Hourly and quarter-hourly intraday continuous + intraday auctions.
**Trading horizon**: Intraday, from day-ahead gate closure to delivery.

---

## Phase 0: Pre-Implementation Research & Context Gathering ✅ COMPLETE

**Status**: All research, data access, and context gathering is done. Proceed directly to Phase 1.

### 0.1 Papers — all 27 papers in context ✅

All papers listed in the original plan are now in the project knowledge base, including the three that were originally missing:
- **Féron, Tankov & Tinsi (2020)** — `Féron__Tankov___Tinsi__2020__intraday_price_formation_and_optimal_trading.md`
- **Martin & Otterson (2018)** — `martin2018_intradayOrderBook.md`
- **Balardy (2022)** — `BalardyEmpiricalAnalysisBidask2022_OCR.pdf`

**Tip for AI agents**: When implementing any specific phase below, re-read the papers listed in that phase's references before writing code. The papers contain specific variable definitions, model specifications, and parameter ranges that should be reflected in the implementation.

### 0.2 Data access — resolved ✅

**Data strategy chosen: Option A+C (zero-cost MVP)**

| Source | What it provides | Access method | Status |
|--------|-----------------|---------------|--------|
| **ENTSO-E** | DA prices, generation forecasts, actual generation, load, cross-border flows, outages, imbalance data (DE, CZ, all EU) | REST API via `entsoe-py` | ✅ API key obtained. Docs: [Sitemap for Restful API](https://transparencyplatform.zendesk.com/hc/en-us/articles/15692855254548-Sitemap-for-Restful-API-Integration) |
| **OTE (Czech)** | DA market results, intraday continuous prices/volumes, IDA auction results, imbalance settlement | SOAP API (free, no key) + JSON endpoint | ✅ Available. See details below |
| **SMARD** | German generation by type, load, residual load (hourly + quarter-hourly) | REST API (free, no key) | ✅ Available |
| **Open-Meteo** | Wind speed (10m/80m/120m), solar radiation, temperature — historical + forecasts + "historical forecast" for backtesting | REST API (free, no key) | ✅ Available |
| **EPEX Spot tick data** | Full trade-by-trade intraday continuous data | Paid subscription (EEX Webshop) | ❌ Deferred — upgrade later if system shows promise |

**OTE data access details** (critical for CZ market):
1. **SOAP API** — `http://www.ote-cr.cz/services/PublicDataService` (WSDL at `/wsdl`). No authentication required. Key electricity services:
   - `GetDamPriceE` — Day-ahead hourly prices and volumes
   - `GetImPriceE` — Intraday continuous market VWAP, min/max, volumes (per day)
   - `GetImPricePeriodE` — Intraday continuous prices per 15-min period (PT15M resolution)
   - `GetIDAPriceE` — IDA auction results (hourly)
   - `GetIDAPricePeriodE` — IDA auction results per period (with Auction field: IDA1/IDA2/IDA3)
   - `GetImbalanceSettlementE` — Hourly imbalance settlement (Version: 0=daily, 1=monthly, 2=final)
   - Parameters are always `StartDate`/`EndDate` (YYYY-MM-DD), optionally `StartHour`/`EndHour` or `StartPeriod`/`EndPeriod`
   - Full documentation: `uzivatelskymanual_webove_sluzby_ote_g.pdf` in project knowledge
2. **JSON endpoint** (undocumented but functional) — `https://www.ote-cr.cz/pw-data/chart-data/01?language=en` (redirected from `/cs/kratkodobe-trhy/elektrina/denni-trh/@@chart-data`). Returns chart-ready JSON. Useful for quick prototyping but SOAP is more reliable for production.
3. **Legacy Python library** — `python-ote` (https://github.com/dankeder/python-ote) — last commit 4 years ago, may need updating but shows the SOAP call patterns.

### 0.3 Dependencies installed ✅

In the `tradingagents` conda environment:
- `entsoe-py` — ENTSO-E API client
- `openmeteo-requests` — Open-Meteo client
- `requests-cache` — HTTP caching for API calls
- `retry-requests` — Retry logic for unreliable endpoints

**epftoolbox note**: The repo is cloned into `epftoolbox-master/` in the project root but is **NOT installed** as a package. It requires Python ≤3.13 and the conda env runs 3.13.13 which triggers `ERROR: Package 'epftoolbox' requires a different Python: 3.13.13 not in '<=3.13,>=3.9'`. **Use it as reference code only** — import individual functions/modules by path if needed, do not `pip install` it.

### 0.4 Example output format ✅

See `complete_report.md` for the full output structure of the original TradingAgents system (SPY analysis). The energy fork should produce the same structural flow but with power-market content: analyst reports → bull/bear debate → research manager synthesis → trader proposal → risk debate → portfolio manager decision.

---

## Phase 1: Data Layer — Replace Stock Data with Energy Market Data ✅ COMPLETE

**Goal**: Build a new `dataflows/` backend that provides energy market data through the same vendor-routing interface.

**Status**: All 8 files implemented and tested with live API data (ENTSO-E, OTE, SMARD, Open-Meteo). See `phase1_review_and_phase2_3_plan.md` for detailed review.

**Known issues to fix in Phase 2**:
1. ENTSO-E CZ imbalance prices returned in CZK, labeled as EUR — needs CZK→EUR conversion
2. SMARD filter_id 410 shared by generation_total and total_load — compute total from individual sources
3. SMARD load forecast filter (123) returns wrong metric — needs correct filter ID or fallback to ENTSO-E
4. `_load_or_fetch` duplicated across all 4 clients — consolidate to `cache_layer.cached_fetch()`

**Key data insight for Phase 3 prompt design**: CZ wind data from ENTSO-E is often zero (Czech installed wind is ~350 MW — negligible). The Weather & Forecast Analyst should focus on solar for CZ and wind+solar for DE-LU. Open-Meteo Historical Forecast API provides forecast revision deltas critical for the Kup22 strategy.

**References to read first**: Kup22 (Section 2: data description), Kie17 (Section 3: data), Kre21b (Section 2: data and variables), Hir22 (Section 3: data)

**Data strategy**: Option A+C — ENTSO-E for fundamentals/forecasts/system data (DE + CZ), OTE SOAP for Czech intraday/DA/imbalance data, SMARD for German generation detail, Open-Meteo for weather. Zero-cost stack.

### 1.1 Create new data vendor modules ✅

**Files to create**:
- `tradingagents/dataflows/entsoe_client.py` — ENTSO-E Transparency Platform data (via `entsoe-py`). Key methods: `query_day_ahead_prices`, `query_wind_and_solar_forecast`, `query_intraday_wind_and_solar_forecast` (forecast deltas = alpha signal per Kup22), `query_generation`, `query_load`/`query_load_forecast`, `query_crossborder_flows`, `query_unavailability_of_generation_units`, `query_imbalance_prices`
- `tradingagents/dataflows/ote_client.py` — OTE SOAP client for Czech market. Endpoint: `http://www.ote-cr.cz/services/PublicDataService`. Implement calls to: `GetDamPriceE`, `GetImPriceE`, `GetImPricePeriodE`, `GetIDAPriceE`, `GetIDAPricePeriodE`, `GetImbalanceSettlementE`. Use `zeep` or raw `requests` for SOAP. Reference `uzivatelskymanual_webove_sluzby_ote_g.pdf` for exact XML schemas.
- `tradingagents/dataflows/smard_client.py` — SMARD API for German generation/load details. Simple GET requests, no auth.
- `tradingagents/dataflows/weather_client.py` — Open-Meteo for wind/solar/temperature. Use `openmeteo-requests` with `requests-cache` and `retry-requests`. Key: the "Historical Forecast" API allows reconstructing what the forecast was at a past date — critical for backtesting forecast revision strategies.
- `tradingagents/dataflows/energy_utils.py` — Shared utilities: timezone handling (CET/CEST), delivery period parsing, caching, data alignment

**Files to modify**:
- `tradingagents/dataflows/interface.py` — Add new vendor entries and tool categories

### 1.2 Define new tool categories and methods ✅

Replace the stock-oriented categories in `interface.py` with energy-market categories:

```python
TOOLS_CATEGORIES = {
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
                  "get_forecast_updates"]  # forecast DELTAS are the key signal [Kup22]
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

### 1.3 Implement each data retrieval function ✅

Each function should:
- Accept `delivery_period` (ISO datetime of delivery start), `market_area` (e.g., "DE-LU", "CZ"), and relevant parameters
- Return a formatted string (matching the original pattern — agents consume string tool outputs)
- Handle caching to `data_cache_dir` to avoid redundant API calls during backtesting
- Gracefully handle missing data periods

**Critical data feeds** (from the playbook and papers):
1. **Day-ahead auction results** — hourly/quarter-hourly prices and volumes per bidding zone [ENTSO-E or EPEX]
2. **Intraday continuous trade data** — VWAP prices, volumes, min/max per period [OTE SOAP `GetImPricePeriodE` for CZ; ENTSO-E intraday auctions + SMARD indices for DE]
3. **Intraday auction results** — IDAs (ID1, ID2, ID3) clearing prices [EPEX/ENTSO-E]
4. **Wind power forecast + actuals + updates** — total and per-TSO area; **forecast deltas** are the primary signal [Kup22, Kie17]
5. **Solar PV forecast + actuals + updates** — same structure as wind [Kie17, Kre21b]
6. **Load forecast + actuals** — to compute residual load [Kie17]
7. **Conventional generation by type** — for merit order slope estimation [Kre21b]
8. **Cross-border physical flows and NTC** — for coupling effects [Kri20, Kat19]
9. **Outage data (REMIT UMMs)** — planned and unplanned outages [Hie20]
10. **Balancing state / ACE signal** — for imbalance exposure estimation [Nar22, Bro22]

**Tip for AI agents**: The `entsoe-py` library wraps the ENTSO-E API nicely and is already installed. For weather, `openmeteo-requests` is installed with caching. For OTE Czech data, use the SOAP API directly — the WSDL at `http://www.ote-cr.cz/services/PublicDataService/wsdl` defines all available methods. Use `zeep` (install it) or raw XML POST requests. The OTE manual (`uzivatelskymanual_webove_sluzby_ote_g.pdf`) has full XML request/response examples for every service. For SMARD, it's simple REST GETs — check the `de-smard` package or build a thin client. You'll need to map weather station locations to TSO areas for aggregation. Check `Kup22` Section 3 for exactly which renewable forecast update variables they use.

### 1.4 Implement a data caching and fallback layer ✅

Since we have free access to all primary data sources (ENTSO-E, OTE, SMARD, Open-Meteo), create:
- `tradingagents/dataflows/cache_layer.py` — SQLite or parquet-based local cache to avoid re-fetching during backtesting. Key: cache by (source, query_type, market_area, date_range) tuple.
- `tradingagents/dataflows/mock_energy.py` — generates realistic synthetic energy data for unit testing and development when API access is unavailable (e.g., sandbox without network). Calibrate from cached real data.
- Include realistic features: negative prices, spikes, seasonal patterns, weekend effects, delivery-period autocorrelation

### 1.5 Update default_config.py ✅

```python
# Add to DEFAULT_CONFIG:
"market_area": "DE-LU",              # Primary bidding zone ("DE-LU" or "CZ")
"delivery_resolution": "60min",       # "60min" or "15min"
"trading_horizon": "intraday",        # "day_ahead" | "intraday" | "both"
"entsoe_api_key": None,              # Set via env var ENTSOE_API_KEY (key obtained)
"weather_provider": "open_meteo",
"data_vendors": {
    "price_data": {
        "DE-LU": "entsoe",           # ENTSO-E for German DA/intraday auction prices
        "CZ": "ote",                 # OTE SOAP for Czech DA + intraday prices
    },
    "system_data": "entsoe",          # Generation, load, cross-border flows, outages
    "weather_data": "open_meteo",     # Wind, solar, temperature
    "market_fundamentals": {
        "DE-LU": "smard",            # SMARD for detailed German generation breakdown
        "CZ": "entsoe",              # ENTSO-E for Czech fundamentals
    },
    "news_data": "entsoe",           # REMIT UMMs via ENTSO-E
},
# OTE-specific config
"ote_soap_url": "http://www.ote-cr.cz/services/PublicDataService",
# SMARD config
"smard_base_url": "https://www.smard.de/app/chart_data",
```

---

## Phase 2: Redefine Agent Roles and State Schema ✅ COMPLETE (with known bugs)

**Goal**: Redesign the agent team from equity-focused to power-market-focused.

**Status**: All tool files, AgentState, tool nodes, propagation, and propagate() signature implemented. Known bugs to fix in Phase 5:
1. **CRITICAL**: `propagation.py` `RiskDebateState` initialized with wrong field names (`agg_history`, `con_history` instead of `aggressive_history`, `conservative_history`, etc.) — will crash at runtime
2. **MODERATE**: All 4 analyst prompt templates include literal `"..."` strings and `instrument_context` is computed but never injected into the template
3. Phase 1 known data bugs (CZK→EUR, SMARD filter_id, load forecast) still not fixed

**References**: Playbook Section "Best approaches for the transition", Kup22, Kie17, Kre21b, Hir22

### 2.1 Redesign the analyst team

Replace the four stock analysts with power-market-appropriate roles:

| Original Agent | New Agent | Rationale |
|---------------|-----------|-----------|
| Market Analyst (technical indicators) | **Price & Technical Analyst** | Analyzes intraday price patterns, spreads, mean-reversion signals, neighboring contract prices. References: Kre21b (autoregressive terms, cross-contract features), Ser22 (path forecasts) |
| Social Media Analyst | **System State Analyst** | Analyzes grid fundamentals: residual load, merit order steepness, cross-border flows, outages. This is the biggest conceptual shift — social sentiment is irrelevant in power; system state IS the sentiment. References: Kie17 (demand-quote regime), Kre21b (merit order slope), Kri20 (cross-border) |
| News Analyst | **Energy News & Regulatory Analyst** | Energy-specific news, REMIT notifications, outage announcements, policy changes. References: Hie20 (REMIT), playbook compliance section |
| Fundamentals Analyst | **Weather & Forecast Analyst** | THE most important new role. Analyzes renewable forecasts, forecast updates/deltas, weather data. Forecast revisions are the primary alpha source. References: Kup22 (core strategy), Kie17 (forecast error effects), Hir22 (fundamental drivers of distribution) |

**Files to modify**:
- `tradingagents/agents/analysts/` — rewrite all four analyst modules
- `tradingagents/agents/__init__.py` — update exports

### 2.2 Update AgentState

**File**: `tradingagents/agents/utils/agent_states.py`

```python
class AgentState(MessagesState):
    # Core identifiers — delivery_period replaces company_of_interest
    delivery_period: Annotated[str, "Delivery period start (ISO datetime)"]
    market_area: Annotated[str, "Bidding zone (e.g., DE-LU, CZ)"]
    trade_date: Annotated[str, "Current trading timestamp"]

    sender: Annotated[str, "Agent that sent this message"]

    # Analyst reports — renamed for power market
    price_technical_report: Annotated[str, "Report from Price & Technical Analyst"]
    system_state_report: Annotated[str, "Report from System State Analyst"]
    news_regulatory_report: Annotated[str, "Report from Energy News & Regulatory Analyst"]
    weather_forecast_report: Annotated[str, "Report from Weather & Forecast Analyst"]

    # Debate states (reusable as-is from original)
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

### 2.3 Update tool definitions

**Files to create/modify** in `tradingagents/agents/utils/`:
- `energy_price_tools.py` — replaces `core_stock_tools.py`
- `system_data_tools.py` — replaces `fundamental_data_tools.py`
- `weather_tools.py` — new, most important tool set
- `energy_news_tools.py` — replaces `news_data_tools.py`
- `energy_indicators_tools.py` — replaces `technical_indicators_tools.py` (power-specific: rolling mean, volatility, spread to DA, time-to-delivery features)

### 2.4 Update tool nodes in trading_graph.py

**File**: `tradingagents/graph/trading_graph.py`, method `_create_tool_nodes()`

Map new analysts to their tools:
```python
self.tool_nodes = {
    "price_technical": ToolNode([get_intraday_prices, get_price_spreads, get_power_indicators]),
    "system_state": ToolNode([get_residual_load, get_merit_order_proxy, get_cross_border_flows, get_outages]),
    "news_regulatory": ToolNode([get_energy_news, get_remit_messages, get_outage_notifications]),
    "weather_forecast": ToolNode([get_wind_forecast, get_solar_forecast, get_forecast_updates, get_weather_forecast]),
}
```

---

## Phase 3: Rewrite Agent Prompts ✅ COMPLETE

**Goal**: Replace stock-trading prompts with power-market-expert prompts.

**Status**: All prompts rewritten with deep domain expertise. Weather & Forecast, System State, Price & Technical, Energy News & Regulatory analysts all have power-specific analytical workflows. Bull/Bear researchers, risk analysts, Trader, PM, and Research Manager all updated. CLI display names updated. Prompt quality is high — includes specific MW magnitudes, EUR/MWh benchmarks, regime classification frameworks, and REMIT compliance awareness.

**References**: Read ALL analyst papers again before writing prompts. Each prompt should encode domain expertise from the literature.

### 3.1 Weather & Forecast Analyst prompt

This is the most important analyst. The prompt should instruct the agent to:
- Retrieve the latest wind and solar forecasts and compare to earlier forecasts (compute deltas)
- Assess forecast confidence and typical error magnitudes
- Identify whether forecast updates imply a surplus or shortage relative to the day-ahead schedule
- Flag large forecast revisions that could move intraday prices significantly
- Consider time-to-delivery: closer to delivery = more accurate forecasts = smaller but more reliable signals [Kup22]
- Output: forecast delta summary, directional implication (upward/downward price pressure), confidence level

**Tip for AI agents**: Look at the `market_analyst.py` prompt structure as a template. The system message should list the exact tools available and describe the analytical workflow. Include specific instructions like: "Compare the current renewable forecast to the day-ahead-used forecast. A positive wind forecast error (more wind than expected) implies downward price pressure. Assess the magnitude relative to typical daily variation."

### 3.2 System State Analyst prompt

Should instruct the agent to:
- Retrieve current residual load (load minus wind minus solar) and compare to day-ahead forecast
- Assess merit order steepness — when conventional capacity is tight, the same forecast shock has much larger price impact [Kie17, Kre21b]
- Check for significant outages (planned or unplanned)
- Assess cross-border flow situation and available interconnector capacity
- Classify the current regime: normal / stressed / oversupplied
- Output: regime classification, key risk factors, directional bias from system state

### 3.3 Price & Technical Analyst prompt

Should instruct the agent to:
- Retrieve recent intraday prices for the target delivery period and neighboring periods
- Calculate spread vs day-ahead price (the "intraday premium/discount")
- Assess recent price trend and mean-reversion potential [Kre21b]
- Check neighboring delivery period prices for cross-product signals [Hir23]
- Note time-to-delivery and its effect on expected volatility [Kat20, Hir22]
- Output: current price level, trend, spread to DA, cross-product signals, volatility assessment

### 3.4 Energy News & Regulatory Analyst prompt

Should instruct the agent to:
- Retrieve recent energy market news and REMIT urgent market messages (UMMs)
- Identify any new outage announcements or availability changes
- Check for regulatory or policy developments affecting the market
- Flag any information that could constitute inside information under REMIT [Hie20]
- Output: relevant news summary, REMIT flags, outage impact assessment

### 3.5 Update researcher and risk analyst prompts

The bull/bear researchers and risk analysts need power-market context in their prompts:
- Bull researcher should argue for positions based on forecast edge, favorable regime, execution opportunity
- Bear researcher should argue based on execution risk, thin liquidity, imbalance exposure, regime uncertainty
- Risk analysts should debate considering spread costs, market impact, imbalance penalty exposure, time-to-delivery risk [Nar21, Bun18]

**Files to modify**: `bull_researcher.py`, `bear_researcher.py`, `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`

### 3.6 Update Trader and Portfolio Manager prompts

- **Trader**: Should reason about execution strategy (passive vs aggressive), position sizing relative to typical delivery-period liquidity, and time-to-delivery urgency [Kat20]
- **Portfolio Manager**: Should consider portfolio-level exposure across delivery periods, net imbalance risk, and overall risk limits

**Files to modify**: `trader/trader.py`, `managers/portfolio_manager.py`, `managers/research_manager.py`

---

## Phase 4: Update Schemas and Decision Outputs ← NEXT

**Goal**: Adapt structured output schemas for power market decisions.

**Status**: NOT STARTED. Current schemas still use equity PortfolioRating (Buy/Overweight/Hold/Underweight/Sell) and TraderAction (Buy/Hold/Sell). Prompts already ask for power-specific outputs (volume_mw, execution_strategy, regime_assessment) but schemas can't capture them. See `phase4_5_implementation_plan.md` for detailed instructions.

**File**: `tradingagents/agents/schemas.py`

### 4.1 Redesign the rating/action enums

```python
class PowerTradingAction(str, Enum):
    """Trading action for a delivery period."""
    BUY = "Buy"          # Go long / increase long position
    SELL = "Sell"         # Go short / increase short position
    HOLD = "Hold"         # Maintain current position
    REDUCE = "Reduce"     # Reduce existing position (either direction)
    NO_TRADE = "NoTrade"  # Explicitly choose not to trade (distinct from Hold)

class MarketRegime(str, Enum):
    """Current market regime classification."""
    NORMAL = "Normal"
    STRESSED = "Stressed"          # Tight conventional capacity, steep merit order
    OVERSUPPLIED = "Oversupplied"  # Excess renewable, potential negative prices
    VOLATILE = "Volatile"          # High uncertainty, frequent forecast revisions
```

### 4.2 Redesign the TraderProposal for power

```python
class PowerTraderProposal(BaseModel):
    action: PowerTradingAction
    reasoning: str
    volume_mw: Optional[float] = None         # Position size in MW
    limit_price_eur: Optional[float] = None    # Limit price in EUR/MWh
    execution_strategy: Optional[str] = None   # "passive_limit" | "aggressive_market" | "iceberg" | "twap"
    urgency: Optional[str] = None              # "low" | "medium" | "high" — function of time-to-delivery
    delivery_period: Optional[str] = None
```

### 4.3 Redesign the PortfolioDecision for power

```python
class PowerPortfolioDecision(BaseModel):
    action: PowerTradingAction
    executive_summary: str
    regime_assessment: MarketRegime
    volume_mw: Optional[float] = None
    price_target_eur: Optional[float] = None
    stop_loss_eur: Optional[float] = None
    max_imbalance_exposure_mw: Optional[float] = None
    time_horizon: Optional[str] = None         # e.g., "until gate closure" or "next 2 hours"
```

---

## Phase 5: Update the Graph Orchestration ← NEXT (partially done)

**Goal**: Wire the new agents into the LangGraph pipeline.

**Status**: PARTIALLY DONE. Tool nodes and propagate() signature already updated in Phase 2. Remaining work: clean up `_run_graph` naming, replace `_fetch_returns` (still uses yfinance/SPY), update `reflection.py` (still "Alpha vs SPY"), update `_log_state` to include power fields, fix critical bug in `propagation.py`. See `phase4_5_implementation_plan.md` for detailed instructions.

**Files to modify**: `tradingagents/graph/setup.py`, `tradingagents/graph/trading_graph.py`, `tradingagents/graph/propagation.py`, `tradingagents/graph/conditional_logic.py`

### 5.1 Update GraphSetup.setup_graph()

Replace analyst names:
- `"market"` → `"price_technical"`
- `"social"` → `"system_state"`
- `"news"` → `"news_regulatory"`
- `"fundamentals"` → `"weather_forecast"`

Update the `selected_analysts` default and all references.

### 5.2 Update Propagator.create_initial_state()

Add power-specific initial state fields: `delivery_period`, `market_area`, `day_ahead_position`, `residual_position`, `regime_indicator`.

### 5.3 Update TradingAgentsGraph.propagate()

Change the method signature from `propagate(company_name, trade_date)` to `propagate(delivery_period, trade_timestamp, market_area="DE-LU")`.

### 5.4 Update reflection and benchmarking

**File**: `tradingagents/graph/reflection.py`

Replace equity-based reflection (alpha vs SPY) with power-market reflection:
- Compare decision against realized intraday price at delivery
- Compare against day-ahead price (was intraday trading value-additive?)
- Assess whether the regime classification was correct
- Evaluate execution cost estimate vs realized

### 5.5 Update _fetch_returns in trading_graph.py

Replace yfinance price fetching with energy price fetching for the delivery period. The "return" concept changes: instead of stock return, measure the **realized P&L** of the recommended trade (entry price vs settlement price, net of estimated spread/impact).

---

## Phase 6: Implement Power-Specific Technical Indicators

**Goal**: Replace stock technical indicators with power-market-appropriate features.

**References**: Kre21b (feature set), Kie17 (features), Kup22 (forecast features), Hir22 (distribution features)

**File to create**: `tradingagents/dataflows/power_indicators.py`

### 6.1 Price-based indicators

- **Spread to day-ahead**: `intraday_price - day_ahead_price` for the delivery period [core signal]
- **Rolling mean reversion**: Short-term deviation from rolling average of recent intraday trades [Kre21b]
- **Cross-product spread**: Price difference between adjacent delivery periods (H vs H+1, QH vs QH+1) [Hir23]
- **Intraday volatility**: Rolling standard deviation of transaction prices within the trading session [Hir22]
- **Time-to-delivery price curve**: How the intraday price has evolved as delivery approaches [Kat20]
- **Bid-ask spread proxy**: Difference between last buy and last sell transaction prices

### 6.2 Fundamental indicators

- **Residual load delta**: Current residual load forecast minus day-ahead residual load forecast [Kie17]
- **Wind forecast error**: Current wind forecast minus day-ahead wind forecast (MW) [Kup22, Kie17]
- **Solar forecast error**: Same for solar [Kie17]
- **Merit order steepness proxy**: Ratio of residual load to available conventional capacity [Kre21b]
- **System imbalance proxy**: Recent ACE/frequency data or balancing energy activation [Nar22]

### 6.3 Regime indicators

- **Demand-quote regime**: Binary/categorical based on conventional capacity utilization [Kie17]
- **Spike probability**: Based on residual load level and historical spike frequency [Jon05]
- **Negative price probability**: Based on wind+solar forecast vs load [Sch11]

---

## Phase 7: Build the Backtesting Framework

**Goal**: Create a professional, reproducible backtesting system for energy trading.

**This is critical for iterative improvement.** The original TradingAgents only has a simple loop in `main.py`. We need a proper framework.

### 7.1 Create the backtesting engine

**File to create**: `tradingagents/backtesting/engine.py`

```python
class EnergyBacktestEngine:
    """
    Runs TradingAgentsGraph over a sequence of delivery periods,
    tracks positions, simulates execution, and calculates P&L.
    """
    def __init__(self, config, start_date, end_date, market_area="DE-LU",
                 delivery_resolution="60min", initial_capital_eur=1_000_000):
        ...

    def run(self):
        """Iterate over delivery periods, call the agent graph, simulate trades."""
        for delivery_period in self._generate_delivery_periods():
            for trading_timestamp in self._generate_trading_windows(delivery_period):
                state, signal = self.graph.propagate(
                    delivery_period, trading_timestamp, self.market_area
                )
                self._simulate_execution(signal, delivery_period, trading_timestamp)
                self._update_positions()
                self._log_step(delivery_period, trading_timestamp, state, signal)

    def _simulate_execution(self, signal, delivery_period, timestamp):
        """Model execution with spread, impact, and partial fill."""
        # Model from Kat20: execution quality depends on order size,
        # time-to-delivery, and current book depth
        ...

    def _calculate_settlement(self, delivery_period):
        """Calculate realized P&L at delivery including imbalance costs."""
        # Any residual position at gate closure settles at imbalance price [Nar22]
        ...
```

### 7.2 Create performance metrics module

**File to create**: `tradingagents/backtesting/metrics.py`

Power-trading-specific metrics (NOT just equity metrics):

1. **Net Trading Value (NTV)**: Total P&L after spread, impact, and imbalance costs — THE primary metric [Ser22, Kat18, Bun18]
2. **Gross vs Net P&L**: Shows how much execution costs eat into alpha
3. **Hit Rate**: Fraction of delivery periods where the directional call was correct
4. **Average P&L per MWh traded**: Profitability normalized by volume
5. **Imbalance cost**: Total cost from positions not closed before gate closure [Nar22]
6. **Sharpe Ratio**: Annualized, but computed on hourly/daily NTV (not equity-style)
7. **Maximum Drawdown**: On cumulative NTV
8. **Win/Loss ratio**: Average winning trade size vs average losing trade size
9. **Regime-conditional performance**: Separate metrics for normal/stressed/oversupplied regimes
10. **Forecast value-add**: Compare agent decisions vs simple day-ahead hold strategy
11. **Selective trading ratio**: Fraction of periods where the system chose NoTrade — "saying no is a feature" [Bun18]

### 7.3 Create execution simulation module

**File to create**: `tradingagents/backtesting/execution_sim.py`

Model realistic execution costs:
- **Spread cost**: Based on historical bid-ask spread for the delivery period and time-to-delivery [Kat20, Kup21]
- **Market impact**: Price impact proportional to order size relative to typical volume [Nar21]
- **Partial fill probability**: Based on order book depth estimates
- **Slippage**: Random component calibrated to historical execution data

**Tip for AI agents**: Kat20 provides specific execution cost models. Kup21 compares auction vs continuous costs. Use these as calibration references. A simple starting model: spread_cost = base_spread * (1 + order_size / median_volume) with base_spread calibrated from historical data.

### 7.4 Create reporting module

**File to create**: `tradingagents/backtesting/reporting.py`

Generate after each backtest run:
- Summary statistics table (all metrics from 7.2)
- Cumulative NTV chart over time
- Regime-conditional performance breakdown
- Per-delivery-period P&L heatmap (hour-of-day vs day-of-week)
- Agent decision log with all analyst reports preserved for debugging
- Execution quality analysis (intended vs realized prices)

### 7.5 Create comparison framework

**File to create**: `tradingagents/backtesting/baselines.py`

Implement baseline strategies for benchmarking:
1. **Day-ahead hold**: Do nothing, settle at imbalance price (this should be the worst baseline)
2. **Naive forecast follower**: Trade in the direction of the latest forecast update, no agent debate
3. **Simple mean reversion**: Buy below DA, sell above DA, with fixed threshold
4. **TWAP execution**: Time-weighted average execution across the trading window
5. **Random agent**: Random Buy/Sell/Hold with same frequency as the agent system (sanity check)

---

## Phase 8: Implement Regime Detection

**Goal**: Build the regime classification layer that conditions all agent analysis.

**References**: Kie17 (demand-quote threshold), Kre21b (merit order slope), Jon05 (spike regimes), Sch11 (negative price regimes)

**File to create**: `tradingagents/analytics/regime.py`

### 8.1 Implement regime classifiers

```python
class PowerMarketRegime:
    """Classifies current market regime based on system state."""

    def classify(self, residual_load_mw, available_conventional_mw,
                 wind_forecast_mw, solar_forecast_mw, recent_prices) -> MarketRegime:
        """
        Rules based on literature:
        - Stressed: residual_load / available_conventional > threshold [Kie17 demand-quote]
        - Oversupplied: wind + solar > load (potential negative prices) [Sch11]
        - Volatile: large recent forecast revisions or price swings [Jon05]
        - Normal: otherwise
        """
        ...

    def estimate_merit_order_slope(self, residual_load_mw, generation_by_type) -> float:
        """Proxy for merit order steepness [Kre21b]."""
        ...
```

### 8.2 Integrate regime into agent state

The regime classification should be computed before the analyst pipeline runs and injected into the initial state, so all agents have access to it. Modify `Propagator.create_initial_state()`.

---

## Phase 9: Implement the Iterative Improvement Loop

**Goal**: Use backtest results to systematically improve agent performance.

### 9.1 Automated prompt tuning cycle

1. Run backtest over a calibration period (e.g., 3 months of historical data)
2. Analyze regime-conditional performance: identify which regimes the agents handle poorly
3. Examine the agent logs for those underperforming periods
4. Generate prompt refinement suggestions (this can be done by an LLM analyzing the logs)
5. Apply prompt changes and re-run backtest
6. Compare metrics; keep changes that improve NTV and Sharpe

**File to create**: `tradingagents/optimization/prompt_tuner.py`

### 9.2 Hyperparameter search

Parameters to tune:
- `max_debate_rounds`: More rounds may help in ambiguous regimes but cost more LLM calls
- `max_risk_discuss_rounds`: Same trade-off
- Regime thresholds (demand-quote cutoffs, spike probability thresholds)
- Execution parameters (spread assumptions, impact coefficients)
- Which analysts to include (test with/without certain analysts to measure their contribution)

### 9.3 Feature importance analysis

For each delivery period in the backtest:
- Record which analyst reports the Research Manager cited in its rationale
- Record which features the Weather & Forecast Analyst highlighted
- Correlate with P&L outcomes
- Prune features/analysts that don't contribute

### 9.4 Walk-forward validation

Implement proper walk-forward validation:
1. Train/calibrate on Period 1 (e.g., months 1-3)
2. Test on Period 2 (month 4)
3. Re-calibrate including Period 2 data
4. Test on Period 3 (month 5)
5. ... continue rolling forward

This prevents overfitting to a single backtest period. It's especially important because power markets have strong seasonal patterns (summer vs winter, high-wind vs low-wind periods).

---

## Phase 10: Add Physical Constraints and Asset-Backed Trading (Optional Advanced)

**Goal**: Support trading with physical assets (batteries, flexible generation).

**References**: Aid15, Ber20, Gla20

### 10.1 Add asset models

**File to create**: `tradingagents/assets/battery.py`
```python
class BatteryAsset:
    capacity_mwh: float
    max_charge_mw: float
    max_discharge_mw: float
    round_trip_efficiency: float
    current_soc: float  # State of charge
    ramp_rate_mw_per_min: float

    def feasible_actions(self, time_to_delivery_min) -> list:
        """Return feasible charge/discharge actions given current state."""
        ...
```

### 10.2 Inject constraints into Trader prompt

The Trader agent's prompt should include the asset's current state and feasibility constraints, so it doesn't propose infeasible trades.

---

## Phase 11: Testing Strategy

### 11.1 Unit tests
- Test each data tool returns valid formatted output for known date ranges
- Test regime classifier with known system states
- Test execution simulator produces reasonable costs
- Test metric calculations against hand-computed examples

### 11.2 Integration tests
- Run the full pipeline for a single delivery period with mock data and verify state flows correctly
- Test that agent prompts produce valid structured outputs
- Test that the backtest engine handles missing data gracefully

### 11.3 Smoke tests
- Run a short backtest (1 week) with real ENTSO-E data to verify end-to-end functionality
- Verify no look-ahead bias: agent at time T only sees data available before T

---

## Phase 12: Documentation and Packaging

### 12.1 Update README.md
- New project description focused on energy trading
- Installation instructions with energy-specific dependencies (entsoe-py, etc.)
- Quick start guide for running a backtest
- Example output interpretation

### 12.2 Configuration guide
- Document all new config options
- Provide example configs for different setups (German market, Czech market, with/without assets)

### 12.3 Agent customization guide
- How to modify analyst prompts for different market areas
- How to add new data sources
- How to add new analyst roles

---

## Phase 13: Deployment Considerations

### 13.1 Cost management
The original paper notes 11 LLM calls and 20+ tool calls per daily prediction. With potentially hundreds of delivery periods per day, costs could be enormous. Mitigations:
- Use cheaper models (`quick_think_llm`) for analysts; reserve expensive models for Research Manager and Portfolio Manager only
- Cache analyst reports that haven't changed significantly between trading windows
- Batch delivery periods with similar characteristics (same regime, similar forecast updates)
- Implement a "significance filter": only run the full pipeline when forecast updates exceed a threshold

### 13.2 Latency
Power intraday markets move faster than daily stock decisions. The full agent pipeline may take minutes. Options:
- Pre-compute analyst reports on a schedule; only re-run when triggers fire (large forecast revision, outage)
- Run agents for multiple delivery periods in parallel
- Use streaming for the Research Manager and Portfolio Manager so traders see reasoning in real-time

---

## Appendix A: External Resources — Status

### APIs and Libraries ✅
1. **entsoe-py** — ✅ Installed in conda env. API key obtained.
2. **Open-Meteo Python client** — ✅ `openmeteo-requests` installed with `requests-cache` and `retry-requests`
3. **OTE SOAP API** — ✅ Free, no key needed. WSDL at `http://www.ote-cr.cz/services/PublicDataService/wsdl`. Full docs in project knowledge (`uzivatelskymanual_webove_sluzby_ote_g.pdf`).
4. **SMARD API** — ✅ Free, no key. Simple REST GET.
5. **EPEX Spot tick data** — ❌ Deferred (paid). Not needed for MVP.
6. **epftoolbox** — ⚠️ Cloned to `epftoolbox-master/` but NOT installable (Python version mismatch). Use as reference code only.

### Papers ✅ All in context
All 27 papers including Féron et al. (2020), Martin & Otterson (2018), and Balardy (2022).

### Domains needed for sandbox network allowlist
- `transparency.entsoe.eu` — ENTSO-E API
- `api.open-meteo.com` — weather data
- `www.smard.de` — SMARD API
- `www.ote-cr.cz` — OTE SOAP + JSON endpoints
- Standard PyPI/npm domains for package installs

---

## Appendix B: Implementation Priority Order

For a minimum viable product (MVP), implement in this order:

1. **Phase 1.1-1.3** (data layer) — without data, nothing works
2. **Phase 2.1-2.3** (agent roles and state) — core architecture change
3. **Phase 3** (prompts) — this is where the domain expertise lives
4. **Phase 4** (schemas) — structured outputs
5. **Phase 5** (graph wiring) — connect everything
6. **Phase 7.1-7.2** (basic backtesting + metrics) — need to measure results
7. **Phase 6** (power indicators) — enrich agent inputs
8. **Phase 7.3-7.5** (execution sim + baselines) — more realistic evaluation
9. **Phase 8** (regime detection) — conditional performance
10. **Phase 9** (iterative improvement) — refine based on results
11. **Phase 11** (testing) — should be interleaved throughout, but formalize here
12. **Phase 10** (asset-backed) — advanced extension
13. **Phase 12-13** (docs, deployment) — polish

---

## Appendix C: Key Differences Cheat Sheet for AI Agents

When modifying any file, keep these mental substitutions in mind:

| Stock Trading Concept | Power Trading Equivalent |
|----------------------|-------------------------|
| Ticker symbol (AAPL) | Delivery period + market area (2024-06-15T14:00 DE-LU) |
| Stock price (OHLCV) | Intraday continuous trade prices for a delivery period |
| Company fundamentals | Grid system state (residual load, generation mix, outages) |
| Earnings reports | Renewable forecast updates and forecast revisions |
| Social media sentiment | Weather forecasts and forecast deltas (this IS the sentiment) |
| P/E ratio, market cap | Merit order slope, residual load ratio, available flexibility |
| Insider transactions | REMIT urgent market messages, outage notifications |
| Daily Buy/Hold/Sell | Per-delivery-period position signal (may trade same product multiple times) |
| Alpha vs S&P 500 | Net trading value vs day-ahead settlement |
| Transaction cost | Spread + market impact + imbalance settlement cost |
| Market hours | Continuous trading from DA auction to gate closure (typically 5-60 min before delivery) |
| Earnings season | Seasonal patterns: winter demand peaks, summer solar peaks, wind seasonality |
| Black swan events | Grid emergencies, sudden outages, extreme weather, negative price episodes |

---

## Appendix D: Implementation Workflow — How to Use Your Three Coding Tools

You have three AI coding tools with different strengths and cost profiles. Here is how to allocate work optimally across them to implement this strategy.

### Tool Profiles

| Tool | Strengths | Weaknesses | Best for |
|------|-----------|------------|----------|
| **VS Code + GitHub Copilot Pro** | Always available, inline completions, good at boilerplate, understands repo context via open files | Weaker at large architectural reasoning, can't read project knowledge papers | Boilerplate code, repetitive patterns, small edits, test writing, fixing lint errors |
| **Opencode (open models + Gemini)** | Free/cheap, good for bulk generation, long context with Gemini | Less reliable on complex domain logic, may hallucinate energy market specifics | Scaffolding, file generation, data parsing code, utility functions, documentation |
| **Claude Code (Pro, usage-limited)** | Best domain reasoning, can read project knowledge papers, best at complex architecture decisions | Limited usage — must be conserved | Architecture decisions, prompt engineering, complex domain logic, code review, debugging hard issues |

### Implementation Sequence with Tool Allocation

**Phase 1: Data Layer** (start here)

1. **Claude Code** — Read STRATEGY.md Phase 1 + relevant papers (Kup22 data section, OTE manual). Design the `dataflows/` module architecture: class interfaces, method signatures, caching strategy, error handling patterns. Output: skeleton files with docstrings, type hints, and clear TODOs. (~1 session)

2. **Opencode/Gemini** — Implement the ENTSO-E client (`entsoe_client.py`). This is largely wrapping `entsoe-py` calls with caching and error handling. Give it the skeleton from step 1 + the entsoe-py docs. Repeat for `weather_client.py` (wrapping `openmeteo-requests`) and `smard_client.py` (simple REST GETs).

3. **Opencode/Gemini** — Implement the OTE SOAP client (`ote_client.py`). Give it the SOAP examples from the OTE manual. This is XML parsing work — bulk generatable.

4. **Copilot** — Fill in `energy_utils.py` (timezone handling, delivery period parsing, data alignment). These are small, well-defined utility functions. Also write unit tests for all data clients using cached/mock responses.

5. **Copilot** — Update `interface.py` vendor routing and `default_config.py`. These are mechanical edits with clear patterns from the existing code.

6. **Claude Code** — Review the complete data layer. Check for: correct timezone handling (CET/CEST transitions), proper caching semantics, no look-ahead bias in backtesting mode, correct API parameter construction. (~1 short session)

**Phase 2-3: Agent Roles + Prompts** (this is where domain expertise matters most)

7. **Claude Code** — This is the highest-value use of Claude Code. Design all four analyst prompts (Weather & Forecast, System State, Price & Technical, Energy News & Regulatory). Read the relevant papers for each analyst before writing. Also redesign the bull/bear researcher prompts, risk analyst prompts, and trader/portfolio manager prompts for power markets. Output: complete prompt text for all agents. (~2 sessions, the most important sessions)

8. **Copilot** — Mechanical refactoring: rename files, update imports, wire new agent names into the graph. Follow the exact mappings in Phase 5 of STRATEGY.md.

9. **Opencode/Gemini** — Implement `agent_states.py` updates, new tool files (`energy_price_tools.py`, `system_data_tools.py`, `weather_tools.py`, `energy_news_tools.py`), and `schemas.py` updates. Give it the skeleton from Claude Code's prompt design session.

**Phase 4-5: Schemas + Graph Wiring**

10. **Copilot** — Update schemas.py with PowerTradingAction, MarketRegime, PowerTraderProposal, PowerPortfolioDecision. These are Pydantic models — Copilot excels here.

11. **Copilot** — Wire the graph: update `setup.py`, `trading_graph.py`, `propagation.py`, `conditional_logic.py`. Follow the exact mappings in STRATEGY.md Phase 5. This is mechanical find-and-replace plus adding new state fields.

**Phase 6: Power Indicators**

12. **Opencode/Gemini** — Implement `power_indicators.py`. The indicator formulas are spelled out in STRATEGY.md Phase 6. This is straightforward numerical computation.

**Phase 7: Backtesting**

13. **Opencode/Gemini** — Scaffold `backtesting/engine.py`, `metrics.py`, `execution_sim.py`, `reporting.py`, `baselines.py`. The structure is well-defined in STRATEGY.md Phase 7.

14. **Claude Code** — Review execution simulation logic (market impact, spread modeling). This needs domain expertise from Kat20, Kup21, Nar21. Also review the metrics module to ensure power-market-appropriate evaluation. (~1 session)

15. **Copilot** — Write tests for the backtesting module. Test each metric against hand-computed examples.

**Phase 8+: Regime Detection, Iteration, Advanced**

16. **Claude Code** — Design regime classification logic (referencing Kie17, Kre21b, Jon05, Sch11). This requires understanding the papers' specific threshold definitions. (~1 session)

17. **Opencode/Gemini** — Implement the regime classifier code based on Claude Code's design.

### Budget Allocation Summary

| Tool | Estimated sessions | Phases covered |
|------|--------------------|----------------|
| **Claude Code** | 5-6 sessions | Architecture (P1), prompts (P2-3), data review (P1), execution/metrics review (P7), regime design (P8) |
| **Opencode/Gemini** | ~15 sessions | Data clients (P1), tool implementations (P2), indicators (P6), backtest scaffolding (P7), regime code (P8) |
| **Copilot** | Continuous | Utilities, tests, mechanical refactoring, config updates, graph wiring, schema updates |

### Key Principle

**Use Claude Code for decisions, Opencode for generation, Copilot for completion.** Claude Code sessions should always produce a clear artifact (skeleton, prompt text, design doc, review notes) that the other tools can execute against. Never use Claude Code for work that Copilot can handle (boilerplate, imports, test scaffolding).

### Practical Tips

- Before each Claude Code session, prepare the context: which STRATEGY.md phase, which papers to reference, what specific output you need
- After Claude Code produces prompts or architecture, immediately commit them — they're the hardest part to reproduce
- Opencode/Gemini works best when given: (a) the skeleton/interface from Claude Code, (b) specific examples of the input/output format, (c) reference to existing code patterns in the repo
- Copilot works best when you have one file open with the pattern and are writing a parallel file — it will autocomplete the pattern
- Run tests frequently — `pytest` after each tool's contribution to catch integration issues early
