"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------
class PowerTradingAction(str, Enum):
    """Trading action for a delivery period."""
    BUY = "Buy"          # Go long / increase long position
    SELL = "Sell"         # Go short / increase short position
    HOLD = "Hold"         # Maintain current position
    REDUCE = "Reduce"     # Reduce existing position (either direction)
    NO_TRADE = "NoTrade"  # Explicitly choose not to trade (distinct from Hold)


class MarketRegime(str, Enum):
    """Current market regime classification."""
    NORMAL = "Normal"
    STRESSED = "Stressed"
    OVERSUPPLIED = "Oversupplied"
    VOLATILE = "Volatile"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PowerTradingAction = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Sell / "
            "Hold / Reduce / NoTrade. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the action."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class PowerTraderProposal(BaseModel):
    """Structured transaction proposal for power intraday trading."""
    action: PowerTradingAction = Field(
        description=(
            "The trading action. Exactly one of: Buy (go long), Sell (go short), "
            "Hold (maintain position), Reduce (decrease existing position), "
            "NoTrade (explicitly choose not to trade this delivery period)."
        )
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analyst reports, forecast "
            "deltas, regime classification, and execution cost assessment. "
            "Two to four sentences."
        )
    )
    volume_mw: Optional[float] = Field(
        default=None,
        description="Position size in MW. Typical range 1-30 MW."
    )
    limit_price_eur: Optional[float] = Field(
        default=None,
        description="Limit price in EUR/MWh. For Buy: max price to pay. For Sell: min price to accept."
    )
    execution_strategy: Optional[str] = Field(
        default=None,
        description=(
            "Execution approach: 'passive_limit' (limit orders, best when >4h to delivery), "
            "'aggressive_market' (take available prices, use when signal is strong/urgent), "
            "'iceberg' (hide large orders in small portions, use when >10 MW), "
            "'twap' (spread execution evenly over remaining window)."
        )
    )
    urgency: Optional[str] = Field(
        default=None,
        description="Urgency level: 'low' (>6h to delivery), 'medium' (2-6h), 'high' (<2h)."
    )
    delivery_period: Optional[str] = Field(
        default=None,
        description="The delivery period this trade targets, e.g. '2024-06-15T14:00'."
    )


def render_power_trader_proposal(proposal: PowerTraderProposal) -> str:
    """Render a PowerTraderProposal to markdown."""
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.volume_mw is not None:
        parts.extend(["", f"**Volume**: {proposal.volume_mw} MW"])
    if proposal.limit_price_eur is not None:
        parts.extend(["", f"**Limit Price**: {proposal.limit_price_eur} EUR/MWh"])
    if proposal.execution_strategy:
        parts.extend(["", f"**Execution Strategy**: {proposal.execution_strategy}"])
    if proposal.urgency:
        parts.extend(["", f"**Urgency**: {proposal.urgency}"])
    if proposal.delivery_period:
        parts.extend(["", f"**Delivery Period**: {proposal.delivery_period}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)



# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PowerPortfolioDecision(BaseModel):
    """Structured output from the Portfolio Manager for power trading."""
    action: PowerTradingAction = Field(
        description=(
            "The final position action. Exactly one of: Buy, Sell, Hold, Reduce, NoTrade. "
            "Based on the risk analysts' debate and regime assessment."
        )
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering the trade rationale, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        )
    )
    regime_assessment: MarketRegime = Field(
        description=(
            "Current market regime: Normal, Stressed, Oversupplied, or Volatile. "
            "Based on the System State Analyst's classification."
        )
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate and reports. Include forecast delta magnitude, regime justification, "
            "and execution cost assessment."
        )
    )
    volume_mw: Optional[float] = Field(
        default=None,
        description="Final approved volume in MW."
    )
    price_target_eur: Optional[float] = Field(
        default=None,
        description="Target price in EUR/MWh."
    )
    stop_loss_eur: Optional[float] = Field(
        default=None,
        description="Stop loss price in EUR/MWh."
    )
    max_imbalance_exposure_mw: Optional[float] = Field(
        default=None,
        description="Maximum acceptable imbalance exposure in MW at gate closure."
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Recommended time horizon, e.g. 'until gate closure' or 'next 2 hours'."
    )


def render_power_pm_decision(decision: PowerPortfolioDecision) -> str:
    """Render a PowerPortfolioDecision to markdown."""
    parts = [
        f"**Action**: {decision.action.value}",
        "",
        f"**Regime**: {decision.regime_assessment.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.volume_mw is not None:
        parts.extend(["", f"**Volume**: {decision.volume_mw} MW"])
    if decision.price_target_eur is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target_eur} EUR/MWh"])
    if decision.stop_loss_eur is not None:
        parts.extend(["", f"**Stop Loss**: {decision.stop_loss_eur} EUR/MWh"])
    if decision.max_imbalance_exposure_mw is not None:
        parts.extend(["", f"**Max Imbalance Exposure**: {decision.max_imbalance_exposure_mw} MW"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)