"""az-scout latency stats plugin.

Provides inter-region latency data based on Microsoft published statistics,
an API endpoint to compute pairwise latency matrices, an MCP tool, and a
D3.js world map visualisation showing regions positioned geographically
with great-circle latency arcs.
"""

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

from az_scout.plugin_api import ChatMode, TabDefinition
from fastapi import APIRouter

_STATIC_DIR = Path(__file__).parent / "static"

try:
    __version__ = _pkg_version("az-scout-plugin-latency-stats")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


class LatencyStatsPlugin:
    """Azure inter-region latency statistics plugin for az-scout."""

    name = "latency-stats"
    version = __version__

    def __init__(self) -> None:
        self._prewarmed = False

    def get_router(self) -> APIRouter | None:
        """Return API routes for latency data."""
        if not self._prewarmed:
            from az_scout_latency_stats.cloud63 import prewarm_cloud63
            from az_scout_latency_stats.intra_zone import prewarm_intra_zone

            prewarm_cloud63()
            prewarm_intra_zone()
            self._prewarmed = True

        from az_scout_latency_stats.routes import router

        return router

    def get_mcp_tools(self) -> list[Callable[..., Any]] | None:
        """Return MCP tool functions for latency queries."""
        from az_scout_latency_stats.tools import intra_region_latency, region_latency

        return [region_latency, intra_region_latency]

    def get_static_dir(self) -> Path | None:
        """Return path to static assets directory."""
        return _STATIC_DIR

    def get_tabs(self) -> list[TabDefinition] | None:
        """Return UI tab definitions."""
        return [
            TabDefinition(
                id="latency-stats",
                label="Latency",
                icon="bi bi-globe-americas",
                js_entry="js/latency-tab.js",
                css_entry="css/latency.css",
            )
        ]

    def get_system_prompt_addendum(self) -> str | None:
        """Return extra guidance for the default discussion chat mode."""
        return (
            "For inter-region latency questions, use the region_latency tool. "
            "It supports two data sources: 'azuredocs' (Microsoft published stats) "
            "and 'cloud63' (crowd-sourced measurements from the Azure Latency Test project). "
            "Default to 'azuredocs' unless the user asks for cloud63 data. "
            "For intra-region (Availability Zone) latency questions, use the "
            "intra_region_latency tool. IMPORTANT: this tool returns latency "
            "between PHYSICAL AZs (az1, az2, az3), which are the same across "
            "all subscriptions. Do NOT remap them through logical-to-physical "
            "zone mappings. Present zone names exactly as returned by the tool."
        )

    def get_chat_modes(self) -> list[ChatMode] | None:
        """Return chat mode definitions, or None to skip."""
        return None


# Module-level instance — referenced by the entry point
plugin = LatencyStatsPlugin()
