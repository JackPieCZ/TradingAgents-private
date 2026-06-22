# Phase 2-3 Review & Phase 4-5 Implementation Plan

## Part 1: Phase 2-3 Code Review — Issues Found

I inspected every file listed in the git log. The overall implementation is solid — all 4 analyst prompts are well-written with deep domain expertise, the tool files correctly wrap `route_to_vendor`, and the graph wiring connects the right tools to the right analysts. However, I found several bugs ranging from critical (will crash at runtime) to moderate (functional but messy).

### CRITICAL Bugs

**Bug 1 — `propagation.py` line 83-85: RiskDebateState initialized with wrong field names**

The `RiskDebateState` TypedDict defines these fields: `aggressive_history`, `conservative_history`, `neutral_history`, `history`, `latest_speaker`, `current_aggressive_response`, `current_conservative_response`, `current_neutral_response`, `judge_decision`, `count`.

But `create_initial_state()` initializes it with:
```python
RiskDebateState(
    history="", agg_history="", con_history="",
    current_response="", judge_decision="", count=0
)
```

The field names `agg_history`, `con_history`, `current_response` don't exist in the TypedDict. This will either crash with a TypeError or silently drop the fields, causing KeyError downstream when the risk debate agents try to read `aggressive_history`, `conservative_history`, etc.

**Fix**: Replace with:
```python
RiskDebateState(
    aggressive_history="", conservative_history="", neutral_history="",
    history="", latest_speaker="",
    current_aggressive_response="", current_conservative_response="",
    current_neutral_response="", judge_decision="", count=0
)
```

### MODERATE Bugs

**Bug 2 — All 4 analyst `create_*` functions: Literal `"..."` injected into system prompt**

Every energy analyst factory (e.g., `create_market_analyst`, `create_social_media_analyst`, `create_fundamentals_analyst`, `create_news_analyst`) constructs the prompt as:
```python
("system", "..." + PROMPT_CONSTANT + "...")
```

This literally prepends and appends the string `...` to the system message the LLM receives. It's confusing noise for the model.

**Fix**: Change to `("system", PROMPT_CONSTANT)` in all 4 files.

**Bug 3 — All 4 analyst `create_*` functions: `instrument_context` computed but never used**

Each analyst factory computes a detailed `instrument_context` string with market-specific information (e.g., CZ solar vs DE-LU wind+solar, demand-quote regime details, REMIT context). This context is passed via `prompt.partial(instrument_context=instrument_context)` but the prompt template string doesn't contain `{instrument_context}` anywhere — so it's silently discarded. The LLM never sees this context.

**Fix**: Add `{instrument_context}` to the prompt template, e.g.:
```python
("system", PROMPT_CONSTANT + "\n\nADDITIONAL CONTEXT:\n{instrument_context}")
```

**Bug 4 — All 4 analyst `create_*` functions: `system_message` partial is unused**

The code does `prompt.partial(system_message=PROMPT_CONSTANT, ...)` but the template doesn't reference `{system_message}`. The PROMPT_CONSTANT is already embedded directly in the template string. This partial is harmless but wasteful — clean it up.

**Bug 5 — `trading_graph.py` `_run_graph()`: Parameter name mismatch**

