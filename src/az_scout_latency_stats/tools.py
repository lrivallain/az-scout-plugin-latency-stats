"""MCP tools for the latency stats plugin."""

import json


def region_latency(source_region: str, target_region: str) -> str:
    """Return indicative RTT latency between two Azure regions.

    Uses Microsoft published statistics from:
    https://learn.microsoft.com/en-us/azure/networking/azure-network-latency
    """
    from az_scout_latency_stats.latency import get_rtt_ms

    rtt = get_rtt_ms(source_region, target_region)
    result = {
        "sourceRegion": source_region,
        "targetRegion": target_region,
        "rttMs": rtt,
        "source": "https://learn.microsoft.com/en-us/azure/networking/azure-network-latency",
        "disclaimer": (
            "Latency values are indicative and must be validated "
            "with in-tenant measurements."
        ),
    }
    return json.dumps(result, indent=2)
