# TradingAgents/graph/reflection.py

from typing import Any


class Reflector:
    """Handles reflection on trading decisions."""

    def __init__(self, quick_thinking_llm: Any):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm
        self.log_reflection_prompt = self._get_log_reflection_prompt()

    def _get_log_reflection_prompt(self) -> str:
        return (
            "You are a power trading analyst reviewing your own past decision now that the outcome is known.\n"
            "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
            "Cover in order:\n"
            "1. Was the directional call correct? (cite the P&L figure in EUR/MWh)\n"
            "2. Was the regime classification accurate? Did the market behave as the regime predicted?\n"
            "3. One concrete lesson to apply to the next similar delivery period.\n\n"
            "Be specific and terse. Your output will be stored verbatim in a decision log "
            "and re-read by future analysts, so every word must earn its place."
        )

    def reflect_on_final_decision(
        self,
        final_decision: str,
        raw_return: float,
        alpha_return: float,
    ) -> str:
        messages = [
            ("system", self.log_reflection_prompt),
            (
                "human",
                (
                    f"Trade P&L: {raw_return:+.2f} EUR/MWh\n"
                    f"P&L vs day-ahead benchmark: {alpha_return:+.2f} EUR/MWh\n\n"
                    f"Final Decision:\n{final_decision}"
                ),
            ),
        ]
        return self.quick_thinking_llm.invoke(messages).content