# Detailed Coding Plan — BUG-4: Fix Inter-Analyst Context Flow

**Purpose**: Step-by-step, copy-paste-ready instructions for a coding agent. Every change specifies the exact file, the exact old text to find, and the exact new text to replace it with.

**Repository**: `JackPieCZ/TradingAgents-private` (latest main branch, commit `834482b` or later)

**Convention**: Each step uses a `FIND → REPLACE` block. The agent should open the file, find the **exact** `FIND` text (character-for-character, including whitespace), and replace it with the `REPLACE WITH` text. If the `FIND` text cannot be found exactly, STOP and report the mismatch — do NOT guess.

---

## PROBLEM STATEMENT

The four energy analysts run in sequence:
1. **Price & Technical Analyst** (`market_analyst.py`)
2. **System State Analyst** (`social_media_analyst.py`)
3. **Energy News & Regulatory Analyst** (`news_analyst.py`)
4. **Weather & Forecast Analyst** (`fundamentals_analyst.py`)

After each analyst finishes, a `Msg Clear` node (from `create_msg_delete()` in `agent_utils.py`) **wipes ALL messages** and replaces them with a single `HumanMessage(content="Continue")`. This means:
- Analyst #2 has **zero** context from Analyst #1
- Analyst #3 has **zero** context from Analysts #1 and #2
- Analyst #4 has **zero** context from any previous analyst

