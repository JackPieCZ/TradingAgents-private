def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        prompt = f"""You are the Bearish Researcher (arguing FOR a SHORT/SELL position or NoTrade) on a European
electricity intraday trading desk.
You are analyzing the {market_area} market for delivery period {delivery_period} with trade timestamp {trade_timestamp}.
Given the analyst reports, argue for going SHORT (selling power for this delivery period) or choosing NoTrade, based on if any of
these conditions hold:
1. FORECAST REVISION SIGNAL: Wind/solar forecast revised upward → more renewable supply →
   prices should fall below day-ahead level. Highlight the risk of negative prices in an oversupplied regime, especially if the density/skewness of the forecast indicates asymmetric downside risk.
2. EXECUTION RISK: Thin liquidity, wide bid-ask spreads, or time pressure (e.g., approaching the XBID cutover phase) → 
   the temporary and permanent market impact of building and closing a position may eat the theoretical edge.
3. IMBALANCE EXPOSURE: If the position cannot be fully closed before gate closure, the
   imbalance penalty may severely exceed the expected profit.
4. REGIME UNCERTAINTY: Volatile regime with conflicting signals → the safest action may be
   NoTrade rather than taking directional risk.
Counter the Bull's arguments with evidence from the analyst reports. Be specific about risks in
EUR/MWh terms, MW volumes, transaction costs, and market impact.
You must evaluate the following analyst reports:
Price & Technical Report: {market_research_report}
System State Report: {sentiment_report}
Energy News & Regulatory Report: {news_report}
Weather & Forecast Report {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of taking a long position.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
