# Implementation Plan: TradingAgents Energy Fork — Post-Phase 5 Audit & Next Steps

**Generated**: 2026-05-04 — Full codebase review of `JackPieCZ/TradingAgents-private`

---

## Part I: Critical Bugs Found (Must Fix Before Anything Else)

### BUG-1: Research Manager Never Sees Analyst Reports [CRITICAL — Signal Loss]

**File**: `tradingagents/agents/managers/research_manager.py`, `create_research_manager()` (line 67–135)

**Problem**: The Research Manager's prompt *mentions* four analyst reports but **never injects them**. The prompt says "You have four analyst reports: 1. Weather & Forecast Analyst (fundamentals_report)..." but the f-string only interpolates `{history}` (the bull/bear debate history) and `{delivery_period}`, `{market_area}`. The actual state fields `state["market_report"]`, `state["sentiment_report"]`, `state["news_report"]`, `state["fundamentals_report"]` are **never read** by this agent.

**Impact**: The Research Manager's synthesis is based entirely on the bull/bear debate summaries. It cannot verify whether the debaters accurately represented the analyst findings. This is one of the most valuable agents in the pipeline — it's supposed to identify the DOMINANT SIGNAL and check for PERSISTENCE TRAP — but it's working blind.

**Fix**: Add the four reports to the prompt:
```python
prompt = f"""
...
ANALYST REPORTS:
--- Price & Technical Analyst ---
{state["market_report"]}

--- System State Analyst ---
{state["sentiment_report"]}

--- Energy News & Regulatory Analyst ---
{state["news_report"]}

--- Weather & Forecast Analyst ---
{state["fundamentals_report"]}

BULL/BEAR DEBATE HISTORY:
{history}
"""
```

### BUG-2: Trader Only Sees Research Manager's Plan — No Analyst Reports [CRITICAL — Signal Loss]

**File**: `tradingagents/agents/trader/trader.py`, `create_trader()` (line 64–133)

