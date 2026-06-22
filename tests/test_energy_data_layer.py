"""Tests for the energy data layer (Phase 1).

These tests connect to real APIs:
- ENTSO-E (requires ENTSO_E_API_KEY env var)
- OTE (no auth required)
- SMARD (no auth required)
- Open-Meteo (no auth required)

Run with: pytest tests/test_energy_data_layer.py -v
"""

import os
import pytest
from datetime import datetime, timedelta
import pandas as pd


# Test data - use a recent date with known data availability
TEST_DATE = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
TEST_MARKET_AREA = "CZ"
TEST_CZ_AREA = "CZ"


class TestEntsoeClient:
    """Test ENTSO-E data client with real API calls."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure ENTSO_E_API_KEY is set or skip tests."""
        api_key = os.environ.get("ENTSOE_API_KEY")
        if not api_key:
            pytest.skip("ENTSO_E_API_KEY not set - skipping integration test")
        self.api_key = api_key

    def test_day_ahead_prices(self):
        """Test fetching day-ahead prices from ENTSO-E."""
        from tradingagents.dataflows.entsoe_client import query_day_ahead_prices

        result = query_day_ahead_prices(TEST_DATE, TEST_MARKET_AREA)

        assert "Day-Ahead Prices" in result
        assert TEST_MARKET_AREA in result
        assert "EUR/MWh" in result
        # Should have 24 hours of data
        lines = [l for l in result.split('\n') if l.strip() and not l.startswith('#')]
        assert len(lines) >= 24

    def test_day_ahead_prices_cz(self):
        """Test fetching day-ahead prices for Czech market."""
        from tradingagents.dataflows.entsoe_client import query_day_ahead_prices

        result = query_day_ahead_prices(TEST_DATE, TEST_CZ_AREA)

        assert "Day-Ahead Prices" in result
        assert TEST_CZ_AREA in result

    def test_wind_solar_forecast(self):
        """Test fetching wind and solar forecasts."""
        from tradingagents.dataflows.entsoe_client import query_solar_forecast

        result = query_solar_forecast(TEST_DATE, TEST_MARKET_AREA)

        assert "Wind" in result or "Solar" in result
        assert "MW" in result

    def test_load_forecast(self):
        """Test fetching load forecast."""
        from tradingagents.dataflows.entsoe_client import query_load_forecast

        result = query_load_forecast(TEST_DATE, TEST_MARKET_AREA)

        assert "Load" in result
        assert "MW" in result
        lines = [l for l in result.split('\n') if l.strip() and not l.startswith('#')]
        assert len(lines) >= 24

    def test_residual_load(self):
        """Test residual load calculation."""
        from tradingagents.dataflows.entsoe_client import query_residual_load

        result = query_residual_load(TEST_DATE, TEST_MARKET_AREA)

        assert "Residual Load" in result
        assert "MW" in result

    def test_crossborder_flows(self):
        """Test cross-border flows data."""
        from tradingagents.dataflows.entsoe_client import query_crossborder_flows

        result = query_crossborder_flows(TEST_DATE, TEST_MARKET_AREA)

        assert "Cross-Border" in result or "MW" in result

    def test_imbalance_prices(self):
        """Test imbalance prices."""
        from tradingagents.dataflows.entsoe_client import query_imbalance_prices

        result = query_imbalance_prices(TEST_DATE, TEST_MARKET_AREA)

        # May not have data for all dates
        assert "Imbalance" in result


class TestOteClient:
    """Test OTE Czech market client."""

    def test_dam_prices(self):
        """Test fetching Czech day-ahead prices."""
        from tradingagents.dataflows.ote_client import get_dam_prices

        result = get_dam_prices(TEST_DATE, in_eur=True)

        assert "Day-Ahead Prices" in result or "CZ" in result
        # OTE should return 24 hours
        lines = [l for l in result.split('\n') if l.strip() and not l.startswith('#')]
        assert len(lines) >= 1

    def test_intraday_prices(self):
        """Test fetching Czech intraday prices."""
        from tradingagents.dataflows.ote_client import get_intraday_prices

        result = get_intraday_prices(TEST_DATE)

        assert "Intraday" in result or "CZ" in result

    def test_intraday_prices_period(self):
        """Test fetching Czech intraday 15-min prices."""
        from tradingagents.dataflows.ote_client import get_intraday_prices_period

        result = get_intraday_prices_period(TEST_DATE)

        assert "Intraday" in result or "CZ" in result or "15" in result


