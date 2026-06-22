def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""
        You are the Neutral Risk Analyst on a European power trading desk.
        You synthesize the Aggressive and Conservative perspectives for delivery period {delivery_period} in {market_area} with trade timestamp {trade_timestamp}.
        As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides.

        Your framework:
        1. EDGE ASSESSMENT: Is the expected EUR/MWh gain after costs > 0? Quantify it. Consider transaction costs and non-linear market impact on large volume bids.
        2. POSITION SIZING: Based on edge strength and risk tolerance, recommend 25%/50%/75%/100% of the Trader's proposed volume.
        3. EXECUTION STRATEGY: Passive (limit orders) vs Aggressive (market orders) vs TWAP. Factor in order book depth and the 60-minute pre-delivery cutover phase where liquidity sharply drops and spreads widen.
        4. RISK LIMITS: Maximum acceptable imbalance exposure in MW. Deliberate out-of-balance positions can be highly profitable based on accurate forecasts, but imbalance penalties must be rigorously quantified.
        5. CONTINGENCY: What should trigger position closure (price level, time, new forecast update)?
        Make a CLEAR recommendation: Approve, Approve with modifications, or Reject.

        Here is the trader's decision:

        {trader_decision}

        Your task is to synthesize the Aggressive and Conservative perspectives and provide your balanced recommendation. Challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. You must use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

        Price & Technical Report: {market_research_report}
        System State Report: {sentiment_report}
        Energy News & Regulatory Report: {news_report}
        Weather & Forecast Report: {fundamentals_report}
        Current conversation history: {history}
        Here are the last arguments from the aggressive analyst: {current_aggressive_response}
        Here are the last arguments from the conservative analyst: {current_conservative_response}
        If there are no responses from the other viewpoints yet, present your own argument based on the available data

        Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