`propagate()` passes `delivery_period` and `trade_timestamp` to `_run_graph()`, but `_run_graph` still names its parameters `company_name` and `trade_date`. Functionally it works (Python doesn't enforce parameter names at the call site), but it's confusing — the variable `company_name` actually holds a delivery period throughout the method body. The commented-out old code is still present everywhere, making the file messy.

**Bug 6 — `_fetch_returns()` and `_resolve_pending_entries()`: Still equity-specific**

These methods use `yfinance` to fetch SPY and stock returns. They will fail or produce meaningless results for power delivery periods. They need to be replaced with energy price fetching (this is Phase 5.5 in the STRATEGY but was not implemented).

**Bug 7 — `reflection.py`: Still references "Alpha vs SPY"**

The reflection prompt produces equity-style reflections ("Raw return: +X%, Alpha vs SPY: +Y%"). This needs to be updated for power markets (e.g., "P&L vs DA price: +X EUR/MWh").

### MINOR Issues

**Bug 8 — Old stock tool imports in `_exchange` variants**

The `_exchange` variants of all analyst factories (e.g., `create_fundamentals_analyst_exchange`) still import and use old equity tools (`get_fundamentals`, `get_balance_sheet`, `get_stock_data`, `get_indicators`, `get_news`, `get_global_news`). These are only called if someone uses the `_exchange` API path, which the energy pipeline doesn't — but they're dead code.

**Bug 9 — `schemas.py` not updated for power market**

The schemas still use equity-style rating types (`PortfolioRating` with Buy/Overweight/Hold/Underweight/Sell, `TraderAction` with Buy/Hold/Sell). The STRATEGY Phase 4 specifies `PowerTradingAction` (Buy/Sell/Hold/Reduce/NoTrade), `MarketRegime`, `PowerTraderProposal`, `PowerPortfolioDecision`. This is explicitly Phase 4 work — but since the Trader and PM prompts already instruct the agent to output power-specific fields (volume_mw, execution_strategy, etc.), there's a mismatch between what the prompt asks for and what the schema accepts.

**Bug 10 — `signal_processing.py` and `rating.py`: 5-tier equity ratings**

These extract `Buy/Overweight/Hold/Underweight/Sell` ratings. Power prompts ask for `Buy/Sell/Hold/Reduce/NoTrade`. The parser won't find `Reduce` or `NoTrade` in its vocabulary, defaulting to `Hold` for those.

**Bug 11 — Phase 1 known bugs still open**

The 4 known issues from the Phase 1 review (ENTSO-E CZ imbalance in CZK, SMARD filter_id 410 conflict, SMARD load forecast filter 123, duplicated `_load_or_fetch`) appear to still be present. The plan mentioned fixing these at the start of Phase 2, but the commits don't show changes to the dataflows files.

### What Was Done Well

- Tool files (`energy_price_tools.py`, `system_data_tools.py`, `weather_tools.py`, `energy_news_tools.py`) are clean, well-documented, and correctly wrap `route_to_vendor`
- Agent prompts contain excellent domain expertise (forecast deltas, merit order reasoning, REMIT compliance, time-to-delivery effects, regime classification framework)
- `AgentState` correctly preserves backward compatibility by keeping old field names (`market_report`, `sentiment_report`, etc.) while adding new power fields
- Graph wiring in `setup.py` correctly binds energy tools to energy analyst factories
- `propagation.py` correctly creates initial state with power-specific context
- `cli/main.py` display names updated correctly
- Bull/Bear researcher prompts have well-adapted power market argumentation
- Risk analyst prompts (aggressive/conservative/neutral) correctly frame power-specific risk dimensions

---

## Part 2: Phase 4 Implementation Plan — Schemas and Decision Outputs

### Overview

Phase 4 replaces the equity-style structured output schemas with power-market-appropriate schemas. This is critical because the Trader and Portfolio Manager prompts (written in Phase 3) already instruct the LLM to output power-specific fields (volume_mw, execution_strategy, regime_assessment, etc.) that the current schemas can't capture.

### Task 4.1: Add Power-Specific Enums to `schemas.py`

**File**: `tradingagents/agents/schemas.py`

Add these new enums ABOVE the existing `PortfolioRating` and `TraderAction` (keep the old ones for backward compatibility):

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
    STRESSED = "Stressed"
    OVERSUPPLIED = "Oversupplied"
    VOLATILE = "Volatile"
```

### Task 4.2: Add `PowerTraderProposal` Schema

**File**: `tradingagents/agents/schemas.py`

Add below the existing `TraderProposal` class:

```python
class PowerTraderProposal(BaseModel):
    """Structured transaction proposal for power intraday trading."""
    action: PowerTradingAction = Field(
        description=(
            "The trading action. Exactly one of: Buy (go long), Sell (go short), "
            "Hold (maintain position), Reduce (decrease existing position), "
            "NoTrade (explicitly choose not to trade this delivery period)."
        )
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analyst reports, forecast "
            "deltas, regime classification, and execution cost assessment. "
            "Two to four sentences."
        )
    )
    volume_mw: Optional[float] = Field(
        default=None,
        description="Position size in MW. Typical range 1-30 MW."
    )
    limit_price_eur: Optional[float] = Field(
        default=None,
        description="Limit price in EUR/MWh. For Buy: max price to pay. For Sell: min price to accept."
    )
    execution_strategy: Optional[str] = Field(
        default=None,
        description=(
            "Execution approach: 'passive_limit' (limit orders, best when >4h to delivery), "
            "'aggressive_market' (take available prices, use when signal is strong/urgent), "
            "'iceberg' (hide large orders in small portions, use when >10 MW), "
            "'twap' (spread execution evenly over remaining window)."
        )
    )
    urgency: Optional[str] = Field(
        default=None,
        description="Urgency level: 'low' (>6h to delivery), 'medium' (2-6h), 'high' (<2h)."
    )
    delivery_period: Optional[str] = Field(
        default=None,
        description="The delivery period this trade targets, e.g. '2024-06-15T14:00'."
    )