**Problem**: The Trader receives only `state["investment_plan"]` (the Research Manager's output). It has zero access to the four analyst reports. Since the Research Manager itself doesn't see the reports (BUG-1), the Trader is now TWO degrees removed from the actual data.

**Impact**: The Trader is asked to specify volume in MW, limit prices in EUR/MWh, and execution strategy — but it has never seen the actual price data, outage data, or forecast numbers. It's guessing based on a summary of a summary.

**Fix**: Inject the four analyst reports into the Trader's user message alongside the investment plan. At minimum, inject the Price & Technical report (for price levels) and the System State report (for regime).

### BUG-3: Portfolio Manager Only Sees Risk Debate — No Analyst Reports [SIGNIFICANT]

**File**: `tradingagents/agents/managers/portfolio_manager.py`, `create_portfolio_manager()` (line 95–188)

**Problem**: The Portfolio Manager receives `{research_plan}`, `{trader_plan}`, and `{history}` (risk debate). No direct access to analyst reports.

**Impact**: Less severe than BUG-1/2 because the risk debaters (Aggressive, Conservative, Neutral) **do** correctly include all four analyst reports in their prompts. So the risk debate history contains analyst data indirectly. But the PM cannot cross-check claims — it must trust the debaters' representations.

**Fix**: Inject at least a brief summary of the four analyst reports, or the full reports if token budget allows.

### BUG-4: `Msg Clear` Wipes ALL Message Context Between Analysts [DESIGN FLAW]

**File**: `tradingagents/agents/utils/agent_utils.py`, `create_msg_delete()` (line 45–58)

**Problem**: After each analyst finishes, `create_msg_delete()` removes ALL messages (including tool call results and the analyst's own output) and replaces them with a single `HumanMessage(content="Continue")`. The next analyst starts with zero message history.

**Impact**: Each analyst only sees the initial system message + "Continue". They cannot learn from what previous analysts discovered. The System State Analyst cannot see the Price & Technical Analyst's findings about price trends, etc. The analyst reports ARE saved as state fields (`market_report`, `sentiment_report`, etc.), but individual analysts don't read those fields — they only see `state["messages"]`.

**Why it exists**: Likely to prevent token budget explosion. As analysts call tools, messages accumulate rapidly (each tool call/response is a message pair). Without clearing, the 4th analyst would see all tool calls from the previous 3 analysts.

**Fix (two options)**:
- **Option A (Minimal)**: Before clearing messages, inject a brief summary of previous analyst reports into the next analyst's system prompt. Add to each analyst's prompt: `"Previous analysts have found: {state['market_report'][:500]}..."` etc.
- **Option B (Better)**: Don't clear messages entirely. Instead, remove tool call/response message pairs but keep the final report messages. This preserves the analytical conclusions without the tool call bloat.
- **Option C (Best)**: Create a `previous_analyst_context` state field that accumulates a short summary from each analyst. Each subsequent analyst reads this field.

### BUG-5: `default_config.py` Routing Errors [MODERATE]

**File**: `tradingagents/default_config.py`

**Problems**:
1. `"get_intraday_auction_prices": "entsoe"` — but ENTSO-E does not support this method (see `VENDOR_METHODS` in interface.py, it's commented out). Only OTE supports IDA prices. Should be `"ote"` or `"ote,entsoe"`.
2. `"get_intraday_prices": "entsoe,ote"` — ENTSO-E `query_intraday_prices` returns a hardcoded stub string ("Intraday prices are currently unavailable..."). First vendor tried is entsoe, which "succeeds" with that stub. The fallback to OTE never triggers because the stub doesn't raise an exception. Should be `"ote,entsoe"` or just `"ote"`.
3. `"get_balancing_data": "entsoe"` — For CZ market, OTE imbalance settlement may be more accurate. Should be `"entsoe,ote"`.
4. `"price_data": "entsoe"` at category level — but for CZ, OTE is the primary source. The tool-level overrides partially fix this, but the intent is unclear.

**Fix**: Reorder vendor priorities to match actual CZ data availability:
```python
"tool_vendors": {
    "get_day_ahead_prices": "entsoe,ote",       # Both work for CZ
    "get_intraday_prices": "ote",                # ENTSOE stub, only OTE has real data
    "get_intraday_auction_prices": "ote",         # Only OTE has IDA data
    "get_balancing_data": "entsoe,ote",           # Both work
    "get_residual_load": "entsoe,smard",
    ...
}
```

### BUG-6: `entsoe_client.query_intraday_prices()` Returns Stub But Doesn't Raise [MODERATE]

**File**: `tradingagents/dataflows/entsoe_client.py`, line 222

**Problem**: The function returns a hardcoded string `"Intraday prices are currently unavailable..."` as its first line, BEFORE the actual `def fetch()` definition. The fetch function is dead code — it's never reached. Because the stub returns a valid string (not an exception), `route_to_vendor` treats it as a successful response and never falls back to OTE.

**Impact**: When `tool_vendors` lists `"entsoe,ote"` for `get_intraday_prices`, agents receive the stub message instead of real OTE data. Looking at the run.log, this was caught: `Vendor 'entsoe' does not support method 'get_intraday_prices'. Skipping.` — but that's only because entsoe isn't in `VENDOR_METHODS` for this key, not because the stub was detected. The actual fallback works by accident.

**Fix**: Either remove the stub and properly implement the entsoe intraday function, or raise `NotImplementedError` so the fallback chain works correctly.

### BUG-7: News Analyst Has Too Few Tools [MODERATE]

**File**: `tradingagents/agents/utils/energy_news_tools.py` — only 2 tools: `get_outage_notifications`, `get_actual_load`

**Problem**: The News analyst's prompt references analyzing REMIT UMMs, demand surprises, and regulatory developments, but it only has 2 tools: outage notifications and actual load. Meanwhile, `get_outages` in system_data_tools.py maps to the **same** entsoe function as `get_outage_notifications` — they're duplicates.

**Impact**: The News analyst is severely under-equipped. It should also have access to cross-border flows (to detect import/export constraints) and possibly day-ahead prices (to compare demand expectations).

**Fix**: Either expand the News analyst's toolkit or merge it with the System State analyst. At minimum, add `get_cross_border_flows` and `get_load_forecast` to the News analyst so it can detect demand surprises.

---

## Part II: Agent Routing & Context Flow Analysis

### Current Graph Flow (from `setup.py`)

```
START
  → Market Analyst (Price & Technical)
    → [tools_market ↔ Market Analyst loop until no more tool calls]
    → Msg Clear Market
  → Social Analyst (System State)
    → [tools_social ↔ Social Analyst loop]
    → Msg Clear Social
  → News Analyst (Energy News & Regulatory)
    → [tools_news ↔ News Analyst loop]
    → Msg Clear News
  → Fundamentals Analyst (Weather & Forecast)
    → [tools_fundamentals ↔ Fundamentals Analyst loop]
    → Msg Clear Fundamentals
  → Bull Researcher ↔ Bear Researcher (debate, max_debate_rounds × 2 turns)
  → Research Manager
  → Trader
  → Aggressive ↔ Conservative ↔ Neutral (risk debate, max_risk_discuss_rounds × 3 turns)
  → Portfolio Manager
→ END
```

### Why the Trader is 3rd of 4 Rounds

The flow is: (1) Analyst Reports → (2) Bull/Bear Debate + Research Manager → (3) Trader → (4) Risk Debate + Portfolio Manager.

This ordering actually makes sense for the original equity framework:
- Analysts gather data → Researchers debate the signal → Research Manager synthesizes → Trader proposes execution → Risk team evaluates → PM decides.

The Trader being in round 3 is correct — it translates the Research Manager's directional call into a concrete execution proposal. The risk team then stress-tests that proposal.

**The real problem is not the ordering — it's the context loss at each transition** (BUGs 1–4 above).

### Context Each Agent Actually Receives (Current State)

| Agent | Analyst Reports? | Previous Agent Outputs? | Messages? |
|-------|-----------------|------------------------|-----------|
| Market Analyst | ❌ (first) | ❌ | Initial message only |
| System State Analyst | ❌ | ❌ | "Continue" only |
| News Analyst | ❌ | ❌ | "Continue" only |
| Weather Analyst | ❌ | ❌ | "Continue" only |
| Bull Researcher | ✅ All 4 reports | ❌ | None (uses state directly) |
| Bear Researcher | ✅ All 4 reports | Bull's arguments | None (uses state directly) |
| Research Manager | ❌ **BUG** | Debate history only | None |
| Trader | ❌ **BUG** | Investment plan only | None |
| Aggressive Debater | ✅ All 4 reports | Trader plan + debate | None |
| Conservative Debater | ✅ All 4 reports | Trader plan + debate | None |
| Neutral Debater | ✅ All 4 reports | Trader plan + debate | None |
| Portfolio Manager | ❌ | Research plan, trader plan, risk debate | None |

### Recommended Context Flow (Fixed)

| Agent | Should Receive |
|-------|---------------|
| Market Analyst | Initial message + tools |
| System State Analyst | Initial message + **Market Analyst summary** + tools |
| News Analyst | Initial message + **Market + System State summaries** + tools |
| Weather Analyst | Initial message + **All previous summaries** + tools |
| Bull Researcher | All 4 reports (✅ already works) |
| Bear Researcher | All 4 reports + Bull arguments (✅ already works) |
| Research Manager | **All 4 reports** + debate history |
| Trader | **All 4 reports** + investment plan |
| Risk Debaters | All 4 reports + trader plan (✅ already works) |
| Portfolio Manager | **All 4 reports** + research plan + trader plan + risk debate |

---

## Part III: Unused Tools & Missing Cross-Referencing

### Tools Implemented in Dataflows But NOT Wired to Any Agent

| Tool Function | In `interface.py`? | In Agent Tools? | Status |
|--------------|-------------------|-----------------|--------|
| `get_intraday_prices_period` (OTE 15-min) | ✅ | ❌ Not in any agent | **Missing** — valuable for granular price analysis |
| `smard_generation` (DE detailed gen) | ✅ | Only via `get_actual_generation` | OK for DE-LU, but routing needs checking |
| `smard_residual_load` (DE residual) | ✅ | Via `get_residual_load` | OK |
| `smard_total_load` (DE load) | ✅ | Via `get_actual_load` | OK |
| `dayahead_market_prices` (SMARD DE) | ✅ | Via `get_day_ahead_prices` | OK |
| `smard_generation_forecast` | ✅ | Via `get_generation_forecast` | OK |
| `smard_load_forecast` | ✅ | Via `get_load_forecast` | OK — but SMARD load forecast filter may be broken (known bug) |
| `mock_*` generators | ✅ | Via fallback | OK for testing |

### Multi-Provider Cross-Referencing (Not Implemented)

STRATEGY.md says: "If there are multiple providers for a similar tool, return the output of all providers so that the agent can cross-reference."

Currently, `route_to_vendor()` tries providers in order and returns the **first successful result**. It does NOT aggregate results from multiple providers.

**Tools with multiple providers that should cross-reference**:
1. `get_day_ahead_prices`: ENTSO-E + OTE + SMARD — all three can provide DA prices for CZ/DE
2. `get_residual_load`: ENTSO-E + SMARD — both can compute residual load for DE
3. `get_actual_generation`: ENTSO-E + SMARD — both have generation breakdown for DE
4. `get_load_forecast`: ENTSO-E + SMARD — both have load forecasts

**Fix**: Create a `route_to_all_vendors()` function that calls ALL available vendors for a method and concatenates their outputs with clear source labels. Use this for critical tools where cross-referencing adds value.

---

## Part IV: Tool Descriptions & Agent Awareness

### Current State

Agents receive tool names via `{tool_names}` in their prompts, which is a comma-separated list of function names. They also see the `@tool` docstrings when the LLM processes tool definitions. However:

1. **Docstrings are brief**: e.g., `get_day_ahead_prices` says "Fetch day-ahead auction clearing prices for a delivery date and bidding zone. Returns hourly prices in EUR/MWh." — this is adequate but doesn't tell the agent what the CSV columns are or how to interpret the data.

2. **Prompts describe tools narratively**: The analyst prompts do a good job of saying "1. Retrieve day-ahead prices (get_day_ahead_prices) — the price anchor" with explanation of what to do with the data. This is actually well-done.

3. **Missing**: Agents don't know what the tool **output format** looks like. They don't know they'll get CSV with specific column names. After BUG-4 fix, subsequent analysts could learn from prior tool outputs — but currently they can't.

### Recommended Enhancement

Add a "TOOL OUTPUT FORMAT" section to each analyst prompt that describes the columns returned by each tool. This helps the LLM parse the data correctly on the first try and avoids wasted tool calls. Example for the Price & Technical Analyst:

```
TOOL OUTPUT FORMATS:
- get_day_ahead_prices → CSV with columns: Hour, Price EUR/MWh, Price EUR/MWh StdDev, Price EUR/MWh Range
- get_intraday_prices → CSV with columns: Hour (CET), Price EUR/MWh, Price EUR/MWh StdDev, Price EUR/MWh Range, Volume MWh
- get_intraday_auction_prices → CSV with columns: Hour (CET), Auction (IDA1/IDA2/IDA3), Price EUR/MWh, ..., Volume MWh, Import MWh, Export MWh, Saldo MWh
- get_imbalance_data → CSV with columns: Hour, Imbalance Volume MW, ..., Imbalance Price EUR/MWh, ...
```

---

## Part V: Specific File-Level Issues

### 5.1 `entsoe_client.py` — Header Formatting (User-Reported `\n\n` Issue)

The entsoe_client uses `\n` for line breaks within headers and `\n\n` for the blank line separating the header from CSV data. This is **correct** for human readability but may look odd in single-line log views (where `\n` renders as literal text). No actual bug here — the output formatting is sound.

However, the **residual load function** (`query_residual_load`) has a subtle issue: it returns a CSV where the "Solar MW" column comes from the generation forecast, but the function is labeled "Residual Load Actual" when using actual load data. The column naming could be clearer.

### 5.2 Report Section Names Still Use Stock Terminology

**File**: `cli/main.py`, `save_report_to_disk()` (line 658–745)

Labels in the complete_report.md use "Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst" instead of the energy-specific names "Price & Technical Analyst", "System State Analyst", "Energy News & Regulatory Analyst", "Weather & Forecast Analyst".

**Fix**: Update the label strings in `save_report_to_disk()`.

### 5.3 `main.py` Not Updated

**File**: `main.py` (root)

Still calls `ta.propagate("NVDA", "2024-05-10")` with stock-market configuration. Should be updated to call with energy parameters.

### 5.4 `_log_state` Path Construction Bug

**File**: `tradingagents/graph/trading_graph.py`, line 490

```python
directory = Path(self.config["results_dir"] + self.ticker + "TradingAgentsStrategy_logs")
```

This concatenates strings without a path separator. With `results_dir="/path/to/logs"` and `ticker="2024-06-15_CZ"`, the path becomes `/path/to/logs2024-06-15_CZTradingAgentsStrategy_logs`. Missing `/` separators.

**Fix**: Use `Path(self.config["results_dir"]) / self.ticker / "TradingAgentsStrategy_logs"` (as `_log_state_exchange` does on line 447).

### 5.5 `yfinance` Import Still Present

**File**: `tradingagents/graph/trading_graph.py`, line 43

```python
import yfinance as yf
```

This is unused (the `_fetch_returns` for energy returns `None, None, None`). Should be removed to eliminate the dependency.

### 5.6 `build_instrument_context()` Returns Stock Language

**File**: `tradingagents/agents/utils/agent_utils.py`, line 37–43

Returns: "The instrument to analyze is `{ticker}`. Use this exact ticker in every tool call..." — This makes no sense for energy markets. Should say "The delivery period to analyze is `{delivery_period}` in market area `{market_area}`."

### 5.7 Old `_exchange` Functions Still Present

Every agent file contains both `create_*_exchange()` (original stock version) and `create_*()` (new energy version). The `_exchange` versions are dead code that imports stock tools (`get_stock_data`, `get_indicators`, `get_news`, etc.). These should be removed to reduce confusion and eliminate unnecessary stock-tool imports.

---

## Part VI: Implementation Plan — Ordered by Impact

### Phase A: Fix Critical Context Flow (Estimated: 1 session)

**Priority**: HIGHEST — This determines whether the entire multi-agent pipeline produces meaningful results.

**A.1** — Fix Research Manager to receive all 4 analyst reports (BUG-1)
- Edit `research_manager.py`: Add `state["market_report"]`, `state["sentiment_report"]`, `state["news_report"]`, `state["fundamentals_report"]` to the prompt

**A.2** — Fix Trader to receive all 4 analyst reports (BUG-2)
- Edit `trader.py`: Add analyst reports to the user message

**A.3** — Fix Portfolio Manager to receive analyst reports (BUG-3)
- Edit `portfolio_manager.py`: Add analyst reports to the prompt

**A.4** — Fix inter-analyst context flow (BUG-4)
- Create a new state field `analyst_context: str` in `AgentState`
- After each analyst produces their report, append a 2–3 sentence summary to `analyst_context`
- Each subsequent analyst reads `analyst_context` from state (not messages)
- Keep `Msg Clear` for token management, but inject `analyst_context` into the system prompt

**A.5** — Fix `default_config.py` vendor routing (BUG-5)
- Reorder `tool_vendors` so OTE is primary for CZ-specific data
- Fix `get_intraday_auction_prices` to use `"ote"` not `"entsoe"`

**A.6** — Fix `entsoe_client.query_intraday_prices()` stub (BUG-6)
- Either implement properly or raise `NotImplementedError`

### Phase B: Clean Up & Harden (Estimated: 1 session)

**B.1** — Remove all `_exchange` dead code from every agent file
- Delete `create_*_exchange()` functions from: `market_analyst.py`, `social_media_analyst.py`, `news_analyst.py`, `fundamentals_analyst.py`, `bull_researcher.py`, `bear_researcher.py`, `research_manager.py`, `portfolio_manager.py`, `trader/trader.py`, `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`
- Delete stock tool imports (`get_stock_data`, `get_indicators`, `get_fundamentals`, `get_news`, etc.) from files that no longer use them

**B.2** — Fix `build_instrument_context()` for energy
- Rewrite to return energy-appropriate context string using `delivery_period` and `market_area`

**B.3** — Fix `_log_state` path construction (5.4)

**B.4** — Remove `import yfinance as yf` from `trading_graph.py` (5.5)

**B.5** — Update report labels in `cli/main.py` (5.2)
- "Market Analyst" → "Price & Technical Analyst"
- "Social Analyst" → "System State Analyst"
- "News Analyst" → "Energy News & Regulatory Analyst"
- "Fundamentals Analyst" → "Weather & Forecast Analyst"

**B.6** — Update `main.py` with energy example
```python
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("2026-05-04", "2026-05-04T14:00", market_area="CZ")
```

### Phase C: Expand Tool Coverage (Estimated: 1 session)

**C.1** — Wire `get_intraday_prices_period` (15-min resolution) to the Price & Technical Analyst
- Add to `energy_price_tools.py`
- Add to `_create_tool_nodes()` and `setup.py`

**C.2** — Expand News Analyst toolkit
- Add `get_cross_border_flows` and `get_load_forecast` to `energy_news_tools.py`
- This lets the News analyst detect demand surprises and import constraints

**C.3** — Add tool output format descriptions to analyst prompts
- For each analyst, add a "TOOL OUTPUT FORMATS" section listing the column names and units for each tool's output

**C.4** — Implement cross-provider aggregation for critical tools
- Create `route_to_all_vendors()` in `interface.py`
- Apply to `get_day_ahead_prices` (ENTSO-E + OTE for CZ) so the agent sees both sources
- Label each output clearly: "## ENTSO-E Data:" and "## OTE Data:"

### Phase D: Implement Phase 6 — Power Indicators (Estimated: 1–2 sessions)

**File to create**: `tradingagents/dataflows/power_indicators.py`

This is called for in STRATEGY.md Phase 6 but hasn't been implemented. These indicators would replace the stock technical indicators (`get_stock_data`, `get_indicators`) that are still referenced in dead code.

**D.1** — Price-based indicators:
- Spread to day-ahead: `intraday_price - day_ahead_price`
- Rolling mean reversion: deviation from rolling average
- Cross-product spread: price difference between adjacent delivery periods
- Intraday volatility: rolling StdDev of transaction prices
- Bid-ask spread proxy

**D.2** — Fundamental indicators:
- Residual load delta: current forecast minus DA forecast
- Wind/Solar forecast error: current minus DA forecast (MW)
- Merit order steepness proxy: residual load / available conventional capacity
- System imbalance proxy

**D.3** — Regime indicators:
- Demand-quote regime binary [Kie17]
- Spike probability based on residual load
- Negative price probability based on wind+solar vs load

**D.4** — Create `energy_indicators_tools.py` in `agents/utils/`
- Wrap the indicator functions as LangChain tools
- Add to the Price & Technical Analyst's toolkit

### Phase E: Implement Phase 7 — Backtesting Framework (Estimated: 2–3 sessions)

This is the most critical missing piece for iterative improvement.

**E.1** — Create `tradingagents/backtesting/engine.py`
- Iterate over delivery periods
- Call agent graph for each
- Track positions and simulate execution

**E.2** — Create `tradingagents/backtesting/execution_sim.py`
- Model spread + market impact based on order size and time-to-delivery
- CZ: wider spreads, ~60x less liquid than DE
- Reference Kat20 for market impact model

**E.3** — Create `tradingagents/backtesting/metrics.py`
- Net Trading Value (profit minus all costs)
- Hit rate (correct direction calls)
- Sharpe ratio of daily P&L
- Maximum drawdown
- Comparison vs day-ahead-only baseline

**E.4** — Create `tradingagents/backtesting/baselines.py`
- Always-DA baseline (never trade intraday)
- Forecast-follower baseline (simple rule: trade on forecast delta sign)
- Random baseline

**E.5** — Implement `_fetch_returns()` in `trading_graph.py`
- Replace the current stub with actual energy price comparison
- Compare recommended trade price against realized intraday VWAP and DA price

### Phase F: Implement Phase 8 — Regime Detection (Estimated: 1 session)

**F.1** — Create `tradingagents/dataflows/regime_classifier.py`
- Demand-quote regime from Kie17: threshold at ~1.18 and ~1.4
- Implement spike probability from Jon05
- Implement negative price probability from Sch11

**F.2** — Wire regime classification into the System State Analyst
- Replace the LLM-based regime classification with a data-driven classifier
- Use the classifier output to pre-populate `regime_indicator` in state
- The System State Analyst can then validate and override if needed

### Phase G: Data Layer Hardening (Estimated: 1 session)

**G.1** — Consolidate `_load_or_fetch` into `cache_layer.cached_fetch()`
- Currently duplicated across all 4 clients (known Phase 1 bug)

**G.2** — Fix SMARD load forecast filter
- Filter ID 123 returns wrong data (known Phase 1 bug)
- Find correct filter ID or fall back to ENTSO-E

**G.3** — Fix SMARD generation total
- Filter ID 410 shared by generation_total and total_load (known Phase 1 bug)
- Compute total from individual source IDs

**G.4** — Verify CZK→EUR conversion
- ENTSO-E CZ imbalance prices — check that the conversion is working correctly
- The current code does convert (line 793–797 of entsoe_client.py), verify the exchange rate source

---

## Part VII: Recommended Execution Order

| Priority | Phase | Sessions | Impact |
|----------|-------|----------|--------|
| 1 | **Phase A** (Critical context flow fixes) | 1 | Fixes the #1 architectural flaw — signal loss through the pipeline |
| 2 | **Phase B** (Clean up & harden) | 1 | Removes confusion, dead code, and minor bugs |
| 3 | **Phase C** (Tool coverage) | 1 | Gives agents more data to work with |
| 4 | **Phase E** (Backtesting) | 2–3 | Without this, you can't measure if changes help |
| 5 | **Phase D** (Power indicators) | 1–2 | Replaces stock indicators with energy-appropriate ones |
| 6 | **Phase F** (Regime detection) | 1 | Data-driven regime classification |
| 7 | **Phase G** (Data hardening) | 1 | Robustness improvements |

**Total estimated effort**: 8–10 focused sessions.

Phase A should be done first and immediately — it's the difference between the pipeline producing informed decisions vs. telephone-game summaries. Phase E (backtesting) should come right after cleanup because you need measurement to guide all subsequent improvements.

---

## Part VIII: Verification Checklist

After implementing Phase A, run the system and verify in the run.log:

- [ ] Research Manager's prompt contains actual analyst report text (not just debate history)
- [ ] Trader's prompt contains price levels from the Price & Technical report
- [ ] Portfolio Manager's prompt contains regime classification from System State report
- [ ] Each analyst after the first sees a summary of what previous analysts found
- [ ] `get_intraday_prices` for CZ returns OTE data (not entsoe stub)
- [ ] `get_intraday_auction_prices` for CZ returns OTE IDA data (not entsoe error)
- [ ] No `Vendor 'entsoe' does not support method` warnings for CZ-primary tools
- [ ] Report labels say "Price & Technical Analyst" not "Market Analyst"
- [ ] Delivery period is an actual date/time, not "SPY" or "NVDA"