class TestSmardClient:
    """Test SMARD German data client."""

    def test_german_generation(self):
        """Test fetching German generation by type."""
        from tradingagents.dataflows.smard_client import get_german_generation

        result = get_german_generation(TEST_DATE, resolution="hour")

        assert "German" in result or "Generation" in result
        assert "MW" in result
        lines = [l for l in result.split('\n') if l.strip() and not l.startswith('#')]
        # Should have at least some hours
        assert len(lines) >= 1

    def test_german_residual_load(self):
        """Test fetching German residual load."""
        from tradingagents.dataflows.smard_client import get_german_residual_load

        result = get_german_residual_load(TEST_DATE, resolution="hour")

        assert "Residual" in result or "German" in result

    def test_german_total_load(self):
        """Test fetching German total load."""
        from tradingagents.dataflows.smard_client import get_german_total_load

        result = get_german_total_load(TEST_DATE, resolution="hour")

        assert "Load" in result or "German" in result


class TestWeatherClient:
    """Test Open-Meteo weather client."""

    def test_wind_forecast(self):
        """Test fetching wind forecast."""
        from tradingagents.dataflows.weather_client import get_wind_forecast

        result = get_wind_forecast(TEST_DATE, TEST_MARKET_AREA)

        assert "Wind" in result
        assert "m/s" in result

    def test_solar_forecast(self):
        """Test fetching solar forecast."""
        from tradingagents.dataflows.weather_client import get_solar_forecast

        result = get_solar_forecast(TEST_DATE, TEST_MARKET_AREA)

        assert "Solar" in result or "Radiation" in result

    def test_weather_forecast(self):
        """Test fetching general weather."""
        from tradingagents.dataflows.weather_client import get_weather_forecast

        result = get_weather_forecast(TEST_DATE, TEST_MARKET_AREA)

        assert "Temperature" in result or "Weather" in result

    def test_historical_forecast(self):
        """Test historical forecast for backtesting."""
        from tradingagents.dataflows.weather_client import get_historical_forecast

        issue_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        result = get_historical_forecast(TEST_DATE, issue_date, TEST_MARKET_AREA)

        assert "Historical" in result or "Forecast" in result


class TestMockEnergy:
    """Test synthetic data generation (no external dependencies)."""

    def test_generate_day_ahead_prices(self):
        """Test synthetic DA price generation."""
        from tradingagents.dataflows.mock_energy import generate_day_ahead_prices

        result = generate_day_ahead_prices(TEST_DATE, TEST_MARKET_AREA, seed=42)

        assert "Day-Ahead Prices" in result
        assert TEST_MARKET_AREA in result
        assert "EUR/MWh" in result
        # Check we have 24 hours
        lines = [l for l in result.split('\n') if l.strip() and not l.startswith('#')]
        assert len(lines) == 25  # header + 24 hours

    def test_generate_intraday_prices(self):
        """Test synthetic intraday price generation."""
        from tradingagents.dataflows.mock_energy import generate_intraday_prices

        result = generate_intraday_prices(TEST_DATE, TEST_MARKET_AREA, seed=42)

        assert "Intraday" in result
        assert "EUR/MWh" in result

    def test_generate_wind_solar_forecast(self):
        """Test synthetic renewable forecast."""
        from tradingagents.dataflows.mock_energy import generate_wind_solar_forecast

        result = generate_wind_solar_forecast(TEST_DATE, TEST_MARKET_AREA, seed=42)

        assert "Wind" in result
        assert "Solar" in result
        assert "MW" in result

    def test_generate_load_forecast(self):
        """Test synthetic load forecast."""
        from tradingagents.dataflows.mock_energy import generate_load_forecast

        result = generate_load_forecast(TEST_DATE, TEST_MARKET_AREA, seed=42)

        assert "Load" in result
        assert "MW" in result

    def test_generate_residual_load(self):
        """Test synthetic residual load."""
        from tradingagents.dataflows.mock_energy import generate_residual_load

        result = generate_residual_load(TEST_DATE, TEST_MARKET_AREA, seed=42)

        assert "Residual" in result
        assert "MW" in result

    def test_seed_reproducibility(self):
        """Test that same seed produces same output."""
        from tradingagents.dataflows.mock_energy import generate_day_ahead_prices

        result1 = generate_day_ahead_prices(TEST_DATE, TEST_MARKET_AREA, seed=12345)
        result2 = generate_day_ahead_prices(TEST_DATE, TEST_MARKET_AREA, seed=12345)

        assert result1 == result2

    def test_different_seeds_different_output(self):
        """Test that different seeds produce different output."""
        from tradingagents.dataflows.mock_energy import generate_day_ahead_prices

        result1 = generate_day_ahead_prices(TEST_DATE, TEST_MARKET_AREA, seed=11111)
        result2 = generate_day_ahead_prices(TEST_DATE, TEST_MARKET_AREA, seed=99999)

        assert result1 != result2


