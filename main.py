from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gemini-3.1-pro-preview"  # Use a different model
config["quick_think_llm"] = "gemini-3-flash-preview"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
# Energy market forward propagation
# delivery_period: ISO datetime for the start of the delivery period to analyze
# trade_timestamp: the current trading time (when the analysis is being run)
# market_area: bidding zone (CZ or DE-LU)
_, decision = ta.propagate("2026-05-04", "2026-05-04T14:00", market_area="CZ")
print(decision)
