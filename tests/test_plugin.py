"""Tests for plugin wiring and metadata."""

from __future__ import annotations

from unittest.mock import patch

from az_scout_latency_stats import LatencyStatsPlugin
from az_scout_latency_stats.tools import intra_region_latency, region_latency


class TestLatencyStatsPlugin:
    """Unit tests for LatencyStatsPlugin."""

    def test_get_router_prewarms_once_and_is_lazy(self) -> None:
        with (
            patch("az_scout_latency_stats.cloud63.prewarm_cloud63") as cloud63_prewarm_mock,
            patch("az_scout_latency_stats.intra_zone.prewarm_intra_zone") as intra_prewarm_mock,
        ):
            plugin = LatencyStatsPlugin()
            cloud63_prewarm_mock.assert_not_called()
            intra_prewarm_mock.assert_not_called()

            router1 = plugin.get_router()
            router2 = plugin.get_router()

        assert router1 is not None
        assert router2 is not None
        assert router1 is router2
        cloud63_prewarm_mock.assert_called_once()
        intra_prewarm_mock.assert_called_once()

    def test_tab_id_matches_plugin_slug(self) -> None:
        plugin = LatencyStatsPlugin()

        tabs = plugin.get_tabs()

        assert tabs is not None
        assert len(tabs) == 1
        assert tabs[0].id == "latency-stats"

    def test_system_prompt_addendum_mentions_tool_and_sources(self) -> None:
        plugin = LatencyStatsPlugin()

        addendum = plugin.get_system_prompt_addendum()

        assert addendum is not None
        assert "region_latency" in addendum
        assert "intra_region_latency" in addendum
        assert "physical" in addendum.lower()
        assert "azuredocs" in addendum
        assert "cloud63" in addendum

    def test_get_mcp_tools_includes_inter_and_intra_tools(self) -> None:
        plugin = LatencyStatsPlugin()

        tools = plugin.get_mcp_tools()

        assert tools is not None
        assert region_latency in tools
        assert intra_region_latency in tools
