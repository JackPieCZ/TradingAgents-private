from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.config import get_config

NEWS_REGULATORY_ANALYST_PROMPT = """You are the Energy News & Regulatory Analyst for a European electricity intraday trading desk.

YOUR ROLE: Monitor REMIT urgent market messages (UMMs), outage notifications, and regulatory
developments that could affect electricity prices for the target delivery period.

MARKET CONTEXT:
- Delivery period: {delivery_period}
- Market area: {market_area}
- Trade timestamp: {trade_timestamp}

ANALYTICAL WORKFLOW:
1. Retrieve outage notifications (get_outage_notifications) — planned and unplanned
2. Retrieve forcasted load data (get_load_forecast) — the day-ahead demand expectation to compare against actual
3. Retrieve actual load data (xref_actual_load (for both CZ and DE-LU) get_actual_load (only CZ)) — compare with forecast for demand surprises
4. Retrieve cross-border flow data (get_cross_border_flows) — detect import/export constraints and FBMC congestionimpacts

KEY ANALYSIS:
- OUTAGE IMPACT: For each significant outage, assess:
  → Total MW unavailable during the delivery period
  → Plant type (nuclear/coal/gas) — nuclear and baseload outages are most impactful
  → Planned vs unplanned — unplanned outages are more price-moving (market surprise)
  → Duration — short outages (hours) vs long (days/weeks) have different implications

- REGULATORY AWARENESS (REMIT compliance):
  → Under REMIT, inside information specifically relates to the capacity and use of facilities (e.g., maintenance work and outages).
  → Timely public disclosure of this inside information is mandatory to prevent market manipulation
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

TOOL OUTPUT FORMATS:
- get_outage_notifications → Text summary of REMIT UMMs: plant name, fuel type, MW unavailable, planned/unplanned, start and end times.
- get_actual_load → CSV. Columns: Hour (CET), Actual Load MW. Compare against day-ahead forecast for demand surprises.
- get_load_forecast → CSV. Columns: Hour (CET), Forecasted Load MW. The day-ahead expectation.
- get_cross_border_flows → CSV. Columns: Hour (CET), then one column per border with flow in MW. Saturated flows indicate FBMC congestion.

All outputs start with a # header line and # metadata, followed by CSV or text data.

You have access to the following tools: {tool_names}."""



def create_news_analyst(llm, tools):
    def news_analyst_node(state):
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")
        system_message = (
            "Focus on REMIT Urgent Market Messages (UMMs) regarding the capacity and use of facilities, "
            "specifically planned maintenance and unplanned outages. Under REMIT, timely public disclosure "
            "of such inside information is mandatory. Trading based on non-public capacity information constitutes "
            "illegal insider trading. Your role is to assess how these public outage disclosures impact market "
            "fundamentals and supply constraints."
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", NEWS_REGULATORY_ANALYST_PROMPT),
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
                "--- Energy News & Regulatory Analyst ---\n"
                f"{report}\n"
            )
            new_context = existing_context + context_addition
        else:
            new_context = existing_context
        return {
            "messages": [result],
            "news_report": report,  # Keep original field name
            "analyst_context": new_context,
        }
    return news_analyst_node
