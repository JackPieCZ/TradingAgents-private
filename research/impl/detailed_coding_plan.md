# Detailed Coding Plan — BUG-5, BUG-6, BUG-7, Part II, III, IV, V

**Purpose**: Step-by-step, copy-paste-ready instructions for a coding agent. Every change specifies the exact file, the exact old text to find, and the exact new text to replace it with.

**Repository**: `JackPieCZ/TradingAgents-private` (latest main branch)

**Convention used throughout**: Each step uses a `FIND → REPLACE` block. The agent should open the file, find the exact `OLD` text, and replace it with the `NEW` text. If the instruction says "DELETE", remove the block entirely with no replacement.

---

## TABLE OF CONTENTS

1. [BUG-5: Fix default_config.py Vendor Routing](#bug-5)
2. [BUG-6: Fix entsoe_client.py Intraday Stub](#bug-6)
3. [BUG-7: Expand News Analyst Toolkit](#bug-7)
4. [Part II: Fix Inter-Analyst Context Flow (BUG-4)](#part-ii)
5. [Part III: Wire Unused Tools & Cross-Referencing](#part-iii)
6. [Part IV: Add Tool Output Format Descriptions](#part-iv)
7. [Part V: File-Level Cleanup](#part-v)

---

## 1. BUG-5: Fix `default_config.py` Vendor Routing

**File**: `tradingagents/default_config.py`

**Problem**: Three routing entries send CZ-specific requests to vendors that don't support them:
- `get_intraday_auction_prices` → `"entsoe"` but ENTSO-E has no implementation for IDA prices (it's commented out in `VENDOR_METHODS`). Only OTE supports IDA prices.
- `get_intraday_prices` → `"entsoe,ote"` but the ENTSO-E implementation is commented out in `VENDOR_METHODS`, so the first vendor always fails and logs a warning before falling back to OTE.
- `get_balancing_data` → `"entsoe"` only, but OTE also provides imbalance settlement data for CZ and should be a fallback.

### Step 1.1 — Fix intraday prices routing

**File**: `tradingagents/default_config.py`

FIND (exact text):
```python
        "get_intraday_prices": "entsoe,ote",
```

REPLACE WITH:
```python
        "get_intraday_prices": "ote",
```

**Why**: ENTSO-E's `query_intraday_prices` is not in `VENDOR_METHODS` (commented out at line 210-212 of `interface.py`). Setting `"entsoe,ote"` causes `route_to_vendor` to log `"Vendor 'entsoe' does not support method 'get_intraday_prices'. Skipping."` every time before falling back to OTE. Making OTE primary eliminates the warning and the wasted fallback attempt.

### Step 1.2 — Fix intraday auction prices routing

**File**: `tradingagents/default_config.py`

FIND:
```python
        "get_intraday_auction_prices": "entsoe",
```

REPLACE WITH:
```python
        "get_intraday_auction_prices": "ote",
```

**Why**: ENTSO-E has no implementation for IDA prices (also commented out in `VENDOR_METHODS` at line 217-219). Only OTE supports `get_intraday_auction_prices` via `ote_ida_prices`. Setting `"entsoe"` causes a `"Vendor 'entsoe' does not support method"` warning every time, and the fallback chain only works because OTE is listed as a remaining available vendor. Making OTE primary fixes this.

### Step 1.3 — Add OTE as fallback for balancing data

**File**: `tradingagents/default_config.py`

FIND:
```python
        "get_balancing_data": "entsoe",
```

REPLACE WITH:
```python
        "get_balancing_data": "entsoe,ote",
```

**Why**: Both ENTSO-E and OTE have implementations for balancing/imbalance data (see `VENDOR_METHODS` at line 250-253 in `interface.py`). For CZ, OTE's imbalance settlement data may be more accurate. Adding OTE as a fallback ensures data availability if ENTSO-E fails.

### Verification

After all three changes, the `tool_vendors` dict in `default_config.py` should look like:
```python
    "tool_vendors": {
        # Energy-specific overrides
        "get_day_ahead_prices": "entsoe,ote",
        "get_intraday_prices": "ote",
        "get_intraday_auction_prices": "ote",
        "get_residual_load": "entsoe,smard",
        "get_generation_forecast": "entsoe",
        "get_actual_generation": "smard,entsoe",
        "get_load_forecast": "entsoe",
        "get_cross_border_flows": "entsoe",
        "get_outages": "entsoe",
        "get_balancing_data": "entsoe,ote",
        "get_wind_forecast": "openmeteo",
        "get_solar_forecast": "openmeteo",
        "get_weather_forecast": "openmeteo",
        "get_forecast_updates": "entsoe",
    },
```

---

## 2. BUG-6: Fix `entsoe_client.py` Intraday Prices Stub

**File**: `tradingagents/dataflows/entsoe_client.py`

**Problem**: The function `query_intraday_prices()` (line 216-266) has a hardcoded `return` statement on line 222 that returns a stub string *before* the actual `fetch()` function definition. This makes the entire function body after line 222 dead code. Because the stub returns a valid string (not an exception), `route_to_vendor` treats it as "success" and never falls back to OTE.

**Note**: Since we already fixed BUG-5 to route `get_intraday_prices` directly to OTE (bypassing ENTSO-E), AND the `entsoe` entry is already commented out from `VENDOR_METHODS`, this function is currently not reachable through the normal code path. However, if someone later uncomments the ENTSO-E entry in `VENDOR_METHODS`, the stub would silently swallow the request. The fix is to raise `NotImplementedError` so the fallback chain works correctly.

### Step 2.1 — Replace stub return with NotImplementedError

**File**: `tradingagents/dataflows/entsoe_client.py`

FIND (exact text, this is lines 216-266):
```python
def query_intraday_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
    auction_sequence: Annotated[Optional[int], "Intraday auction number: 1, 2, or 3. None for all."] = None,
) -> str:
    """Fetch intraday auction prices (XBID/CIDAR) for a given date and zone."""
    return "Intraday prices are currently unavailable due to ENTSO-E API changes. This will be re-enabled in Phase 2 after we implement the new API endpoints and data parsing logic."

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
```

REPLACE WITH:
```python
def query_intraday_prices(
    delivery_date: Annotated[str, "Delivery date in YYYY-MM-DD format"],
    market_area: Annotated[str, "Bidding zone, e.g. 'DE-LU' or 'CZ'"],
    auction_sequence: Annotated[Optional[int], "Intraday auction number: 1, 2, or 3. None for all."] = None,
) -> str:
    """Fetch intraday auction prices (XBID/CIDAR) for a given date and zone.

    NOTE: ENTSO-E intraday price endpoint is not yet implemented.
    Raises NotImplementedError so route_to_vendor falls through to OTE.
    """
    raise NotImplementedError(
        "ENTSO-E intraday prices are not yet implemented. "
        "Use OTE as the vendor for get_intraday_prices."
    )
```

**Why**: Raising `NotImplementedError` ensures that if someone re-adds `"entsoe"` to `VENDOR_METHODS` for `get_intraday_prices`, the `route_to_vendor` function's `except Exception` block on line 347-348 of `interface.py` will catch it and fall back to the next vendor (OTE). The old dead code below the stub is removed entirely since it was unreachable anyway.

---

<a id="bug-7"></a>

## 3. BUG-7: Expand News Analyst Toolkit

**Problem**: The News & Regulatory Analyst only has 2 tools (`get_outage_notifications`, `get_actual_load`), but its prompt references analyzing demand surprises and its role requires understanding cross-border constraints. Additionally, `get_outage_notifications` in `energy_news_tools.py` calls the exact same underlying function (`entsoe_outages`) as `get_outages` in `system_data_tools.py` — they're duplicates.

**Fix**: Add `get_cross_border_flows` and `get_load_forecast` to the News analyst's toolkit. This lets it detect import/export constraints and demand surprises (load forecast vs actual).

### Step 3.1 — Add new tools to `energy_news_tools.py`

**File**: `tradingagents/agents/utils/energy_news_tools.py`

FIND (the entire file content):
```python
"""Energy news and regulatory tools for the News & Regulatory Analyst."""
from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_outage_notifications(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch REMIT urgent market messages (UMMs) about generation unit outages.
    Includes planned maintenance and unplanned outages with MW unavailable."""
    return route_to_vendor("get_outage_notifications", delivery_date=delivery_date, market_area=market_area)

@tool
def get_actual_load(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch actual realized total load (demand) for context on demand patterns."""
    return route_to_vendor("get_actual_load", delivery_date=delivery_date, market_area=market_area)
```

REPLACE WITH:
```python
"""Energy news and regulatory tools for the News & Regulatory Analyst."""
from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_outage_notifications(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch REMIT urgent market messages (UMMs) about generation unit outages.
    Includes planned maintenance and unplanned outages with MW unavailable."""
    return route_to_vendor("get_outage_notifications", delivery_date=delivery_date, market_area=market_area)

@tool
def get_actual_load(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch actual realized total load (demand) for context on demand patterns."""
    return route_to_vendor("get_actual_load", delivery_date=delivery_date, market_area=market_area)

@tool
def get_cross_border_flows(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch cross-border physical power flows with neighboring bidding zones.
    Positive = import into zone, Negative = export. Use to detect FBMC congestion
    and import/export constraints that affect local supply-demand balance."""
    return route_to_vendor("get_cross_border_flows", delivery_date=delivery_date, market_area=market_area)

@tool
def get_load_forecast(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch the day-ahead total load (demand) forecast in MW.
    Compare with get_actual_load to detect demand surprises —
    actual load significantly above forecast = upward price pressure."""
    return route_to_vendor("get_load_forecast", delivery_date=delivery_date, market_area=market_area)
```

### Step 3.2 — Update imports in `setup.py` for news tools

**File**: `tradingagents/graph/setup.py`

FIND:
```python
from tradingagents.agents.utils.energy_news_tools import (
    get_outage_notifications, get_actual_load
)
```

REPLACE WITH:
```python
from tradingagents.agents.utils.energy_news_tools import (
    get_outage_notifications, get_actual_load,
    get_cross_border_flows as news_cross_border_flows,
    get_load_forecast as news_load_forecast,
)
```

**Why the aliased imports**: `get_cross_border_flows` and `get_load_forecast` are already imported from `system_data_tools` in this file. We alias the news versions to avoid name collisions. They call the same underlying `route_to_vendor` function, but they are separate `@tool`-decorated functions with different docstrings tailored to the News analyst's perspective.

### Step 3.3 — Wire new tools into the News analyst node in `setup.py`

**File**: `tradingagents/graph/setup.py`

FIND:
```python
        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm, [
                    get_outage_notifications, get_actual_load
                ]
            )
```

REPLACE WITH:
```python
        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm, [
                    get_outage_notifications, get_actual_load,
                    news_cross_border_flows, news_load_forecast,
                ]
            )
```

### Step 3.4 — Update imports in `trading_graph.py` for news tools

**File**: `tradingagents/graph/trading_graph.py`

FIND:
```python
from tradingagents.agents.utils.energy_news_tools import (
    get_outage_notifications, get_actual_load
)
```

REPLACE WITH:
```python
from tradingagents.agents.utils.energy_news_tools import (
    get_outage_notifications, get_actual_load,
    get_cross_border_flows as news_cross_border_flows,
    get_load_forecast as news_load_forecast,
)
```

### Step 3.5 — Wire new tools into the News ToolNode in `trading_graph.py`

**File**: `tradingagents/graph/trading_graph.py`

FIND:
```python
            "news": ToolNode(  # Energy News & Regulatory Analyst
                [
                    # # News and insider information
                    # get_news,
                    # get_global_news,
                    # get_insider_transactions,
                    get_outage_notifications, get_actual_load
                ]
            ),
```

REPLACE WITH:
```python
            "news": ToolNode(  # Energy News & Regulatory Analyst
                [
                    get_outage_notifications, get_actual_load,
                    news_cross_border_flows, news_load_forecast,
                ]
            ),
```

### Step 3.6 — Update the News analyst prompt to reference new tools

**File**: `tradingagents/agents/analysts/news_analyst.py`

FIND:
```python
ANALYTICAL WORKFLOW:
1. Retrieve outage notifications (get_outage_notifications) — planned and unplanned
2. Retrieve actual load data (get_actual_load) — compare with forecast for demand surprises
```

REPLACE WITH:
```python
ANALYTICAL WORKFLOW:
1. Retrieve outage notifications (get_outage_notifications) — planned and unplanned
2. Retrieve actual load data (get_actual_load) — compare with forecast for demand surprises
3. Retrieve load forecast (get_load_forecast) — the day-ahead demand expectation to compare against actual
4. Retrieve cross-border flows (get_cross_border_flows) — detect import/export constraints and FBMC congestion
```

### Verification

After these changes:
- The News analyst has 4 tools: `get_outage_notifications`, `get_actual_load`, `get_cross_border_flows`, `get_load_forecast`
- The prompt workflow section references all 4 tools
- Both `setup.py` and `trading_graph.py` pass all 4 tools to the News analyst and its ToolNode
- No name collision with the System State analyst's tools (aliased imports)

---

<a id="part-ii"></a>

## 4. Part II: Fix Inter-Analyst Context Flow (BUG-4)

**Problem**: After each analyst finishes, `create_msg_delete()` wipes ALL messages and replaces them with `HumanMessage(content="Continue")`. The next analyst starts with zero context from previous analysts. Each analyst works in complete isolation.

**Fix**: Implement Option C from the plan — create an `analyst_context` state field that accumulates a short summary from each analyst. Each subsequent analyst reads this field in its system prompt. Keep `Msg Clear` for token management.

### Step 4.1 — Add `analyst_context` field to `AgentState`

**File**: `tradingagents/agents/utils/agent_states.py`

FIND:
```python
class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Ticker or delivery_period identifier"]
    trade_date: Annotated[str, "What date we are trading at"]

    sender: Annotated[str, "Agent that sent this message"]

    # research step
    market_report: Annotated[str, "Report from Price & Technical Analyst"]
    sentiment_report: Annotated[str, "Report from System State Analyst"]
    news_report: Annotated[str, "Report from Energy News & Regulatory Analyst"]
    fundamentals_report: Annotated[str, "Report from Weather & Forecast Analyst"]
```

REPLACE WITH:
```python
class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Ticker or delivery_period identifier"]
    trade_date: Annotated[str, "What date we are trading at"]

    sender: Annotated[str, "Agent that sent this message"]

    # Inter-analyst context: accumulates key findings so later analysts
    # can see what earlier analysts discovered (without full message history).
    analyst_context: Annotated[str, "Accumulated key findings from previous analysts"]

    # research step
    market_report: Annotated[str, "Report from Price & Technical Analyst"]
    sentiment_report: Annotated[str, "Report from System State Analyst"]
    news_report: Annotated[str, "Report from Energy News & Regulatory Analyst"]
    fundamentals_report: Annotated[str, "Report from Weather & Forecast Analyst"]
```

### Step 4.2 — Initialize `analyst_context` in the propagation call

**File**: `tradingagents/graph/trading_graph.py`

Find the method that builds the initial state dict and passes it into the graph. Search for where `market_report` is initialized to `""`:

FIND (look for a block like this within the `propagate` method — approximately line 309-400):
```python
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
```

REPLACE WITH:
```python
            "analyst_context": "",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
```

**IMPORTANT**: If the coding agent cannot find this exact block, search for the dict literal inside the `propagate()` method (around line 309-400) that initializes the `AgentState` fields. Add `"analyst_context": "",` as the first entry in the research step section.

### Step 4.3 — Modify `create_msg_delete()` to inject analyst context

**File**: `tradingagents/agents/utils/agent_utils.py`

The current `create_msg_delete()` wipes all messages and adds `HumanMessage(content="Continue")`. We need to make it inject the accumulated `analyst_context` into the placeholder message so the next analyst sees it.

FIND:
```python
def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages
```

REPLACE WITH:
```python
def create_msg_delete():
    def delete_messages(state):
        """Clear messages but inject accumulated analyst context for the next analyst."""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Build context summary from previous analysts' findings
        context = state.get("analyst_context", "")
        if context:
            placeholder_text = (
                f"Previous analysts have reported the following key findings:\n\n"
                f"{context}\n\n"
                f"Use these findings as context for your own analysis. Continue with your assigned tools."
            )
        else:
            placeholder_text = "Continue"

        placeholder = HumanMessage(content=placeholder_text)

        return {"messages": removal_operations + [placeholder]}

    return delete_messages
```

### Step 4.4 — Make the Market Analyst (first analyst) append to `analyst_context`

**File**: `tradingagents/agents/analysts/market_analyst.py`

In the `create_market_analyst` function (the energy version, starting around line 159), the return dict currently is:

FIND:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        return {
            "messages": [result],
            "market_report": report,  # Keep original field name
        }
```

REPLACE WITH:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        # Append a brief summary to analyst_context for subsequent analysts
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                f"--- Price & Technical Analyst ---\n"
                f"{report[:1500]}\n"
            )
            new_context = existing_context + context_addition
        else:
            new_context = existing_context
        return {
            "messages": [result],
            "market_report": report,  # Keep original field name
            "analyst_context": new_context,
        }
```

**Why `[:1500]`**: We truncate to ~1500 chars to prevent token budget explosion. The full report is still stored in `market_report`; this is just inter-analyst context.

### Step 4.5 — Make the System State Analyst (second analyst) append to `analyst_context`

**File**: `tradingagents/agents/analysts/social_media_analyst.py`

In the `create_social_media_analyst` function (energy version, starting around line 126):

FIND:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        return {
            "messages": [result],
            "sentiment_report": report,
        }
```

REPLACE WITH:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        # Append a brief summary to analyst_context for subsequent analysts
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                f"--- System State Analyst ---\n"
                f"{report[:1500]}\n"
            )
            new_context = existing_context + context_addition
        else:
            new_context = existing_context
        return {
            "messages": [result],
            "sentiment_report": report,
            "analyst_context": new_context,
        }
```

### Step 4.6 — Make the News Analyst (third analyst) append to `analyst_context`

**File**: `tradingagents/agents/analysts/news_analyst.py`

In the `create_news_analyst` function (energy version, starting around line 105):

FIND:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        return {
            "messages": [result],
            "news_report": report,  # Keep original field name
        }
```

REPLACE WITH:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        # Append a brief summary to analyst_context for subsequent analysts
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                f"--- Energy News & Regulatory Analyst ---\n"
                f"{report[:1500]}\n"
            )
            new_context = existing_context + context_addition
        else:
            new_context = existing_context
        return {
            "messages": [result],
            "news_report": report,  # Keep original field name
            "analyst_context": new_context,
        }
```

### Step 4.7 — Make the Weather & Forecast Analyst (fourth analyst) append to `analyst_context`

**File**: `tradingagents/agents/analysts/fundamentals_analyst.py`

In the `create_fundamentals_analyst` function (energy version, starting around line 72):

FIND:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        return {
            "messages": [result],
            "fundamentals_report": report,  # Keep original field name
        }
```

REPLACE WITH:
```python
        report = result.content if len(result.tool_calls) == 0 else ""
        # Append a brief summary to analyst_context for subsequent analysts
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                f"--- Weather & Forecast Analyst ---\n"
                f"{report[:1500]}\n"
            )
            new_context = existing_context + context_addition
        else:
            new_context = existing_context
        return {
            "messages": [result],
            "fundamentals_report": report,  # Keep original field name
            "analyst_context": new_context,
        }
```

### Verification for Part II

After these changes:
- `AgentState` has an `analyst_context: str` field
- Initial state sets `analyst_context` to `""`
- Each analyst appends a truncated version of its report to `analyst_context` when it finishes
- `create_msg_delete()` injects the accumulated `analyst_context` into the placeholder message
- The 2nd analyst sees the 1st analyst's findings; the 3rd sees the 1st+2nd; the 4th sees all three
- Full reports are still stored separately in `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`

---

<a id="part-iii"></a>

## 5. Part III: Wire Unused Tools & Cross-Referencing

### Step 5.1 — Wire `get_intraday_prices_period` to the Price & Technical Analyst

`get_intraday_prices_period` (OTE 15-min resolution intraday prices) is implemented in the data layer but not wired to any agent. It's valuable for granular intraday price analysis.

#### Step 5.1a — Create the tool wrapper

**File**: `tradingagents/agents/utils/energy_price_tools.py`

FIND (the end of the file, after the `get_imbalance_data` tool):
```python
@tool
def get_imbalance_data(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch imbalance settlement prices and volumes. Imbalance price is
    the penalty for positions not closed before gate closure."""
    return route_to_vendor("get_balancing_data", delivery_date=delivery_date, market_area=market_area)
```

REPLACE WITH (append the new tool after):
```python
@tool
def get_imbalance_data(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch imbalance settlement prices and volumes. Imbalance price is
    the penalty for positions not closed before gate closure."""
    return route_to_vendor("get_balancing_data", delivery_date=delivery_date, market_area=market_area)

@tool
def get_intraday_prices_period(delivery_date: str, market_area: str = "CZ") -> str:
    """Fetch 15-minute resolution intraday continuous market prices from OTE.
    Provides granular VWAP, volume, and price range data for each 15-min
    delivery period. More detailed than hourly get_intraday_prices."""
    return route_to_vendor("get_intraday_prices_period", delivery_date=delivery_date, market_area=market_area)
```

#### Step 5.1b — Add import in `setup.py`

**File**: `tradingagents/graph/setup.py`

FIND:
```python
from tradingagents.agents.utils.energy_price_tools import (
    get_day_ahead_prices, get_intraday_prices,
    get_intraday_auction_prices, get_imbalance_data
)
```

REPLACE WITH:
```python
from tradingagents.agents.utils.energy_price_tools import (
    get_day_ahead_prices, get_intraday_prices,
    get_intraday_auction_prices, get_imbalance_data,
    get_intraday_prices_period,
)
```

#### Step 5.1c — Wire into Market analyst node in `setup.py`

**File**: `tradingagents/graph/setup.py`

FIND:
```python
        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm, [
                    get_day_ahead_prices, get_intraday_prices,
                    get_intraday_auction_prices, get_imbalance_data
                ]
            )
```

REPLACE WITH:
```python
        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm, [
                    get_day_ahead_prices, get_intraday_prices,
                    get_intraday_auction_prices, get_imbalance_data,
                    get_intraday_prices_period,
                ]
            )
```

#### Step 5.1d — Add import in `trading_graph.py`

**File**: `tradingagents/graph/trading_graph.py`

FIND:
```python
from tradingagents.agents.utils.energy_price_tools import (
    get_day_ahead_prices, get_intraday_prices,
    get_intraday_auction_prices, get_imbalance_data
)
```

REPLACE WITH:
```python
from tradingagents.agents.utils.energy_price_tools import (
    get_day_ahead_prices, get_intraday_prices,
    get_intraday_auction_prices, get_imbalance_data,
    get_intraday_prices_period,
)
```

#### Step 5.1e — Wire into Market ToolNode in `trading_graph.py`

**File**: `tradingagents/graph/trading_graph.py`

FIND:
```python
            "market": ToolNode(  # Price & Technical Analyst
                [
                    # # Core stock data tools
                    # get_stock_data,
                    # # Technical indicators
                    # get_indicators,
                    get_day_ahead_prices, get_intraday_prices,
                    get_intraday_auction_prices, get_imbalance_data
                ]
            ),
```

REPLACE WITH:
```python
            "market": ToolNode(  # Price & Technical Analyst
                [
                    get_day_ahead_prices, get_intraday_prices,
                    get_intraday_auction_prices, get_imbalance_data,
                    get_intraday_prices_period,
                ]
            ),
```

#### Step 5.1f — Add to config routing

**File**: `tradingagents/default_config.py`

FIND:
```python
        "get_forecast_updates": "entsoe",
    },
```

REPLACE WITH:
```python
        "get_forecast_updates": "entsoe",
        "get_intraday_prices_period": "ote",
    },
```

**Why `"ote"` only**: Only OTE has the 15-min resolution intraday data for CZ (see `VENDOR_METHODS`).

### Step 5.2 — (Cross-referencing) Defer `route_to_all_vendors()` to a later phase

The implementation plan mentions creating a `route_to_all_vendors()` function to aggregate results from multiple vendors for the same tool (e.g., getting DA prices from both ENTSO-E and OTE and showing both). This is a significant architectural change that should be deferred. **No action required here** — flag for a future session.

---

<a id="part-iv"></a>

## 6. Part IV: Add Tool Output Format Descriptions to Analyst Prompts

**Problem**: Agents don't know what their tools' output looks like. They don't know the CSV column names or units, leading to potential misinterpretation of data.

### Step 6.1 — Add output format section to Price & Technical Analyst prompt

**File**: `tradingagents/agents/analysts/market_analyst.py`

FIND (at the end of the `PRICE_TECHNICAL_ANALYST_PROMPT` string, just before the closing line):
```python
You have access to the following tools: {tool_names}. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.""" + get_language_instruction()
```

REPLACE WITH:
```python
TOOL OUTPUT FORMATS (so you know what to expect from each tool):
- get_day_ahead_prices → CSV header + rows. Columns: Hour (CET), Price EUR/MWh. One row per delivery hour.
- get_intraday_prices → CSV header + rows. Columns: Hour (CET), Price EUR/MWh (VWAP), Volume MWh, plus additional spread/range metrics.
- get_intraday_auction_prices → CSV header + rows. Columns: Hour (CET), Auction (IDA1/IDA2/IDA3), Price EUR/MWh, Volume MWh, Import MWh, Export MWh, Saldo MWh.
- get_imbalance_data → CSV header + rows. Columns vary by source but typically include: Hour, Imbalance Volume MW, Imbalance Price EUR/MWh.
- get_intraday_prices_period → CSV header + rows. 15-minute resolution. Columns: Period (CET), Price EUR/MWh (VWAP), Volume MWh, Min Price, Max Price.

All tool outputs start with a Markdown header line (# Title) followed by metadata lines (# Source, # Unit) and then CSV data. Parse from the first non-comment line onward.

You have access to the following tools: {tool_names}. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.""" + get_language_instruction()
```

### Step 6.2 — Add output format section to System State Analyst prompt

**File**: `tradingagents/agents/analysts/social_media_analyst.py`

FIND (at the end of `SYSTEM_STATE_ANALYST_PROMPT`, last line):
```python
You have access to the following tools: {tool_names}."""
```

REPLACE WITH:
```python
TOOL OUTPUT FORMATS:
- get_residual_load → CSV. Columns: Hour (CET), Total Load MW, Wind MW, Solar MW, Residual Load MW. Residual = Total - Wind - Solar.
- get_actual_generation → CSV. Columns: Hour (CET) and one column per fuel type (e.g. Lignite MW, Nuclear MW, Gas MW, Wind MW, Solar MW, etc.).
- get_load_forecast → CSV. Columns: Hour (CET), Forecasted Load MW.
- get_cross_border_flows → CSV. Columns: Hour (CET), then one column per border (e.g. CZ→DE MW, DE→CZ MW). Positive = export, Negative = import (convention may vary).
- get_outages → Text summary of planned/unplanned outages with plant name, type, MW unavailable, start/end times.

All outputs start with a # header line and # metadata, followed by CSV data.

You have access to the following tools: {tool_names}."""
```

### Step 6.3 — Add output format section to News Analyst prompt

**File**: `tradingagents/agents/analysts/news_analyst.py`

FIND (at the end of `NEWS_REGULATORY_ANALYST_PROMPT`, last line):
```python
You have access to the following tools: {tool_names}."""
```

REPLACE WITH:
```python
TOOL OUTPUT FORMATS:
- get_outage_notifications → Text summary of REMIT UMMs: plant name, fuel type, MW unavailable, planned/unplanned, start and end times.
- get_actual_load → CSV. Columns: Hour (CET), Actual Load MW. Compare against day-ahead forecast for demand surprises.
- get_load_forecast → CSV. Columns: Hour (CET), Forecasted Load MW. The day-ahead expectation.
- get_cross_border_flows → CSV. Columns: Hour (CET), then one column per border with flow in MW. Saturated flows indicate FBMC congestion.

All outputs start with a # header line and # metadata, followed by CSV or text data.

You have access to the following tools: {tool_names}."""
```

### Step 6.4 — Add output format section to Weather & Forecast Analyst prompt

**File**: `tradingagents/agents/analysts/fundamentals_analyst.py`

FIND (at the end of `WEATHER_FORECAST_ANALYST_PROMPT`, the last line before the closing `"""`):
```python
You have access to the following tools: {tool_names}."""
```

REPLACE WITH:
```python
TOOL OUTPUT FORMATS:
- get_generation_forecast → CSV. Columns: Hour (CET), Wind Onshore MW, Wind Offshore MW, Solar MW (TSO day-ahead forecast).
- get_wind_forecast → CSV. Hourly weather model data. Columns include: Hour (CET), Wind Speed 80m m/s, Wind Speed 120m m/s, Wind Direction degrees, Wind Gusts m/s.
- get_solar_forecast → CSV. Hourly data. Columns include: Hour (CET), GHI W/m², DNI W/m², DHI W/m², Tilted Irradiance W/m², Cloud Cover percent.
- get_forecast_updates → CSV. Columns: Hour (CET), then updated MW forecasts with delta columns showing revision since day-ahead.
- get_weather_forecast → CSV. Columns: Hour (CET), Temperature °C, Precipitation mm, Cloud Cover percent, Pressure hPa, Humidity percent.
- get_historical_forecast → CSV. Same format as get_weather_forecast but from yesterday's model run. Compare with today's forecast to find revisions.

All outputs start with a # header line and # metadata, followed by CSV data.

You have access to the following tools: {tool_names}."""
```

---

<a id="part-v"></a>

## 7. Part V: Specific File-Level Issues

### Step 7.1 — (Issue 5.2) Update report labels in `cli/main.py`

**Problem**: Report labels use stock terminology ("Market Analyst", "Social Analyst") instead of energy names.

There are **multiple locations** to update. Apply each find-replace in order:

#### 7.1a — Fix the progress table (around line 303-308)

**File**: `cli/main.py`

FIND:
```python
        "Analyst Team": [
            "Market Analyst",
            "Social Analyst",
            "News Analyst",
            "Fundamentals Analyst",
        ],
```

REPLACE WITH:
```python
        "Analyst Team": [
            "Price & Technical Analyst",
            "System State Analyst",
            "Energy News & Regulatory Analyst",
            "Weather & Forecast Analyst",
        ],
```

**IMPORTANT NOTE**: These names are used as keys to match against `agent_status` dict keys elsewhere in the CLI. The `agent_status` keys come from the LangGraph node names, which are set in `setup.py` as `f"{analyst_type.capitalize()} Analyst"` — i.e., `"Market Analyst"`, `"Social Analyst"`, etc. Changing the display labels here will break the status matching.

**REVISED APPROACH**: Instead of changing the display labels in the `all_teams` dict (which is used for status matching), we need to change the labels only in the *display* functions. Let's leave `all_teams` alone and instead fix the `ANALYST_AGENT_NAMES` mapping and the display functions.

**ACTUALLY**: Let me re-check. The `all_teams` dict labels ARE the display labels — they're matched against `agent_status` which uses the graph node names. The graph node names are `"Market Analyst"`, `"Social Analyst"`, etc. (set by `f"{analyst_type.capitalize()} Analyst"` in `setup.py`). So changing these display labels would break the match.

**BETTER APPROACH**: Create a display-name mapping and apply it only in the output/display functions. But this is more complex. Let's instead fix only the **report-saving** and **report-display** functions where the labels are hardcoded strings that don't need to match anything.

#### 7.1a (revised) — Fix report labels in `save_report_to_disk` function

**File**: `cli/main.py`

FIND:
```python
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
```
REPLACE WITH:
```python
        analyst_parts.append(("Price & Technical Analyst", final_state["market_report"]))
```

FIND:
```python
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
```
REPLACE WITH:
```python
        analyst_parts.append(("System State Analyst", final_state["sentiment_report"]))
```

FIND:
```python
        analyst_parts.append(("News Analyst", final_state["news_report"]))
```
REPLACE WITH:
```python
        analyst_parts.append(("Energy News & Regulatory Analyst", final_state["news_report"]))
```

FIND:
```python
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
```
REPLACE WITH:
```python
        analyst_parts.append(("Weather & Forecast Analyst", final_state["fundamentals_report"]))
```

#### 7.1b — Fix report labels in `display_complete_report` function

**File**: `cli/main.py`

FIND:
```python
        analysts.append(("Market Analyst", final_state["market_report"]))
```
REPLACE WITH:
```python
        analysts.append(("Price & Technical Analyst", final_state["market_report"]))
```

FIND:
```python
        analysts.append(("Social Analyst", final_state["sentiment_report"]))
```
REPLACE WITH:
```python
        analysts.append(("System State Analyst", final_state["sentiment_report"]))
```

FIND:
```python
        analysts.append(("News Analyst", final_state["news_report"]))
```
REPLACE WITH:
```python
        analysts.append(("Energy News & Regulatory Analyst", final_state["news_report"]))
```

FIND:
```python
        analysts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
```
REPLACE WITH:
```python
        analysts.append(("Weather & Forecast Analyst", final_state["fundamentals_report"]))
```

#### 7.1c — Fix `ANALYST_AGENT_NAMES` mapping

**File**: `cli/main.py`

FIND:
```python
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
```

REPLACE WITH:
```python
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
# Display-friendly names for reports and UI output
ANALYST_DISPLAY_NAMES = {
    "market": "Price & Technical Analyst",
    "social": "System State Analyst",
    "news": "Energy News & Regulatory Analyst",
    "fundamentals": "Weather & Forecast Analyst",
}
```

**Note**: `ANALYST_AGENT_NAMES` must keep the original values because they match the LangGraph node names used for status tracking. `ANALYST_DISPLAY_NAMES` can be used in future display improvements.

### Step 7.2 — (Issue 5.3) Update `main.py` with energy example

**File**: `main.py` (root of repository)

FIND (entire file content):
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gemini-3.1-pro-preview"  # Use a different model
config["quick_think_llm"] = "gemini-3-flash-preview"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: alpha_vantage, yfinance
    "technical_indicators": "yfinance",      # Options: alpha_vantage, yfinance
    "fundamental_data": "yfinance",          # Options: alpha_vantage, yfinance
    "news_data": "yfinance",                 # Options: alpha_vantage, yfinance
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

REPLACE WITH:
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gemini-3.1-pro-preview"
config["quick_think_llm"] = "gemini-3-flash-preview"
config["max_debate_rounds"] = 1

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# Energy market forward propagation
# delivery_period: ISO datetime for the start of the delivery period to analyze
# trade_timestamp: the current trading time (when the analysis is being run)
# market_area: bidding zone (CZ or DE-LU)
_, decision = ta.propagate("2026-05-04", "2026-05-04T14:00", market_area="CZ")
print(decision)
```

### Step 7.3 — (Issue 5.4) Fix `_log_state` path construction bug

**File**: `tradingagents/graph/trading_graph.py`

FIND:
```python
        directory = Path(self.config["results_dir"] + self.ticker + "TradingAgentsStrategy_logs")
```

REPLACE WITH:
```python
        directory = Path(self.config["results_dir"]) / self.ticker / "TradingAgentsStrategy_logs"
```

**Why**: The original code concatenates strings without path separators, producing paths like `/path/to/logs2024-06-15_CZTradingAgentsStrategy_logs`. The fix uses `Path` / operator to insert proper OS-appropriate separators, matching the pattern already used in `_log_state_exchange` on line 453.

### Step 7.4 — (Issue 5.5) Remove unused `yfinance` import

**File**: `tradingagents/graph/trading_graph.py`

FIND:
```python
import yfinance as yf
```

REPLACE WITH (delete entirely — replace with empty string or a blank line):
```python
```

**Why**: The `yf` import is unused. The `_fetch_returns` method for energy returns `None, None, None` without using yfinance. Removing it eliminates an unnecessary dependency.

### Step 7.5 — (Issue 5.6) Fix `build_instrument_context()` for energy markets

**File**: `tradingagents/agents/utils/agent_utils.py`

FIND:
```python
def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )
```

REPLACE WITH:
```python
def build_instrument_context(ticker: str) -> str:
    """Describe the instrument or delivery period for agents to reference.

    For energy markets, the 'ticker' is the delivery_period identifier
    (e.g. '2024-06-15' or '2024-06-15T14:00'). For stock markets, it's
    the ticker symbol (e.g. 'NVDA', 'AAPL.TO').
    """
    # Detect if this looks like an energy delivery period (date-like) or a stock ticker
    if any(c.isdigit() and "-" in ticker for c in [ticker]):
        return (
            f"The delivery period to analyze is `{ticker}`. "
            "Use this identifier in every tool call and report."
        )
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )
```

**WAIT** — the detection logic above is fragile. Let me provide a simpler, more robust version:

ACTUALLY REPLACE WITH:
```python
def build_instrument_context(ticker: str) -> str:
    """Describe the instrument or delivery period for agents to reference.

    For energy markets, the 'ticker' field carries the delivery_period
    identifier (e.g. '2024-06-15' or '2024-06-15T14:00').
    For stock markets, it's the ticker symbol (e.g. 'NVDA').
    """
    # Simple heuristic: dates contain '-' and start with a digit
    if ticker and ticker[0].isdigit() and "-" in ticker:
        return (
            f"The delivery period to analyze is `{ticker}`. "
            "Use this identifier in every tool call and report."
        )
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )
```

### Step 7.6 — (Issue 5.7) Remove `_exchange` dead code from all agent files

Every agent file has a `create_*_exchange()` function that is the original stock-market version. These are dead code — never called from anywhere (only the non-`_exchange` versions are imported in `__init__.py` and used by `setup.py`). They import stock tools that add confusion.

**This is a bulk operation across 12 files.** For each file, delete the `create_*_exchange` function entirely (from its `def` line to the line before the next top-level `def` or end of file).

#### 7.6a — `tradingagents/agents/analysts/market_analyst.py`

FIND (lines 79-156, the entire `create_market_analyst_exchange` function):
```python
def create_market_analyst_exchange(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke({"messages": state["messages"]})

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
```

DELETE this entire function (replace with empty string).

Also remove the now-unused stock tool imports at the top of the file:

FIND:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_stock_data,
)
```

REPLACE WITH:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
```

#### 7.6b — `tradingagents/agents/analysts/social_media_analyst.py`

DELETE the entire `create_social_media_analyst_exchange` function (lines 72-123).

Also fix the imports at the top:

FIND:
```python
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction, get_news
```

REPLACE WITH:
```python
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
```

#### 7.6c — `tradingagents/agents/analysts/news_analyst.py`

DELETE the entire `create_news_analyst_exchange` function (lines 51-102).

Also fix the imports at the top:

FIND:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)
```

REPLACE WITH:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
```

#### 7.6d — `tradingagents/agents/analysts/fundamentals_analyst.py`

DELETE the entire `create_fundamentals_analyst_exchange` function (lines 14-69).

Also fix the imports at the top:

FIND:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
)
```

REPLACE WITH:
```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
```

#### 7.6e — `tradingagents/agents/researchers/bull_researcher.py`

DELETE the entire `create_bull_researcher_exchange` function (lines 3-49).

#### 7.6f — `tradingagents/agents/researchers/bear_researcher.py`

DELETE the entire `create_bear_researcher_exchange` function (lines 3-51).

#### 7.6g — `tradingagents/agents/managers/research_manager.py`

DELETE the entire `create_research_manager_exchange` function (lines 13-64).

#### 7.6h — `tradingagents/agents/managers/portfolio_manager.py`

DELETE the entire `create_portfolio_manager_exchange` function (lines 24-92).

#### 7.6i — `tradingagents/agents/trader/trader.py`

DELETE the entire `create_trader_exchange` function (lines 17-61).

Also fix the imports — `TraderProposal` and `render_trader_proposal` were only used by the exchange version:

FIND:
```python
import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import PowerTraderProposal, render_power_trader_proposal
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
```

**Note**: Verify that `TraderProposal` and `render_trader_proposal` are NOT imported in this file. Looking at the actual file, the import is `from tradingagents.agents.schemas import PowerTraderProposal, render_power_trader_proposal` — this is the energy version and IS used by the remaining `create_trader()` function. So the import is fine. Just delete the `create_trader_exchange` function body.

#### 7.6j — `tradingagents/agents/risk_mgmt/aggressive_debator.py`

DELETE the entire `create_aggressive_debator_exchange` function (lines 3-54).

#### 7.6k — `tradingagents/agents/risk_mgmt/conservative_debator.py`

DELETE the entire `create_conservative_debator_exchange` function (lines 3-55).

#### 7.6l — `tradingagents/agents/risk_mgmt/neutral_debator.py`

DELETE the entire `create_neutral_debator_exchange` function (lines 3-53).

### Step 7.7 — Clean up unused stock tool imports in `agent_utils.py`

After removing all `_exchange` functions, the stock tool imports in `agent_utils.py` are only needed if any remaining code uses them. Since all `_exchange` functions are deleted, check if anything else imports these tools.

**File**: `tradingagents/agents/utils/agent_utils.py`

The stock tool imports at the top of the file are:
```python
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
```

After Step 7.6, these are no longer imported by any analyst file. **However**, the `_exchange` versions of the agents imported them via `agent_utils.py` (e.g., `from tradingagents.agents.utils.agent_utils import get_stock_data`). Now that all `_exchange` functions are deleted, these imports are dead.

**BUT**: Before deleting, verify nothing else uses them. The `trading_graph.py` has them commented out (lines 49-60). The `interface.py` imports them directly from their own modules. So they can be safely removed from `agent_utils.py`.

FIND (lines 1-20 of `agent_utils.py`):
```python
from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
```

REPLACE WITH:
```python
from langchain_core.messages import HumanMessage, RemoveMessage
```

### Step 7.8 — (Issue 5.1) Residual load column naming — INFORMATIONAL, NO CHANGE

The implementation plan notes that `query_residual_load` in `entsoe_client.py` has a subtle column naming issue (Solar MW column comes from generation forecast but function is labeled "Residual Load Actual"). This is a cosmetic issue. **No change required** — just be aware of it.

---

## EXECUTION ORDER

Apply changes in this order to minimize merge conflicts:

1. **BUG-5** (Steps 1.1-1.3) — `default_config.py` only, simple text swaps
2. **BUG-6** (Step 2.1) — `entsoe_client.py`, replace one function
3. **BUG-7** (Steps 3.1-3.6) — `energy_news_tools.py`, `setup.py`, `trading_graph.py`, `news_analyst.py`
4. **Part V Step 7.7** (agent_utils.py cleanup) — Do this BEFORE Part II since Part II modifies `agent_utils.py`
5. **Part V Step 7.6** (dead code removal) — All agent files
6. **Part V Steps 7.1-7.5** (file-level fixes) — Various files
7. **Part II** (Steps 4.1-4.7) — `agent_states.py`, `trading_graph.py`, `agent_utils.py`, all 4 analyst files
8. **Part III** (Step 5.1) — `energy_price_tools.py`, `setup.py`, `trading_graph.py`, `default_config.py`
9. **Part IV** (Steps 6.1-6.4) — All 4 analyst prompt files

---

## POST-IMPLEMENTATION VERIFICATION CHECKLIST

After all changes, run the system and verify:

- [ ] No `Vendor 'entsoe' does not support method` warnings for `get_intraday_prices` or `get_intraday_auction_prices`
- [ ] `get_intraday_prices` for CZ returns real OTE data (not a stub string)
- [ ] News analyst makes tool calls to 4 tools (outages, actual load, cross-border flows, load forecast)
- [ ] Second analyst (System State) sees Price & Technical Analyst's findings in its messages
- [ ] Third analyst (News) sees both previous analysts' findings
- [ ] Fourth analyst (Weather) sees all three previous analysts' findings
- [ ] `get_intraday_prices_period` is available to the Price & Technical Analyst
- [ ] Report labels in saved reports say "Price & Technical Analyst" not "Market Analyst"
- [ ] `main.py` runs with energy parameters (no NVDA reference)
- [ ] Log file paths have proper separators (not concatenated strings)
- [ ] No `import yfinance` in `trading_graph.py`
- [ ] No `create_*_exchange` functions remain in any agent file
- [ ] No stock tool imports (`get_stock_data`, `get_indicators`, etc.) in `agent_utils.py`
