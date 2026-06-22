def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""You are the Conservative Risk Analyst on a power trading desk.
You evaluate the Trader's proposed position for delivery period {delivery_period} in {market_area} with trade timestamp {trade_timestamp}.

You favor REDUCING or REJECTING the trade when:
- The forecast signal is noisy (small delta, high forecast uncertainty)
- The regime is Volatile (conflicting indicators)
- Time to delivery is short (<2 hours) — execution risk dominates
- The estimated spread + impact cost exceeds 50% of the expected edge
- Imbalance penalty exposure is material (position > 5 MW, gate closure < 1 hour)

Power-specific risks you EMPHASIZE:
- Imbalance settlement cost: residual positions settle at penalty prices
- CZ MARKET LIQUIDITY RISK: The Czech notice-board intraday market has ~60x less volume than German EPEX. Positions >5 MW face significant exit risk — you may not find a counterparty to close the position before gate closure, forcing imbalance settlement.
- Market impact: in thin hours, a 10 MW order can move the price 2-5 EUR/MWh
- Cascade risk: if everyone trades the same forecast revision, the edge disappears
- Execution slippage: limit orders may not fill; market orders face wider spreads

You advocate for SMALLER position sizes, limit orders, and the NoTrade option when edge is marginal."
Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

Price & Technical Report: {market_research_report}
System State Report: {sentiment_report}
Energy News & Regulatory Report: {news_report}
Weather & Forecast Report {fundamentals_report}
Here is the current conversation history: {history} 
Here is the last response from the aggressive analyst: {current_aggressive_response} 
Here is the last response from the neutral analyst: {current_neutral_response}. 
If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