Each analyst works in complete isolation, unable to cross-reference findings (e.g., the Weather analyst can't say "the price spike the Price Analyst found correlates with the wind forecast drop I see").

## SOLUTION DESIGN

We add a new `analyst_context: str` field to `AgentState` that **accumulates** a truncated summary from each analyst. Each subsequent analyst sees this accumulated context injected into the `HumanMessage` placeholder that replaces the wiped messages. The full reports remain stored in their individual fields (`market_report`, `sentiment_report`, etc.) for downstream agents.

**Data flow after fix:**
```
Analyst #1 runs → writes report to market_report, appends summary to analyst_context
    ↓
Msg Clear #1 → wipes messages, creates placeholder WITH analyst_context content
    ↓
Analyst #2 starts → sees Analyst #1's summary in its first message
    ↓
Analyst #2 runs → writes report to sentiment_report, appends summary to analyst_context
    ↓
Msg Clear #2 → wipes messages, creates placeholder WITH Analyst #1 + #2 summaries
    ↓
... and so on for Analysts #3 and #4
```

**Why this is safe:**
- `analyst_context` is a plain `str` field in LangGraph's `AgentState`, so "last write wins" (no reducer needed).
- During an analyst's tool-call loop, `report` is `""` (empty), so `analyst_context` is returned unchanged (existing value). Only the **final** invocation (when `result.tool_calls` is empty) appends the new summary. This means no double-appending.
- The `Msg Clear` node only **reads** `analyst_context` — it does **not** write to it. So there's no conflict between the analyst's write and the delete node.
- Each summary is truncated to 1500 characters to prevent token budget explosion. The full report remains in the dedicated field.

---

## FILES MODIFIED (6 files)

| # | File | What Changes |
|---|------|-------------|
| 1 | `tradingagents/agents/utils/agent_states.py` | Add `analyst_context` field to `AgentState` |
| 2 | `tradingagents/graph/propagation.py` | Initialize `analyst_context` to `""` in `create_initial_state()` |
| 3 | `tradingagents/agents/utils/agent_utils.py` | Modify `create_msg_delete()` to inject `analyst_context` into placeholder |
| 4 | `tradingagents/agents/analysts/market_analyst.py` | Append summary to `analyst_context` after report |
| 5 | `tradingagents/agents/analysts/social_media_analyst.py` | Append summary to `analyst_context` after report |
| 6 | `tradingagents/agents/analysts/news_analyst.py` | Append summary to `analyst_context` after report |
| 7 | `tradingagents/agents/analysts/fundamentals_analyst.py` | Append summary to `analyst_context` after report |

**Note**: Analyst #4 (Weather & Forecast) also appends to `analyst_context` even though no subsequent analyst reads it. This is deliberate — it makes the code uniform and future-proof if analysts are reordered or new ones added.

---

## STEP-BY-STEP INSTRUCTIONS

### Step 1 — Add `analyst_context` field to `AgentState`

**File**: `tradingagents/agents/utils/agent_states.py`
**Line**: 46–56 (the `AgentState` class definition)

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

**What changed**: Added a single field `analyst_context: Annotated[str, "..."]` between `sender` and the research step fields. This field will hold the concatenated summaries from all analysts that have run so far.

**Verification after this step**: Run this command from the repo root:
```bash
python -c "from tradingagents.agents.utils.agent_states import AgentState; print('analyst_context' in AgentState.__annotations__); print('OK')"
```
Expected output:
```
True
OK
```

---

### Step 2 — Initialize `analyst_context` to `""` in `create_initial_state()`

**File**: `tradingagents/graph/propagation.py`
**Line**: 68–71 (inside the `create_initial_state` method's return dict)

**IMPORTANT**: This is in `propagation.py`, NOT in `trading_graph.py`. The `trading_graph.py` file calls `self.propagator.create_initial_state()` which is defined in `propagation.py`.

FIND:
```python
            # Reports initialized empty
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
```

REPLACE WITH:
```python
            # Inter-analyst context (accumulated findings passed between analysts)
            "analyst_context": "",
            # Reports initialized empty
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
```

**What changed**: Added `"analyst_context": "",` as a new key in the initial state dictionary, immediately before the report fields. This ensures the field exists when the first analyst tries to read it via `state.get("analyst_context", "")`.

**Verification after this step**: Run:
```bash
python -c "
from tradingagents.graph.propagation import Propagator
p = Propagator()
state = p.create_initial_state('2024-06-15T14:00', '2024-06-14T10:00')
assert 'analyst_context' in state, 'analyst_context not in state!'
assert state['analyst_context'] == '', 'analyst_context not empty!'
print('OK')
"
```
Expected output: `OK`

---

### Step 3 — Modify `create_msg_delete()` to inject analyst context into placeholder

**File**: `tradingagents/agents/utils/agent_utils.py`
**Line**: 45–57 (the entire `create_msg_delete` function)

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
        """Clear messages but inject accumulated analyst context for the next analyst.

        After each analyst finishes, this node wipes the message history (to keep
        token counts manageable) but injects a summary of all previous analysts'
        findings into the placeholder message so the next analyst has cross-analyst
        context.
        """
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Build context summary from previous analysts' findings
        context = state.get("analyst_context", "")
        if context:
            placeholder_text = (
                "Previous analysts have reported the following key findings:\n\n"
                f"{context}\n\n"
                "Use these findings as context for your own analysis. "
                "Continue with your assigned tools."
            )
        else:
            placeholder_text = "Continue"

        placeholder = HumanMessage(content=placeholder_text)

        return {"messages": removal_operations + [placeholder]}

    return delete_messages
```

**What changed**:
1. The function now reads `state.get("analyst_context", "")` to get the accumulated findings.
2. If `analyst_context` is non-empty, the placeholder message contains a preamble ("Previous analysts have reported...") followed by the concatenated summaries, followed by an instruction to continue.
3. If `analyst_context` is empty (i.e., for the first analyst, before any summaries exist), the placeholder is just `"Continue"` as before — so Analyst #1 behavior is unchanged.
4. The `Msg Clear` node does NOT write to `analyst_context` — it only reads it. The `analyst_context` writes happen in the analyst return dicts (Steps 4–7).

**Why `state.get("analyst_context", "")` with a default**: Defensive coding. If somehow `analyst_context` isn't in the state (e.g., old state dicts from before this change), it falls back to `""` and produces the old `"Continue"` placeholder. This makes the change backward-compatible.

---

### Step 4 — Market Analyst (Analyst #1): Append summary to `analyst_context`

**File**: `tradingagents/agents/analysts/market_analyst.py`
**Line**: 185–189 (inside the `create_market_analyst` function, the return dict of the inner `market_analyst_node`)

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
        # Append a brief summary to analyst_context for subsequent analysts.
        # Only appends when report is non-empty (i.e., final invocation, not mid-tool-loop).
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                "--- Price & Technical Analyst ---\n"
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

**What changed**:
1. Before returning, we read the current `analyst_context` from state.
2. If `report` is non-empty (meaning the LLM produced a final text response, not a tool call), we append a labeled, truncated version of the report (`[:1500]` chars) to the existing context.
3. If `report` is empty (meaning the LLM made a tool call and will be invoked again), we pass through `existing_context` unchanged — no double-appending.
4. The return dict now includes `"analyst_context": new_context` alongside the existing fields.

**Why `[:1500]` truncation**: The full report can be thousands of characters. We only need the key findings for cross-referencing. The full report is still stored in `market_report` for downstream agents (Bull/Bear researchers, Research Manager, etc.).

**Edge case — `state.get("analyst_context", "")` returns `""` here**: Yes, because this is the FIRST analyst. The `analyst_context` was initialized to `""` in Step 2. After this step, `analyst_context` will contain the Market Analyst's summary for the next analyst.

---

### Step 5 — System State Analyst (Analyst #2): Append summary to `analyst_context`

**File**: `tradingagents/agents/analysts/social_media_analyst.py`
**Line**: 151–155 (inside the `create_social_media_analyst` function, the return dict of the inner `social_media_analyst_node`)

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
        # Append a brief summary to analyst_context for subsequent analysts.
        # Only appends when report is non-empty (i.e., final invocation, not mid-tool-loop).
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                "--- System State Analyst ---\n"
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

**What changed**: Identical pattern to Step 4, but:
- The label says `"--- System State Analyst ---"` instead of `"--- Price & Technical Analyst ---"`
- The report field is `sentiment_report` (unchanged from before)
- When this analyst finishes, `analyst_context` will contain BOTH the Market Analyst's summary (from Step 4) AND this analyst's summary

---

### Step 6 — News Analyst (Analyst #3): Append summary to `analyst_context`

**File**: `tradingagents/agents/analysts/news_analyst.py`
**Line**: 131–135 (inside the `create_news_analyst` function, the return dict of the inner `news_analyst_node`)

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
        # Append a brief summary to analyst_context for subsequent analysts.
        # Only appends when report is non-empty (i.e., final invocation, not mid-tool-loop).
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                "--- Energy News & Regulatory Analyst ---\n"
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

**What changed**: Same pattern. Label is `"--- Energy News & Regulatory Analyst ---"`. When this analyst finishes, `analyst_context` will contain summaries from Analysts #1, #2, and #3.

---

### Step 7 — Weather & Forecast Analyst (Analyst #4): Append summary to `analyst_context`

**File**: `tradingagents/agents/analysts/fundamentals_analyst.py`
**Line**: 153–157 (inside the `create_fundamentals_analyst` function, the return dict of the inner `fundamentals_analyst_node`)

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
        # Append a brief summary to analyst_context for subsequent analysts.
        # Only appends when report is non-empty (i.e., final invocation, not mid-tool-loop).
        existing_context = state.get("analyst_context", "")
        if report:
            context_addition = (
                "--- Weather & Forecast Analyst ---\n"
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

**What changed**: Same pattern. Label is `"--- Weather & Forecast Analyst ---"`. Even though no subsequent analyst reads this (Weather is the last analyst before Bull Researcher), the Bull/Bear researchers and other downstream agents could theoretically benefit from `analyst_context` in the future.

---

## EXECUTION ORDER

Apply changes in exactly this order:

1. **Step 1** — `agent_states.py` (add field to type definition)
2. **Step 2** — `propagation.py` (initialize field in state dict)
3. **Step 3** — `agent_utils.py` (modify `create_msg_delete`)
4. **Step 4** — `market_analyst.py` (first analyst appends)
5. **Step 5** — `social_media_analyst.py` (second analyst appends)
6. **Step 6** — `news_analyst.py` (third analyst appends)
7. **Step 7** — `fundamentals_analyst.py` (fourth analyst appends)

**Why this order matters**: Step 1 must come first because Steps 4-7 write to the `analyst_context` field that Step 1 defines. Step 2 must come before any execution because the initial state needs the field. Step 3 must come before Steps 4-7 in execution (though file edits can be in any order) because the `Msg Clear` node runs between analysts.

---

## POST-IMPLEMENTATION VERIFICATION

### Quick Syntax Check

Run from the repo root:
```bash
python -c "
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.graph.propagation import Propagator
from tradingagents.agents.utils.agent_utils import create_msg_delete

# 1. Verify analyst_context is in AgentState
assert 'analyst_context' in AgentState.__annotations__, 'FAIL: analyst_context not in AgentState'
print('PASS: analyst_context field exists in AgentState')

# 2. Verify initial state includes analyst_context
p = Propagator()
state = p.create_initial_state('2024-06-15T14:00', '2024-06-14T10:00')
assert 'analyst_context' in state, 'FAIL: analyst_context not in initial state'
assert state['analyst_context'] == '', 'FAIL: analyst_context not empty in initial state'
print('PASS: analyst_context initialized to empty string')

# 3. Verify create_msg_delete reads analyst_context
from langchain_core.messages import HumanMessage
delete_fn = create_msg_delete()

# Simulate state with no context (first analyst)
mock_state_empty = {
    'messages': [HumanMessage(content='test', id='msg1')],
    'analyst_context': '',
}
result_empty = delete_fn(mock_state_empty)
# Should just say 'Continue'
placeholder_msgs = [m for m in result_empty['messages'] if isinstance(m, HumanMessage)]
assert len(placeholder_msgs) == 1, 'FAIL: expected exactly one placeholder HumanMessage'
assert placeholder_msgs[0].content == 'Continue', f'FAIL: expected Continue, got: {placeholder_msgs[0].content[:50]}'
print('PASS: empty analyst_context produces Continue placeholder')

# Simulate state with context (second+ analyst)
mock_state_with_context = {
    'messages': [HumanMessage(content='test', id='msg2')],
    'analyst_context': '--- Price & Technical Analyst ---\nDay-ahead price: 85 EUR/MWh\n',
}
result_ctx = delete_fn(mock_state_with_context)
placeholder_msgs_ctx = [m for m in result_ctx['messages'] if isinstance(m, HumanMessage)]
assert len(placeholder_msgs_ctx) == 1, 'FAIL: expected exactly one placeholder HumanMessage'
assert 'Previous analysts' in placeholder_msgs_ctx[0].content, 'FAIL: placeholder missing context preamble'
assert 'Price & Technical Analyst' in placeholder_msgs_ctx[0].content, 'FAIL: placeholder missing analyst label'
print('PASS: non-empty analyst_context injects findings into placeholder')

print()
print('ALL CHECKS PASSED')
"
```

Expected output:
```
PASS: analyst_context field exists in AgentState
PASS: analyst_context initialized to empty string
PASS: empty analyst_context produces Continue placeholder
PASS: non-empty analyst_context injects findings into placeholder

ALL CHECKS PASSED
```

### Runtime Behavior Check

After running the full pipeline with real or mock LLMs, verify in the logs or output:
- [ ] Analyst #2 (System State) receives a `HumanMessage` containing `"--- Price & Technical Analyst ---"` and a summary of prices/technical findings
- [ ] Analyst #3 (News) receives a `HumanMessage` containing BOTH `"--- Price & Technical Analyst ---"` AND `"--- System State Analyst ---"` summaries
- [ ] Analyst #4 (Weather) receives a `HumanMessage` containing ALL THREE previous analyst summaries
- [ ] Analyst #1 (Market) still receives `"Continue"` as before (no regression)
- [ ] Full reports in `market_report`, `sentiment_report`, `news_report`, `fundamentals_report` are unchanged and complete (not truncated)
- [ ] No `KeyError` for `analyst_context` anywhere in the pipeline

---

## TROUBLESHOOTING

**Problem**: `KeyError: 'analyst_context'` during runtime
**Cause**: Step 2 was not applied — the initial state doesn't include the field.
**Fix**: Verify `propagation.py` has `"analyst_context": "",` in the `create_initial_state()` return dict.

**Problem**: Analyst #2 still only sees `"Continue"` — no cross-analyst context
**Cause**: Either Step 3 was not applied (the `create_msg_delete` still uses the old code) or Step 4 was not applied (Market Analyst doesn't write to `analyst_context`).
**Fix**: Check both `agent_utils.py` (Step 3) and `market_analyst.py` (Step 4).

**Problem**: `analyst_context` contains duplicate entries (same analyst's summary appears twice)
**Cause**: The `if report:` guard in Steps 4-7 isn't working — possibly the `report` variable logic was altered.
**Fix**: Verify that the line `report = result.content if len(result.tool_calls) == 0 else ""` is still present and unmodified in each analyst file. During tool-call iterations, `report` should be `""`, and the `if report:` block should be skipped.

**Problem**: Token budget explosion — analyst context grows too large
**Cause**: Reports are very long and even the `[:1500]` truncation isn't enough.
**Fix**: Reduce the truncation limit from `1500` to `800` or `500` in Steps 4-7. Search for `report[:1500]` in all four analyst files and replace with `report[:800]`.
