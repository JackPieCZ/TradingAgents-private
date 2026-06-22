# Changelog

All notable changes to TradingAgents Energy are documented in this file.

This project is a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) adapted for European electricity intraday trading.

## [2.0.0] — 2026-05-05 — Energy Markets Fork

### Added
- **ENTSO-E client** (`tradingagents/dataflows/entsoe_client.py`): 11 query functions covering day-ahead prices, intraday prices, wind/solar forecasts, actual generation, load, cross-border flows, outages (REMIT UMMs), imbalance prices, and residual load. Supports DE-LU and CZ bidding zones. Includes CZK → EUR conversion for CZ imbalance prices.
- **OTE client** (`tradingagents/dataflows/ote_client.py`): Czech market data via raw SOAP XML (no `zeep` dependency). Functions: `get_dam_prices`, `get_intraday_prices`, `get_ida_prices` (IDA1/IDA2/IDA3 auctions), `get_imbalance_settlement`.
- **SMARD client** (`tradingagents/dataflows/smard_client.py`): German generation by fuel type, total load, residual load, generation forecasts, load forecasts, and day-ahead market prices.
- **Open-Meteo client** (`tradingagents/dataflows/weather_client.py`): Wind speed at hub heights (80m/120m), solar irradiance (GHI/DNI/DHI/tilted), general weather (temperature/precipitation/cloud cover/pressure), and historical forecasts for backtesting forecast revision strategies.
- **Parquet-based caching** (`tradingagents/dataflows/cache_layer.py`): `cached_fetch()` stores API responses as `.parquet` files keyed by (source, query, area, date) to avoid redundant calls during backtesting.
- **CET/CEST timezone utilities** (`tradingagents/dataflows/energy_utils.py`): DST-safe datetime handling for European power markets.
- **Mock energy data generator** (`tradingagents/dataflows/mock_energy.py`): Synthetic data with realistic features (negative prices, spikes, seasonal patterns, weekend effects) for testing without API access.
- **Energy-specific tool modules**: `energy_price_tools.py` (4 tools), `system_data_tools.py` (4 tools), `weather_tools.py` (6 tools), `energy_news_tools.py` (2 tools) — all route through `interface.py` → `route_to_vendor()`.
- **Cross-reference tools** (`cross_reference_tools.py`): `route_to_all_vendors()` queries the same method against all available vendors for multi-source data validation.
- **Power-specific Pydantic schemas** (`tradingagents/agents/schemas.py`):
  - `PowerTradingAction` enum: Buy / Sell / Hold / Reduce / NoTrade
  - `MarketRegime` enum: Normal / Stressed / Oversupplied / Volatile
  - `PowerTraderProposal`: volume_mw, limit_price_eur, execution_strategy (passive_limit / aggressive_market / iceberg / twap / ida_submission), urgency, delivery_period
  - `PowerPortfolioDecision`: action, regime_assessment, volume_mw, price_target_eur, stop_loss_eur, max_imbalance_exposure_mw, time_horizon
  - `ResearchPlan`: uses `PowerTradingAction` for recommendation field
- **Inter-analyst context sharing**: `analyst_context` field in `AgentState` accumulates key findings from each analyst. `create_msg_delete()` injects this context into the HumanMessage placeholder between analyst runs, enabling later analysts to see earlier findings without full message history.
- **Power-specific state fields** in `AgentState`: `delivery_period`, `market_area`, `day_ahead_position`, `residual_position`, `regime_indicator`, `analyst_context`.

### Changed
- **Fundamentals Analyst → Weather & Forecast Analyst**: Analyzes renewable generation forecasts, forecast revision deltas (the primary alpha source per Kup22), and weather data. CZ-specific: solar dominance (~2.1 GW), negligible wind (~350 MW). DE-LU: both wind and solar material.
- **Social Media Analyst → System State Analyst**: Analyzes grid fundamentals — residual load, merit order steepness, cross-border flows, outages. Classifies market regime (Normal/Stressed/Oversupplied/Volatile).
- **News Analyst → Energy News & Regulatory Analyst**: Monitors REMIT UMMs, outage notifications, demand surprises, and cross-border congestion.
- **Market Analyst → Price & Technical Analyst**: Analyzes intraday price patterns, spread vs DA, mean-reversion signals (Hurst exponent H ≈ 0.42 for CZ intraday), IDA auction price discovery, and imbalance exposure.
- All analyst prompts rewritten with domain-specific benchmarks from 27 academic papers (Kup22, Kie17, Kre21b, Hir22, Hir23, Kat20, Nar21, Bun18, Ber17, Féron20, etc.).
- Bull/Bear researchers: argue for LONG/SHORT power positions based on forecast revision signals, system stress, mean reversion, cross-border flows, IDA opportunities, and execution feasibility.
- Trader: proposes execution strategy (passive_limit / aggressive_market / iceberg / twap / ida_submission) with MW sizing, limit prices, and urgency based on time-to-delivery.
- Research Manager: synthesizes analyst reports with persistence trap detection for CZ (AR(1) R² = 0.61).
- Portfolio Manager: regime-appropriate sizing, market-appropriate sizing (CZ ~60× less liquid than DE), mean-reversion time horizon guidance, and portfolio context.
- Risk debaters: power-specific risk framing — imbalance exposure, spread costs, gate closure timing, forecast confidence.
- `propagate()` signature: `(delivery_period, trade_timestamp, market_area="CZ")` replaces `(company_name, trade_date)`.
- Analyst execution order: fundamentals → social → news → market (Weather & Forecast first for maximum context cascading).
- `_fetch_returns()` stubbed for energy markets (returns `None` until Phase 7 backtesting implementation).
- State logging updated for power-specific fields (delivery_period, market_area, regime_indicator).
- `default_config.py`: Energy vendor routing at both category and tool level. Market area default "CZ". OTE SOAP URL and SMARD base URL configured.
- Vendor fallback chain: primary vendor → remaining available vendors per method.

### Deprecated
- Stock-market `_exchange()` variants in all agent files retained but unused (for potential backward compatibility).
- `yfinance` / `alpha_vantage` imports in `interface.py` retained but not called by energy pipeline.
- `core_stock_tools.py`, `fundamental_data_tools.py`, `news_data_tools.py`, `technical_indicators_tools.py` retained but unused.

### Fixed
- `_log_state` path construction (missing path separator between results_dir and ticker).
- `get_forecast_updates` re-enabled in `_create_tool_nodes` ToolNode registration.
- ENTSO-E CZ imbalance price conversion from CZK to EUR.
- ENTSO-E forecast column labeling ("Wind Forecast MW" / "Solar Forecast MW") to prevent LLM hallucination.
- Residual load calculation restored (Load − Wind − Solar).

---

## [1.x.x] — Pre-fork (TauricResearch/TradingAgents)

See the [original repository](https://github.com/TauricResearch/TradingAgents) or `CHANGELOG_OLD.md` for the pre-fork changelog covering US equity trading features, CLI implementation, structured output support, checkpoint/resume, and multi-provider LLM support.