class TestEnergyUtils:
    """Test utility functions."""

    def test_get_entsoe_area_code(self):
        """Test ENTSO-E area code lookup."""
        from tradingagents.dataflows.energy_utils import get_entsoe_area_code

        assert get_entsoe_area_code("DE-LU") == "10Y1001A1001A82H"
        assert get_entsoe_area_code("CZ") == "10YCZ-CEPS-----N"

    def test_get_entsoe_area_code_invalid(self):
        """Test invalid market area raises error."""
        from tradingagents.dataflows.energy_utils import get_entsoe_area_code

        with pytest.raises(ValueError):
            get_entsoe_area_code("INVALID")

    def test_delivery_date_to_entsoe_period(self):
        """Test date to ENTSO-E period conversion."""
        from tradingagents.dataflows.energy_utils import delivery_date_to_entsoe_period

        start, end = delivery_date_to_entsoe_period("2024-06-15")

        assert start.year == 2024
        assert start.month == 6
        assert start.day == 15
        assert end.day == 16

    def test_parse_delivery_period_hourly(self):
        """Test parsing hourly delivery period."""
        from tradingagents.dataflows.energy_utils import parse_delivery_period

        start, end = parse_delivery_period("2024-06-15T14:00")

        assert start.hour == 14
        assert end.hour == 15
        assert (end - start).total_seconds() == 3600

    def test_parse_delivery_period_quarterhour(self):
        """Test parsing quarter-hourly delivery period."""
        from tradingagents.dataflows.energy_utils import parse_delivery_period

        start, end = parse_delivery_period("2024-06-15T14:00/PT15M")

        assert start.hour == 14
        assert end.minute == 15
        assert (end - start).total_seconds() == 900


class TestCacheLayer:
    """Test caching functionality."""

    def test_cache_path_generation(self):
        """Test cache path building."""
        from tradingagents.dataflows.energy_utils import get_cache_path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = get_cache_path("entsoe", "day_ahead_prices", "DE-LU", "2024-06-15", tmpdir)

            assert "entsoe" in path
            assert "DE-LU" in path
            assert "day_ahead_prices" in path
            assert "2024-06-15" in path
            assert path.endswith(".parquet")

    def test_cache_save_and_load(self):
        """Test saving and loading from cache."""
        from tradingagents.dataflows import cache_layer

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test DataFrame
            df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

            # Save to cache
            cache_layer.save_to_cache(df, "test", "query", "DE-LU", "2024-06-15")

            # Load from cache
            loaded = cache_layer.load_cached("test", "query", "DE-LU", "2024-06-15")

            assert loaded is not None
            assert list(loaded.columns) == ["a", "b"]
            assert len(loaded) == 3


class TestInterfaceRouting:
    """Test vendor routing in interface.py."""

    def test_energy_tools_categories_defined(self):
        """Test that energy tool categories exist."""
        from tradingagents.dataflows.interface import TOOLS_CATEGORIES

        assert "price_data" in TOOLS_CATEGORIES
        assert "system_data" in TOOLS_CATEGORIES
        assert "weather_data" in TOOLS_CATEGORIES

    def test_energy_vendor_methods_defined(self):
        """Test that energy vendor methods exist."""
        from tradingagents.dataflows.interface import VENDOR_METHODS

        assert "get_day_ahead_prices" in VENDOR_METHODS
        assert "get_wind_forecast" in VENDOR_METHODS
        assert "get_residual_load" in VENDOR_METHODS

    def test_price_routing_to_entsoe(self):
        """Test price data routes to entsoe by default."""
        from tradingagents.dataflows.interface import get_vendor

        vendor = get_vendor("price_data")
        assert "entsoe" in vendor

    def test_weather_routing_to_openmeteo(self):
        """Test weather data routes to openmeteo by default."""
        from tradingagents.dataflows.interface import get_vendor

        vendor = get_vendor("weather_data")
        assert "openmeteo" in vendor


class TestDefaultConfig:
    """Test configuration defaults."""

    def test_energy_config_present(self):
        """Test energy-specific config keys exist."""
        from tradingagents.default_config import DEFAULT_CONFIG

        assert "market_area" in DEFAULT_CONFIG
        assert "delivery_resolution" in DEFAULT_CONFIG
        assert "trading_horizon" in DEFAULT_CONFIG

    def test_default_market_area(self):
        """Test default market area is DE-LU."""
        from tradingagents.default_config import DEFAULT_CONFIG

        assert DEFAULT_CONFIG["market_area"] == "DE-LU"

    def test_data_vendors_config(self):
        """Test data vendors config structure."""
        from tradingagents.default_config import DEFAULT_CONFIG

        assert "data_vendors" in DEFAULT_CONFIG
        assert "price_data" in DEFAULT_CONFIG["data_vendors"]
        assert "system_data" in DEFAULT_CONFIG["data_vendors"]
        assert "weather_data" in DEFAULT_CONFIG["data_vendors"]

    def test_tool_vendors_config(self):
        """Test tool-level vendor overrides."""
        from tradingagents.default_config import DEFAULT_CONFIG

        assert "tool_vendors" in DEFAULT_CONFIG
        assert "get_day_ahead_prices" in DEFAULT_CONFIG["tool_vendors"]
