"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PowerTraderProposal, render_power_pm_decision, PowerPortfolioDecision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PowerPortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")

        prompt = f"""You are the Portfolio Manager making the final trading decision for delivery period {delivery_period} in {market_area}.
        with trade timestamp: {trade_timestamp}

        Review the Trader's proposal and the Risk Team's debate. Make your final decision considering:

        1. REGIME-APPROPRIATE SIZING:
        - Normal regime: standard position sizes, moderate conviction needed
        - Stressed regime: smaller positions (risk of extreme moves), but higher expected returns
        - Oversupplied: can be larger (downside bounded by floor price), but negative prices have limits
        - Volatile: smallest positions or NoTrade unless signal is unambiguous

        2. MARKET-APPROPRIATE SIZING:
        - CZ: Market is ~60x less liquid than DE. A 10 MW order in CZ has proportionally 60x the market impact of 10 MW in DE. For CZ: Typical range 1-10 MW. The CZ notice-board market makes closing positions harder - factor in exit liquidity.
        - DE-LU: Standard range 5-30 MW. EPEX continuous provides adequate depth for these sizes.

        3. MEAN-REVERSION TIME HORIZON (CZ only):
        - Within 24h: Hurst ≈ 0.42 → nearly random, do NOT count on same-day reversion
        - Over 25-240h: Hurst ≈ 0.19 → strong mean reversion, multi-day trends WILL revert
        - Implication: if taking a mean-reversion position in CZ, set a multi-day time horizon, not an intraday one. For intraday, only trade on FUNDAMENTAL signals (forecast deltas).

        4. PORTFOLIO CONTEXT:
        - Current position across ALL delivery periods (not just this one)
        - Net imbalance exposure — total MW at risk if markets move against us
        - Correlation between adjacent delivery hours (a long H14 and long H15 doubles exposure)


        3. YOUR DECISION must include:
        - Regime assessment: Normal/Stressed/Oversupplied/Volatile
        - Action: Buy/Sell/Hold/Reduce/NoTrade
        - Executive summary and Investment rationale grounded in specific evidence from the analysts
        - Execution strategy: passive/aggressive/iceberg/twap/IDA
        - Volume in MW
        - Price target in EUR/MWh
        - Stop loss in EUR/MWh
        - Maximum imbalance exposure you'll accept
        - Time horizon for mean reversion in hours (if applicable) + urgency level (low/medium/high) based on time to delivery and signal decay rate

        REMEMBER: The goal is NET TRADING VALUE after all costs. A clever NoTrade decision on a marginal signal is worth more than a losing trade on a noisy signal.

        **Context:**
        - Research Manager's investment plan: **{research_plan}**
        - Trader's transaction proposal: **{trader_plan}**
        {lessons_line}
        
        **Analyst Reports:**
        --- Price & Technical Analyst ---
        {state.get('market_report', 'N/A')}

        --- System State Analyst ---
        {state.get('sentiment_report', 'N/A')}

        --- Energy News & Regulatory Analyst ---
        {state.get('news_report', 'N/A')}

        --- Weather & Forecast Analyst ---
        {state.get('fundamentals_report', 'N/A')}

        **Risk Analysts Debate History:**
        {history}

        Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_power_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