def render_power_trader_proposal(proposal: PowerTraderProposal) -> str:
    """Render a PowerTraderProposal to markdown."""
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.volume_mw is not None:
        parts.extend(["", f"**Volume**: {proposal.volume_mw} MW"])
    if proposal.limit_price_eur is not None:
        parts.extend(["", f"**Limit Price**: {proposal.limit_price_eur} EUR/MWh"])
    if proposal.execution_strategy:
        parts.extend(["", f"**Execution Strategy**: {proposal.execution_strategy}"])
    if proposal.urgency:
        parts.extend(["", f"**Urgency**: {proposal.urgency}"])
    if proposal.delivery_period:
        parts.extend(["", f"**Delivery Period**: {proposal.delivery_period}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)
```

### Task 4.3: Add `PowerPortfolioDecision` Schema

**File**: `tradingagents/agents/schemas.py`

Add below the existing `PortfolioDecision` class:

```python
class PowerPortfolioDecision(BaseModel):
    """Structured output from the Portfolio Manager for power trading."""
    action: PowerTradingAction = Field(
        description=(
            "The final position action. Exactly one of: Buy, Sell, Hold, Reduce, NoTrade. "
            "Based on the risk analysts' debate and regime assessment."
        )
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering the trade rationale, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        )
    )
    regime_assessment: MarketRegime = Field(
        description=(
            "Current market regime: Normal, Stressed, Oversupplied, or Volatile. "
            "Based on the System State Analyst's classification."
        )
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate and reports. Include forecast delta magnitude, regime justification, "
            "and execution cost assessment."
        )
    )
    volume_mw: Optional[float] = Field(
        default=None,
        description="Final approved volume in MW."
    )
    price_target_eur: Optional[float] = Field(
        default=None,
        description="Target price in EUR/MWh."
    )
    stop_loss_eur: Optional[float] = Field(
        default=None,
        description="Stop loss price in EUR/MWh."
    )
    max_imbalance_exposure_mw: Optional[float] = Field(
        default=None,
        description="Maximum acceptable imbalance exposure in MW at gate closure."
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Recommended time horizon, e.g. 'until gate closure' or 'next 2 hours'."
    )


