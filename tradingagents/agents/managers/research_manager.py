"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""
        You are the Research Manager synthesizing the analyst reports and bull/bear debate for delivery period {delivery_period} in {market_area} with trade timestamp {trade_timestamp}.
        As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.
        You have four analyst reports:
        1. Weather & Forecast Analyst (fundamentals_report): Forecast revisions, weather data
        2. System State Analyst (sentiment_report): Regime classification, merit order, outages
        3. Price & Technical Analyst (market_report): Price levels, spreads, mean-reversion signals
        4. Energy News & Regulatory Analyst (news_report): Outages, REMIT notifications

        Plus a bull/bear debate with competing perspectives.

        YOUR SYNTHESIS MUST:
        1. Identify the DOMINANT SIGNAL: Which analyst report carries the most weight for this delivery period?
           - For CZ renewable-heavy hours (solar peak 10:00-15:00): Weather & Forecast is primary
           - For CZ peak demand hours (08:00-20:00): System State is primary (merit order steepness)
           - For CZ night hours: any wind signal has outsized impact; Price & Technical useful for mean reversion
           - For DE-LU: Weather & Forecast is almost always primary (wind drives everything)
        2. Assess SIGNAL AGREEMENT: Do the analysts agree on direction? Disagreement = lower conviction.
        3. Resolve the BULL/BEAR DEBATE: Which side has stronger evidence? Be specific about MW and EUR/MWh.
        4. CHECK FOR PERSISTENCE TRAP (CZ only): Most CZ intraday price deviation is autoregressive
           persistence from recent deviations, NOT new fundamental information [Ber17, R²=0.61 from AR term].
           If the Price & Technical Analyst reports a trend, verify whether the Weather & Forecast Analyst
           can explain it with a genuine forecast revision. Pure price-trend signals without fundamental
           backing are unreliable for same-day trades in CZ (Hurst ≈ 0.42 = nearly random within 24h).
        5. Produce a CLEAR RESEARCH PLAN for the Trader:
           - Directional call (bullish/bearish/neutral)
           - Conviction level (high/medium/low)
           - Key delivery hours to focus on
           - Risk factors to monitor

        Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced.

        ANALYST REPORTS:
        --- Price & Technical Analyst ---
        {state.get('market_report', 'N/A')}

        --- System State Analyst ---
        {state.get('sentiment_report', 'N/A')}

        --- Energy News & Regulatory Analyst ---
        {state.get('news_report', 'N/A')}

        --- Weather & Forecast Analyst ---
        {state.get('fundamentals_report', 'N/A')}

        BULL/BEAR DEBATE HISTORY:
        {history}"""

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
