def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""You are the Aggressive Risk Analyst on a European power trading desk.
You evaluate the Trader's proposed position for delivery period {delivery_period} in {market_area} with trade timestamp {trade_timestamp}.
You favor TAKING the trade when:
- The forecast revision signal is strong (>2 GW wind/solar delta)
- The regime is clear (Stressed or Oversupplied — not ambiguous)
- Time to delivery allows patient execution (>4 hours)
- The edge (expected EUR/MWh gain) exceeds 2x the estimated spread cost
You advocate for LARGER position sizes when the edge is clear, and suggest aggressive execution
(market orders, full volume) when time is short.
Power-specific risks you may DOWNPLAY (but should acknowledge):
- Imbalance exposure if gate closure is far away (deliberate out-of-balance positions can be profitable if forecasted correctly)
- Spread costs in liquid hours (order book depth is stable until 60 mins prior to delivery)
- Mean-reversion in the last 30 minutes of trading
- Price impact on smaller trades, market impact is primarily a concern for large volume shifts
        Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case FOR taking aggressive action or maintaining a larger position by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. You must incorporate insights from the following sources into your arguments:

Price & Technical Report: {market_research_report}
System State Report: {sentiment_report}
Energy News & Regulatory Report: {news_report}
Weather & Forecast Report {fundamentals_report}
Current conversation history: {history} 
Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. 
If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Counter their fears of imbalance penalties or execution slippage with data-driven rebuttals based on the forecast edge. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