def render_power_pm_decision(decision: PowerPortfolioDecision) -> str:
    """Render a PowerPortfolioDecision to markdown."""
    parts = [
        f"**Action**: {decision.action.value}",
        "",
        f"**Regime**: {decision.regime_assessment.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.volume_mw is not None:
        parts.extend(["", f"**Volume**: {decision.volume_mw} MW"])
    if decision.price_target_eur is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target_eur} EUR/MWh"])
    if decision.stop_loss_eur is not None:
        parts.extend(["", f"**Stop Loss**: {decision.stop_loss_eur} EUR/MWh"])
    if decision.max_imbalance_exposure_mw is not None:
        parts.extend(["", f"**Max Imbalance Exposure**: {decision.max_imbalance_exposure_mw} MW"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)
```

### Task 4.4: Wire Power Schemas into Trader

**File**: `tradingagents/agents/trader/trader.py`

In `create_trader()`:
1. Change the import and `bind_structured` call:
   ```python
   from tradingagents.agents.schemas import PowerTraderProposal, render_power_trader_proposal
   structured_llm = bind_structured(llm, PowerTraderProposal, "Trader")
   ```
2. Change the `invoke_structured_or_freetext` call to use `render_power_trader_proposal` instead of `render_trader_proposal`

The `create_trader_exchange()` function (old equity path) should remain unchanged for backward compatibility.

### Task 4.5: Wire Power Schemas into Portfolio Manager

**File**: `tradingagents/agents/managers/portfolio_manager.py`

In `create_portfolio_manager()`:
1. Change the import and `bind_structured` call:
   ```python
   from tradingagents.agents.schemas import PowerPortfolioDecision, render_power_pm_decision
   structured_llm = bind_structured(llm, PowerPortfolioDecision, "Portfolio Manager")
   ```
2. Change the `invoke_structured_or_freetext` call to use `render_power_pm_decision` instead of `render_pm_decision`

The `create_portfolio_manager_exchange()` function (old equity path) should remain unchanged.

### Task 4.6: Update `rating.py` for Power Actions

**File**: `tradingagents/agents/utils/rating.py`

The parser needs to recognize the power-specific action vocabulary:

```python
# Add power-tier scale alongside the equity 5-tier scale
RATINGS_POWER: Tuple[str, ...] = (
    "Buy", "Sell", "Hold", "Reduce", "NoTrade",
)

_POWER_SET = {r.lower() for r in RATINGS_POWER}

# Update the regex to also match "Action: X" (power PM uses **Action** not **Rating**)
_ACTION_LABEL_RE = re.compile(r"(?:rating|action).*?[:\-][\s*]*(\w+)", re.IGNORECASE)


def parse_rating(text: str, default: str = "Hold") -> str:
    """Extract a rating from prose text. Supports both equity 5-tier and power action scales."""
    combined_set = _RATING_SET | _POWER_SET
    
    for line in text.splitlines():
        m = _ACTION_LABEL_RE.search(line)
        if m and m.group(1).lower() in combined_set:
            word = m.group(1).lower()
            # Normalize NoTrade capitalization
            if word == "notrade":
                return "NoTrade"
            return word.capitalize()
    
    for line in text.splitlines():
        for word in line.lower().split():
            clean = word.strip("*:.,")
            if clean in combined_set:
                if clean == "notrade":
                    return "NoTrade"
                return clean.capitalize()
    
    return default
```

### Task 4.7: Update `__init__.py` Exports

**File**: `tradingagents/agents/__init__.py`

No changes needed — the schemas module is imported separately by the files that use it. But verify that `schemas.py` is importable after the changes.

### Task 4.8: Verification

After implementing Tasks 4.1-4.7, verify:
1. `python -c "from tradingagents.agents.schemas import PowerTradingAction, MarketRegime, PowerTraderProposal, PowerPortfolioDecision; print('OK')"` — imports work
2. `python -c "from tradingagents.agents.utils.rating import parse_rating; assert parse_rating('**Action**: NoTrade') == 'NoTrade'; assert parse_rating('**Rating**: Buy') == 'Buy'; print('OK')"` — rating parser handles both scales
3. Run smoke test 1 from the plan (mock LLM) — the system should still complete without errors even though the mock LLM won't produce valid structured output (the `invoke_structured_or_freetext` fallback handles that)

---

## Part 3: Phase 5 Implementation Plan — Graph Orchestration Cleanup

### Overview

Phase 5 fixes the remaining equity-specific code in the graph layer. Most of the heavy lifting was already done during Phase 2-3 (propagation, tool wiring, propagate signature). What remains is: cleaning up internal naming, replacing the equity reflection/return system, and logging power-specific state.

### Task 5.0: Fix Critical Bugs from Phase 2-3 Review (DO THIS FIRST)

These MUST be fixed before any Phase 5 work:

**5.0.1 — Fix `propagation.py` RiskDebateState initialization**

**File**: `tradingagents/graph/propagation.py`, lines 83-86

Replace:
```python
"risk_debate_state": RiskDebateState(
    history="", agg_history="", con_history="",
    current_response="", judge_decision="", count=0
),
```
With:
```python
"risk_debate_state": RiskDebateState(
    aggressive_history="",
    conservative_history="",
    neutral_history="",
    history="",
    latest_speaker="",
    current_aggressive_response="",
    current_conservative_response="",
    current_neutral_response="",
    judge_decision="",
    count=0,
),
```

**5.0.2 — Fix analyst prompt templates (all 4 files)**

**Files**: `fundamentals_analyst.py`, `social_media_analyst.py`, `market_analyst.py`, `news_analyst.py`

In each file's `create_*` (energy) function, replace:
```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "..." + PROMPT_CONSTANT + "..."),
    MessagesPlaceholder(variable_name="messages"),
])
```
With:
```python
prompt = ChatPromptTemplate.from_messages([
    ("system", PROMPT_CONSTANT + "\n\nADDITIONAL CONTEXT:\n{instrument_context}"),
    MessagesPlaceholder(variable_name="messages"),
])
```

And remove the unused `system_message` partial from each. Keep the `instrument_context` partial (it will now actually work).

### Task 5.1: Clean Up `_run_graph()` Internal Naming

**File**: `tradingagents/graph/trading_graph.py`

Rename the `_run_graph` method parameters and internal variable names:

```python
def _run_graph(self, delivery_period, trade_timestamp):
    """Execute the graph and write the resulting state to disk and memory log."""
    past_context = self.memory_log.get_past_context(delivery_period)
    init_agent_state = self.propagator.create_initial_state(
        delivery_period, trade_timestamp, past_context=past_context,
        market_area=self.config.get("market_area", "CZ")
    )
    # ... rest of method uses delivery_period instead of company_name
