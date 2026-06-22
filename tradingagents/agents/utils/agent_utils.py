from venv import logger

from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the instrument or delivery period for agents to reference.

    For energy markets, the 'ticker' is the delivery_period identifier
    (e.g. '2024-06-15' or '2024-06-15T14:00'). For stock markets, it's
    the ticker symbol (e.g. 'NVDA', 'AAPL.TO').
    """
    # Detect if this looks like an energy delivery period (date-like) or a stock ticker
    if ticker and ticker[0].isdigit() and "-" in ticker:
        logger.info("Identified energy market context based on ticker format. Using delivery period instruction.")
        return (
            f"The delivery period to analyze is `{ticker}`. "
            "Use this identifier in every tool call and report."
        )
    logger.info("Identified stock market context based on ticker format. Using exchange-qualified ticker instruction.")
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages but inject accumulated analyst context for the next analyst.

        After each analyst finishes, this node wipes the message history (to keep
        token counts manageable) but injects a summary of all previous analysts'
        findings into the placeholder message so the next analyst has cross-analyst
        context.
        """
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Build context summary from previous analysts' findings
        context = state.get("analyst_context", "")
        if context:
            placeholder_text = (
                "Previous analysts have reported the following key findings:\n\n"
                f"{context}\n\n"
                "Use these findings as context for your own analysis. Continue with your assigned tools."
            )
        else:
            placeholder_text = "Continue"

        placeholder = HumanMessage(content=placeholder_text)

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
