from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import copy
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

config = copy.deepcopy(DEFAULT_CONFIG)
config["llm_provider"] = "google"
config["deep_think_llm"] = "gemini-3.1-pro-preview"
config["quick_think_llm"] = "gemini-3-flash-preview"

graph = TradingAgentsGraph(config=config)
state, signal = graph.propagate(
    delivery_period="2026-05-01",
    trade_timestamp="2026-04-30T18:00",
    market_area="CZ"
)

# Verify all reports populated
assert state["market_report"] != "", "Market report empty"
assert state["sentiment_report"] != "", "Sentiment report empty"
assert state["news_report"] != "", "News report empty"
assert state["fundamentals_report"] != "", "Fundamentals report empty"
assert state["final_trade_decision"] != "", "Final decision empty"

# Verify power fields present
assert state.get("delivery_period") == "2026-05-01"
assert state.get("market_area") == "CZ"

# Verify signal extraction works with power actions
print(f"State: {state}")
print(f"Signal: {signal}")
print("SMOKE TEST PASSED")