```

Remove all commented-out old code (the `# self.ticker = company_name` lines, etc.).

### Task 5.2: Replace `_fetch_returns()` with Energy Price Fetching

**File**: `tradingagents/graph/trading_graph.py`

Replace the entire `_fetch_returns()` method. For the MVP, this can be a stub that returns None (disabling deferred reflection) until the backtesting framework in Phase 7 provides the actual settlement price lookup:

```python
def _fetch_returns(
    self, delivery_period: str, trade_date: str, holding_days: int = 5
) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """Fetch realized P&L for a power delivery period.
    
    In the power market, the "return" is the realized P&L:
    (intraday entry price - settlement price) * volume, net of spread/impact.
    
    This requires the backtesting/execution_sim module (Phase 7).
    For now, returns None to skip deferred reflection.
    """
    # TODO Phase 7: Implement using energy price data
    # Compare recommended trade price against:
    # 1. Actual intraday settlement (VWAP or last price)
    # 2. Day-ahead price (was intraday trading value-additive?)
    # 3. Imbalance price (what was the penalty exposure?)
    logger.debug(
        "Skipping return fetch for %s (energy implementation pending)", delivery_period
    )
    return None, None, None
```

### Task 5.3: Update Reflection for Power Markets

**File**: `tradingagents/graph/reflection.py`

Update the reflection prompt to use power-market concepts:

