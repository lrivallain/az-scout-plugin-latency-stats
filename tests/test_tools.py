"""Tests for MCP tools — mode parameter."""

from __future__ import annotations

import json
import time

from az_scout_latency_stats.tools import intra_region_latency, region_latency


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


class TestIntraRegionLatency:
    """Test intra_region_latency MCP tool."""

    def test_intra_zone_not_loaded_returns_error(self) -> None:
        import az_scout_latency_stats.intra_zone as mod

        with mod._cache_lock:
            mod._intra_zone_loaded = False
            mod._intra_zone_loaded_at = 0.0
            mod._intra_zone_pairs = {}

        result = json.loads(intra_region_latency("westeurope", "az1", "az2"))
        assert "error" in result

    def test_intra_zone_pair_returns_latency(self) -> None:
        import az_scout_latency_stats.intra_zone as mod

        with mod._cache_lock:
            mod._intra_zone_pairs = {("westeurope", "az1", "az2"): 1200.0}
            mod._intra_zone_loaded_at = time.monotonic()
            mod._intra_zone_loaded = True

        result = json.loads(intra_region_latency("westeurope", "az1", "az2"))
        assert result["sourcePhysicalZone"] == "az1"
        assert result["targetPhysicalZone"] == "az2"
        assert result["latencyUsP50"] == 1200.0
        assert result["methodology"] == (
            "P50 RTT (sum of directional medians, microseconds) between physical AZs"
        )

        with mod._cache_lock:
            mod._intra_zone_pairs = {}
            mod._intra_zone_loaded_at = 0.0
            mod._intra_zone_loaded = False

    def test_intra_zone_region_summary(self) -> None:
        import az_scout_latency_stats.intra_zone as mod

        with mod._cache_lock:
            mod._intra_zone_pairs = {
                ("westeurope", "az1", "az2"): 1200.0,
                ("westeurope", "az1", "az3"): 1400.0,
                ("westeurope", "az2", "az3"): 1300.0,
            }
            mod._intra_zone_loaded_at = time.monotonic()
            mod._intra_zone_loaded = True

        result = json.loads(intra_region_latency("westeurope"))
        assert result["region"] == "westeurope"
        assert result["zones"] == ["az1", "az2", "az3"]
        assert len(result["pairs"]) == 3

        with mod._cache_lock:
            mod._intra_zone_pairs = {}
            mod._intra_zone_loaded_at = 0.0
            mod._intra_zone_loaded = False

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
