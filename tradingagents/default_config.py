import os

_TRADINGAGENTS_HOME = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
# _TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    "log_level": "INFO",
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "google",
    "deep_think_llm": "gemini-3.1-pro-preview",
    "quick_think_llm": "gemini-3-flash-preview",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None, # "high", "minimal", etc.
    "openai_reasoning_effort": None, # "medium", "high", "low"
    "anthropic_effort": None, # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": True,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 5,
    "max_risk_discuss_rounds": 5,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        # Stock data (legacy)
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
        # Energy data (new)
        "price_data": "entsoe,ote,smard",
        "system_data": "entsoe,ote,smard",
        "weather_data": "openmeteo",
        "market_fundamentals": "entsoe,ote,smard",
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Energy-specific overrides
        "get_outage_notifications": "entsoe",
        "get_actual_load": "entsoe,smard",
        "get_day_ahead_prices": "entsoe,ote,smard",
        "get_intraday_prices": "ote",
        "get_intraday_auction_prices": "ote",
        "get_balancing_data": "entsoe,ote",
        "get_residual_load": "entsoe,ote",
        "get_actual_generation": "entsoe,smard",
        "get_load_forecast": "entsoe,smard",
        "get_cross_border_flows": "entsoe",
        "get_historical_forecast": "openmeteo",
        "get_wind_forecast": "openmeteo",
        "get_solar_forecast": "openmeteo",
        "get_generation_forecast": "entsoe,smard",
        "get_forecast_updates": "entsoe",
        "get_weather_forecast": "openmeteo",
    },
    # Energy market specific configuration
    "market_area": "CZ",  # Primary bidding zone ("DE-LU" or "CZ")
    "delivery_resolution": "60min",  # "60min" or "15min"
    "trading_horizon": "intraday",  # "day_ahead" | "intraday" | "both"
    "weather_provider": "open_meteo",
    # OTE-specific config
    "ote_soap_url": "http://www.ote-cr.cz/services/PublicDataService",
    # SMARD config
    "smard_base_url": "https://www.smard.de/app/chart_data",
}