```python
def _get_log_reflection_prompt(self) -> str:
    return (
        "You are a power trading analyst reviewing your own past decision now that the outcome is known.\n"
        "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
        "Cover in order:\n"
        "1. Was the directional call correct? (cite the P&L figure in EUR/MWh)\n"
        "2. Was the regime classification accurate? Did the market behave as the regime predicted?\n"
        "3. One concrete lesson to apply to the next similar delivery period.\n\n"
        "Be specific and terse. Your output will be stored verbatim in a decision log "
        "and re-read by future analysts, so every word must earn its place."
    )

def reflect_on_final_decision(
    self,
    final_decision: str,
    raw_return: float,
    alpha_return: float,
) -> str:
    messages = [
        ("system", self.log_reflection_prompt),
        (
            "human",
            (
                f"Trade P&L: {raw_return:+.2f} EUR/MWh\n"
                f"P&L vs day-ahead benchmark: {alpha_return:+.2f} EUR/MWh\n\n"
                f"Final Decision:\n{final_decision}"
            ),
        ),
    ]
    return self.quick_thinking_llm.invoke(messages).content
```

### Task 5.4: Update `_log_state()` to Include Power Fields

**File**: `tradingagents/graph/trading_graph.py`

Add power-specific fields to the logged state:

```python
def _log_state(self, trade_date, final_state):
    self.log_states_dict[str(trade_date)] = {
        # Power identifiers
        "delivery_period": final_state.get("delivery_period", ""),
        "market_area": final_state.get("market_area", ""),
        "regime_indicator": final_state.get("regime_indicator", ""),
        # Backward compat
        "company_of_interest": final_state["company_of_interest"],
        "trade_date": final_state["trade_date"],
        # Reports
        "market_report": final_state["market_report"],
        "sentiment_report": final_state["sentiment_report"],
        "news_report": final_state["news_report"],
        "fundamentals_report": final_state["fundamentals_report"],
        # Debates (unchanged)
        "investment_debate_state": { ... },  # same as before
        "trader_investment_decision": final_state["trader_investment_plan"],
        "risk_debate_state": { ... },  # same as before
        "investment_plan": final_state["investment_plan"],
        "final_trade_decision": final_state["final_trade_decision"],
    }
    # ... rest unchanged
```

### Task 5.5: Update `memory.py` for Power Trading

**File**: `tradingagents/agents/utils/memory.py`

The memory log currently stores decisions keyed by `ticker` and `trade_date`. For power, the key should be `delivery_period` + `market_area`.

Search the file for references to "ticker" and update the mental model, but keep backward compatibility. The key change: `store_decision()` and `get_past_context()` should work with delivery periods.

Inspect the existing code and change the `ticker` parameter name to `identifier` (or keep as `ticker` for compat but document that it receives `delivery_period_market_area` in the energy path).

The log format should remain append-only markdown per the original design. No structural changes needed — just parameter naming.

### Task 5.6: Remove Equity Imports and Dead Code

**File**: `tradingagents/graph/trading_graph.py`

Remove:
```python
import yfinance as yf
```

And remove all commented-out lines that reference the old equity code patterns.

**Files**: All 4 analyst files (`fundamentals_analyst.py`, `social_media_analyst.py`, `market_analyst.py`, `news_analyst.py`)

In the `_exchange` variant functions (which are the OLD equity path), you have two options:
1. **Keep them** for backward compatibility (if you ever want to run the stock path)
2. **Remove them** if you're fully committed to the energy fork

Recommendation: Keep them for now but add a comment `# Legacy equity path — not used in energy fork`

### Task 5.7: Smoke Test Verification

After implementing all Phase 5 tasks, run:

1. **Smoke Test A — Mock LLM, verify no crashes**:
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import copy

config = copy.deepcopy(DEFAULT_CONFIG)
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-4o-mini"
config["quick_think_llm"] = "gpt-4o-mini"

# Test with mock data vendors
config["data_vendors"] = {
    "price_data": "mock", "system_data": "mock",
    "weather_data": "mock", "news_data": "mock",
    "market_fundamentals": "mock"
}

