"""MCP tools for the latency stats plugin."""

import json

from az_scout_latency_stats._log import logger

def region_latency(source_region: str, target_region: str, mode: str = "azuredocs") -> str:
    """Return indicative RTT latency between two Azure regions.

    Args:
        source_region: Azure region name (e.g. 'westeurope').
        target_region: Azure region name (e.g. 'eastus').
        mode: Data source — 'azuredocs' (Microsoft published stats) or
              'cloud63' (crowd-sourced from Azure Latency Test project).
    """
    if mode == "cloud63":
        from az_scout_latency_stats.cloud63 import (
            get_cloud63_rtt_ms,
            is_cloud63_loaded,
        )

        if not is_cloud63_loaded():
            return json.dumps(
                {
                    "error": (
                        "Cloud63 data not yet loaded. "
                        "Use the web UI first to trigger the initial fetch, "
                        "or call the /matrix endpoint with mode='cloud63'."
                    ),
                },
                indent=2,
            )

        rtt = get_cloud63_rtt_ms(source_region, target_region)
        result = {
            "sourceRegion": source_region,
            "targetRegion": target_region,
            "rttMs": rtt,
            "mode": "cloud63",
            "source": "https://latency.azure.cloud63.fr/",
            "disclaimer": (
                "Cloud63 latency values are crowd-sourced measurements. "
                "Validate with in-tenant measurements."
            ),
        }
        return json.dumps(result, indent=2)

    from az_scout_latency_stats.latency import get_rtt_ms

    rtt = get_rtt_ms(source_region, target_region)
    result = {
        "sourceRegion": source_region,
        "targetRegion": target_region,
        "rttMs": rtt,
        "mode": "azuredocs",
        "source": "https://learn.microsoft.com/en-us/azure/networking/azure-network-latency",
        "disclaimer": (
            "Latency values are indicative and must be validated with in-tenant measurements."
        ),
    }
    return json.dumps(result, indent=2)
