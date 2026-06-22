"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import PowerTraderProposal, render_power_trader_proposal
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, PowerTraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        delivery_period = state.get("delivery_period", state.get("company_of_interest", ""))
        market_area = state.get("market_area", "CZ")
        trade_timestamp = state.get("trade_date", "")

        messages = [
            {
                "role": "system",
                "content": (
                    f"""You are the Trader on a European electricity intraday trading desk. Based on the Research Manager's plan, propose a specific trade for delivery period {delivery_period}
                    in {market_area} with trade timestamp {trade_timestamp}. 
                    Your proposal MUST specify:
                    1. ACTION: Buy / Sell / Hold / Reduce / NoTrade
                    2. VOLUME: Position size in MW (typical range: 1-30 MW)
                    3. LIMIT PRICE: Maximum price to pay (Buy) or minimum price to accept (Sell) in EUR/MWh
                    4. EXECUTION STRATEGY:
                    - "passive_limit": Place limit orders at favorable prices. Best when time to delivery > 4h.
                    - "aggressive_market": Take available prices immediately. Use when signal is strong and urgent.
                    - "iceberg": Hide large orders by splitting into small visible portions. Use when > 10 MW.
                    - "twap": Spread execution evenly over the remaining trading window.
                    - "ida_submission": Submit limit orders into the next upcoming IDA auction.
                      IDAs freeze the continuous order book and clear at a uniform price across borders, providing massive liquidity. BEST for large positions (>10 MW) where continuous market impact would erode the edge. Check IDA timing
                      relative to delivery — if the next IDA is before your delivery period, use it. If not, fall back to continuous execution.
                    5. URGENCY: low/medium/high based on time to delivery and signal decay rate
                    6. IDA SUBMISSION: Submit limit orders into the next upcoming IDA auction. IDAs freeze the continuous order book and clear at a uniform price. BEST for large positions (>10 MW) where continuous market impact would erode the edge. Zero market impact slippage.
                    EXECUTION COST AWARENESS:
                    - Market impact grows EXPONENTIALLY with order size — not linearly [Kat20]
                    - Never execute >5 MW in a single order book sweep — slice into smaller portions
                    - Even optimized execution barely deviates from TWAP — keep it simple [Kat20]
                    - Index prices (ID1, ID3) are NOT achievable — real execution is always worse [Kat20]
                    - DE-LU: Bid-ask spread 0.5-3 EUR/MWh, impact ~0.5 EUR/MWh per 5 MW in liquid hours
                    - CZ: Notice-board market with MUCH LESS liquidity than EPEX. Expect wider spreads,
                      more difficulty closing positions, and proportionally larger impact per MW.
                    - Gate closure: CZ = 60 min before delivery; DE = 5-30 min (varies by product)
                    - Imbalance penalty: can be 50-500% of DA price in extreme cases
                    IMPORTANT: NoTrade is a valid and valuable decision [Bun18]. If the expected edge after
                    costs is < 1 EUR/MWh, or if the regime is unclear, choosing NoTrade protects capital.
                    Selective trading dramatically improves net P&L vs always-trading strategies."""
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                    f"plan tailored for delivery period {delivery_period} in {market_area}. Use this plan as a foundation for evaluating your next trading decision.\n\n"
                    f"ANALYST REPORTS:\n"
                    f"--- Price & Technical Analyst ---\n{state.get('market_report', 'N/A')}\n\n"
                    f"--- System State Analyst ---\n{state.get('sentiment_report', 'N/A')}\n\n"
                    f"--- Energy News & Regulatory Analyst ---\n{state.get('news_report', 'N/A')}\n\n"
                    f"--- Weather & Forecast Analyst ---\n{state.get('fundamentals_report', 'N/A')}\n\n"
                    f"Proposed Investment Plan: {investment_plan}\n\n"
                    f"Leverage these insights to make an informed and strategic decision."
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_power_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