graph = TradingAgentsGraph(config=config)
state, signal = graph.propagate(
    delivery_period="2026-05-01",
    trade_timestamp="2026-04-30T18:00",
    market_area="CZ"
)

# Verify all reports populated
assert state["market_report"] != "", "Market report empty"
assert state["sentiment_report"] != "", "Sentiment report empty"
assert state["news_report"] != "", "News report empty"
assert state["fundamentals_report"] != "", "Fundamentals report empty"
assert state["final_trade_decision"] != "", "Final decision empty"

# Verify power fields present
assert state.get("delivery_period") == "2026-05-01"
assert state.get("market_area") == "CZ"

# Verify signal extraction works with power actions
print(f"Signal: {signal}")
print("SMOKE TEST PASSED")
```

2. **Smoke Test B — Import verification**:
```python
from tradingagents.agents.schemas import (
    PowerTradingAction, MarketRegime,
    PowerTraderProposal, PowerPortfolioDecision,
    render_power_trader_proposal, render_power_pm_decision
)
from tradingagents.agents.utils.rating import parse_rating

# Test power rating parsing
assert parse_rating("**Action**: NoTrade") == "NoTrade"
assert parse_rating("**Action**: Buy") == "Buy"
assert parse_rating("**Action**: Reduce") == "Reduce"
assert parse_rating("**Rating**: Sell") == "Sell"  # backward compat

# Test schema instantiation
proposal = PowerTraderProposal(
    action=PowerTradingAction.BUY,
    reasoning="Strong downward wind revision",
    volume_mw=10.0,
    limit_price_eur=45.50,
    execution_strategy="passive_limit",
    urgency="medium"
)
rendered = render_power_trader_proposal(proposal)
assert "10.0 MW" in rendered
assert "45.5" in rendered
print("SCHEMA TEST PASSED")
```

---

## Part 4: Summary of Files to Touch

### Phase 4 (Schemas)
| File | Change | Effort |
|------|--------|--------|
| `tradingagents/agents/schemas.py` | Add PowerTradingAction, MarketRegime, PowerTraderProposal, PowerPortfolioDecision + render functions | Medium |
| `tradingagents/agents/trader/trader.py` | Wire PowerTraderProposal into `create_trader()` | Small |
| `tradingagents/agents/managers/portfolio_manager.py` | Wire PowerPortfolioDecision into `create_portfolio_manager()` | Small |
| `tradingagents/agents/utils/rating.py` | Add power action vocabulary to parser | Small |

### Phase 5 (Graph Cleanup + Bug Fixes)
| File | Change | Effort |
|------|--------|--------|
| `tradingagents/graph/propagation.py` | **FIX CRITICAL BUG**: RiskDebateState field names | Small |
| `tradingagents/agents/analysts/fundamentals_analyst.py` | Fix prompt template ("..." removal, instrument_context injection) | Small |
| `tradingagents/agents/analysts/social_media_analyst.py` | Same fix | Small |
| `tradingagents/agents/analysts/market_analyst.py` | Same fix | Small |
| `tradingagents/agents/analysts/news_analyst.py` | Same fix | Small |
| `tradingagents/graph/trading_graph.py` | Clean up _run_graph naming, replace _fetch_returns, remove yfinance, add power fields to _log_state, remove dead code | Medium |
| `tradingagents/graph/reflection.py` | Update prompt for power market reflection | Small |
| `tradingagents/agents/utils/memory.py` | Update parameter naming for power context | Small |

### Execution Order

1. **Task 5.0** (bug fixes) — FIRST, this unblocks everything
2. **Tasks 4.1-4.3** (schema definitions) — pure additions, no breaking changes
3. **Tasks 4.4-4.5** (wire schemas into trader/PM) — depends on 4.1-4.3
4. **Task 4.6** (rating parser) — depends on 4.1
5. **Tasks 5.1-5.6** (graph cleanup) — can be done in any order
6. **Task 5.7** (smoke tests) — LAST, validates everything

**Estimated total effort**: 4-6 hours for a coding agent. ~600 lines of new/modified code.
