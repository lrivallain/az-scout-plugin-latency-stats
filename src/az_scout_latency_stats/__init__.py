"""az-scout latency stats plugin.

Provides inter-region latency data based on Microsoft published statistics,
an API endpoint to compute pairwise latency matrices, an MCP tool, and a
D3.js graph visualisation showing regions as nodes with latency edges.
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

    def get_router(self) -> APIRouter | None:
        """Return API routes for latency data."""
        from az_scout_latency_stats.routes import router

        return router

    def get_mcp_tools(self) -> list[Callable[..., Any]] | None:
        """Return MCP tool functions for latency queries."""
        from az_scout_latency_stats.tools import region_latency

        return [region_latency]

    def get_static_dir(self) -> Path | None:
        """Return path to static assets directory."""
        return _STATIC_DIR

    def get_tabs(self) -> list[TabDefinition] | None:
        """Return UI tab definitions."""
        return [
            TabDefinition(
                id="latency",
                label="Latency",
                icon="bi bi-diagram-3",
                js_entry="js/latency-tab.js",
                css_entry="css/latency.css",
            )
        ]

    def get_chat_modes(self) -> list[ChatMode] | None:
        """Return chat mode definitions, or None to skip."""
        return None


# Module-level instance — referenced by the entry point
plugin = LatencyStatsPlugin()
