"""Tests for MCP tools — mode parameter."""

from __future__ import annotations

import json
import time

from az_scout_latency_stats.tools import region_latency


class TestRegionLatencyAzuredocsMode:
    """Test region_latency tool in azuredocs mode."""

    def test_default_mode_is_azuredocs(self) -> None:
        result = json.loads(region_latency("francecentral", "westeurope"))
        assert result["mode"] == "azuredocs"
        assert result["rttMs"] is not None
        assert result["rttMs"] > 0

    def test_explicit_azuredocs_mode(self) -> None:
        result = json.loads(region_latency("francecentral", "westeurope", mode="azuredocs"))
        assert result["mode"] == "azuredocs"

    def test_unknown_pair_returns_null(self) -> None:
        result = json.loads(region_latency("francecentral", "nonexistent", mode="azuredocs"))
        assert result["rttMs"] is None


class TestRegionLatencyCloud63Mode:
    """Test region_latency tool in cloud63 mode."""

    def test_cloud63_not_loaded_returns_error(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        with mod._cache_lock:
            mod._cloud63_loaded = False
            mod._cloud63_loaded_at = 0.0
            mod._cloud63_pairs = {}

        result = json.loads(region_latency("westeurope", "eastus", mode="cloud63"))
        assert "error" in result

    def test_cloud63_loaded_returns_rtt(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        with mod._cache_lock:
            mod._cloud63_pairs = {
                ("westeurope", "eastus"): 75.5,
                ("eastus", "westeurope"): 76.0,
            }
            mod._cloud63_loaded_at = time.monotonic()
            mod._cloud63_loaded = True

        result = json.loads(region_latency("westeurope", "eastus", mode="cloud63"))
        assert result["mode"] == "cloud63"
        assert result["rttMs"] == 152  # 75.5 + 76.0 rounded

        # Tear down
        with mod._cache_lock:
            mod._cloud63_pairs = {}
            mod._cloud63_loaded_at = 0.0
            mod._cloud63_loaded = False

    def test_cloud63_one_way_only_returns_null(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        with mod._cache_lock:
            # Only one direction — should return None
            mod._cloud63_pairs = {("westeurope", "eastus"): 75.5}
            mod._cloud63_loaded_at = time.monotonic()
            mod._cloud63_loaded = True

        result = json.loads(region_latency("westeurope", "eastus", mode="cloud63"))
        assert result["mode"] == "cloud63"
        assert result["rttMs"] is None

        # Tear down
        with mod._cache_lock:
            mod._cloud63_pairs = {}
            mod._cloud63_loaded_at = 0.0
            mod._cloud63_loaded = False
