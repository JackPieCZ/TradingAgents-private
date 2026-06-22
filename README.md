# TradingAgents Energy

**Multi-Agent LLM Framework for European Electricity Intraday Trading**

A fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) adapted for European power markets. Uses a team of specialized AI agents to analyze electricity market data, debate trading opportunities, and produce structured trading decisions for intraday continuous and IDA auction markets.

```diff
+ Total Lines Added (+)   : 24,695
- Total Lines Deleted (-) : 6,795
```
For the full summary of changes see ([CHANGELOG.md](https://github.com/JackPieCZ/TradingAgents-Energy/blob/main/CHANGELOG.md))

Built on the TradingAgents architecture ([arXiv:2412.20138v7](https://arxiv.org/abs/2412.20138v7)) with domain adaptations informed by 27 academic papers on intraday electricity price formation, forecast-driven trading, and market microstructure.

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

---

## Architecture

The framework orchestrates a pipeline of specialized agents, each backed by real European energy market data:

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

### Analyst Team

The Analyst Team runs four specialized agents in sequence. Each agent appends a concise summary to
a shared `analyst_context` field so that later analysts can see what earlier analysts discovered —
without carrying the full message history forward.

**1. Weather & Forecast Analyst** (`fundamentals_analyst.py`) — *most important agent; primary alpha source*

Computes the **forecast revision delta**: the change in wind/solar generation forecasts between the
day-ahead auction and the current intraday timestamp. A positive wind revision (more wind than
priced in) is a downward price signal; a negative revision is upward. The magnitude is interpreted
relative to the merit order steepness reported by the System State Analyst. Runs last so it has
full context from all three preceding analysts.

Tools: `get_wind_forecast`, `get_solar_forecast`, `get_generation_forecast`, `get_forecast_updates`, `get_weather_forecast`, `get_historical_forecast`

References: `Kup22` (forecast revision trading strategy — primary alpha source), `Kie17` (forecast error → price impact), `Hir22` (fundamental drivers of price distribution)

> **Market-specific note:** For CZ, solar is the dominant variable (~2.5 GW installed); wind is
> negligible (~350 MW). For DE-LU, both wind (~65 GW onshore + ~8 GW offshore) and solar
> (~80 GW) are material and must be assessed independently.

---

**2. System State Analyst** (`social_media_analyst.py`) — *grid fundamentals replace social sentiment*

Analyses residual load (load minus wind minus solar), actual generation by fuel type, and
cross-border flow positions to classify the current market regime (normal / stressed /
oversupplied). When conventional capacity is tight, the same forecast shock has a much larger price
impact — this agent flags that non-linearity. Reads the Price & Technical summary from
`analyst_context` before forming conclusions.

Tools: `get_residual_load`, `get_actual_generation`, `get_load_forecast`, `get_cross_border_flows`, `get_outage_notifications`, `get_actual_load`

References: `Kie17` (demand-quote regime, merit order slope), `Kre21b` (merit order slope), `Kri20` (cross-border flows)

---

**3. Energy News & Regulatory Analyst** (`news_analyst.py`) — *event risk and REMIT flags*

Identifies outage announcements, REMIT Urgent Market Messages, and demand surprises by comparing
actual load against the day-ahead forecast. Flags any information that could constitute inside
information under REMIT Article 3. Reads the Price & Technical and System State summaries before
forming conclusions.

Tools: `get_outage_notifications`, `get_actual_load`, `get_load_forecast`, `get_cross_border_flows`

References: `Hie20` (REMIT and outage notification impact)

---

**4. Price & Technical Analyst** (`market_analyst.py`) — *establishes the price anchor*

Retrieves intraday price history and computes the spread between the current intraday price and the
day-ahead settlement. Assesses recent price momentum, mean-reversion potential, and cross-product
signals from adjacent delivery periods. Outputs a price-level summary that anchors all subsequent
analysts.

Tools: `get_day_ahead_prices`, `get_intraday_prices`, `get_intraday_auction_prices`, `get_imbalance_data`

References: `Kre21b` (autoregressive terms, cross-contract features), `Hir22`/`Hir23` (distribution features, cross-product signals), `Kat20` (time-to-delivery volatility)

---

## Supported Markets

| Market | Data Sources | Products |
|--------|-------------|----------|
| **CZ** (Czech Republic) | ENTSO-E, OTE SOAP API, Open-Meteo | DA prices, intraday continuous (VWAP), IDA1/IDA2/IDA3 auctions, imbalance settlement |
| **DE-LU** (Germany/Luxembourg) | ENTSO-E, SMARD, Open-Meteo | DA prices, generation by type, load, residual load, cross-border flows |

**Data sources** (all free, zero-cost stack):

- **ENTSO-E Transparency Platform** — DA prices, generation forecasts, actual generation, load, cross-border flows, outages (REMIT), imbalance prices
- **OTE SOAP API** — Czech DA, intraday continuous, IDA auctions, imbalance settlement
- **SMARD** — German generation by fuel type, load, residual load
- **Open-Meteo** — Wind speed, solar irradiance, temperature, historical forecasts

---

## Installation

### Prerequisites

- Python 3.13+
- An ENTSO-E API key ([follow these steps](https://www.amsleser.no/blog/post/21-obtaining-api-token-from-entso-e), [register here](https://transparency.entsoe.eu/))
- An LLM API key (Google Gemini, OpenAI, Anthropic, or xAI)

### Setup

```bash
# Clone the repository
git clone https://github.com/JackPieCZ/TradingAgents-Energy.git
cd TradingAgents-Energy

# Create and activate conda environment
conda create -n tradingagents python=3.13
conda activate tradingagents

# Install base dependencies
pip install -r requirements.txt

# Install energy-specific dependencies
pip install entsoe-py openmeteo-requests requests-cache retry-requests

# Configure environment variables
cp .env.example .env
# Edit .env and add:
#   ENTSOE_API_KEY=your_key_here
#   GOOGLE_API_KEY=your_key_here   (or OPENAI_API_KEY, ANTHROPIC_API_KEY)
```

### Verify installation

```bash
# Test energy data layer (requires ENTSO-E API key)
python tests/smoketestA.py
```

---

## Quick Start

### Python API

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

load_dotenv()

config = DEFAULT_CONFIG.copy()
config["market_area"] = "CZ"  # or "DE-LU"

ta = TradingAgentsGraph(debug=True, config=config)

# Analyze CZ market for May 4, 2026 delivery
_, decision = ta.propagate(
    delivery_period="2026-05-04",
    trade_timestamp="2026-05-04T14:00",
    market_area="CZ",
)
print(decision)  # e.g., "Sell"
```

### CLI

```bash
python -m cli.main
```

The CLI guides you through:

1. **Delivery date** — which day's delivery periods to analyze
2. **Market area** — CZ or DE-LU
3. **Trade timestamp** — when the analysis is being run
4. **Output language** — for analyst reports
5. **Analyst selection** — which agents to include
6. **Research depth** — number of debate rounds
7. **LLM provider** — Google, OpenAI, Anthropic, or xAI
8. **Model selection** — fast thinker and deep thinker models

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

---

## Configuration

Key configuration options in `default_config.py`:

```python
{
    "market_area": "CZ",           # "CZ" or "DE-LU"
    "delivery_resolution": "60min", # "60min" or "15min"
    "trading_horizon": "intraday",  # "day_ahead" | "intraday" | "both"
    
    # Vendor routing (category-level defaults)
    "data_vendors": {
        "price_data": "entsoe",
        "system_data": "entsoe",
        "weather_data": "openmeteo",
        "market_fundamentals": "smard",
    },
    
    # Tool-level overrides (take precedence)
    "tool_vendors": {
        "get_day_ahead_prices": "entsoe,ote",  # Fallback chain
        "get_intraday_prices": "ote",
        "get_intraday_auction_prices": "ote",
        ...
    },
    
    # LLM settings
    "llm_provider": "google",
    "deep_think_llm": "gemini-3.1-pro-preview",
    "quick_think_llm": "gemini-3-flash-preview",
}
```

---

## Project Structure

```
tradingagents/
├── agents/
│   ├── analysts/
│   │   ├── fundamentals_analyst.py    # Weather & Forecast Analyst
│   │   ├── social_media_analyst.py    # System State Analyst
│   │   ├── news_analyst.py            # Energy News & Regulatory Analyst
│   │   └── market_analyst.py          # Price & Technical Analyst
│   ├── researchers/
│   │   ├── bull_researcher.py         # Argues for LONG positions
│   │   └── bear_researcher.py         # Argues for SHORT/NoTrade
│   ├── risk_mgmt/
│   │   ├── aggressive_debator.py
│   │   ├── conservative_debator.py
│   │   └── neutral_debator.py
│   ├── managers/
│   │   ├── research_manager.py        # Synthesizes debate → plan
│   │   └── portfolio_manager.py       # Final decision
│   ├── trader/
│   │   └── trader.py                  # Execution proposal
│   ├── schemas.py                     # Power trading schemas
│   └── utils/
│       ├── agent_states.py            # LangGraph state definition
│       ├── energy_price_tools.py      # Price data tools
│       ├── system_data_tools.py       # Grid state tools
│       ├── weather_tools.py           # Weather/forecast tools
│       ├── energy_news_tools.py       # News/outage tools
│       └── cross_reference_tools.py   # Multi-vendor validation
├── dataflows/
│   ├── interface.py                   # Vendor routing layer
│   ├── entsoe_client.py              # ENTSO-E Transparency API
│   ├── ote_client.py                 # Czech OTE SOAP API
│   ├── smard_client.py               # German SMARD API
│   ├── weather_client.py             # Open-Meteo API
│   ├── cache_layer.py                # Parquet caching
│   ├── energy_utils.py               # CET/CEST timezone handling
│   └── mock_energy.py                # Synthetic test data
├── graph/
│   ├── trading_graph.py              # Main orchestrator
│   ├── setup.py                      # Graph construction
│   ├── propagation.py                # State initialization
│   ├── conditional_logic.py          # Flow control
│   ├── signal_processing.py          # Rating extraction
│   └── reflection.py                 # Decision reflection
└── default_config.py                 # Configuration defaults
```

---

## Domain Concepts

For readers familiar with equity trading but new to power markets:

| Equity Concept | Power Market Equivalent |
|---|---|
| Ticker symbol | Delivery period (e.g., 2026-05-04T14:00) |
| Earnings surprise | Renewable forecast revision delta |
| P/E ratio | Residual load / available conventional capacity |
| Social sentiment | Weather forecasts and forecast deltas |
| Insider transaction | REMIT urgent market message (UMM) |
| Daily Buy/Hold/Sell | Per-delivery-period position signal |
| Alpha vs S&P 500 | Net trading value vs DA settlement price |
| Transaction cost | Spread + market impact + imbalance settlement cost |

---

## Research Papers

The agent prompts encode domain knowledge from these key papers:

- **Kup22** — Forecast revision trading strategy (primary alpha source)
- **Kie17** — Demand-quote regime and forecast error impact
- **Kre21b** — Feature set and merit order slope
- **Hir22/Hir23** — Distribution features and cross-product signals
- **Kat20** — Execution costs and market impact modeling
- **Nar21/Nar22** — Balancing market dynamics
- **Bun18** — Selective trading and transaction cost awareness
- **Ber17** — Czech intraday market specifics and autoregressive features
- **Féron20** — Intraday price formation and optimal trading
- **Hie20** — REMIT and outage notification impact

Full paper list and citations available in `research/Sources_Power_trading_transition_from_algo_finance.md`.

---

## Credits

- Original framework: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — [arXiv:2412.20138v7](https://arxiv.org/abs/2412.20138v7)
- Energy adaptation: Jakub Kolář

## License

See [LICENSE](LICENSE) for terms.
