"""MCP tools for the latency stats plugin."""

import json

from az_scout_latency_stats.metadata import (
    AZUREDOCS_DISCLAIMER,
    AZUREDOCS_SOURCE,
    CLOUD63_DISCLAIMER,
    CLOUD63_SOURCE,
    INTRA_ZONE_DISCLAIMER,
    INTRA_ZONE_METHODOLOGY,
    INTRA_ZONE_SOURCE,
)


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
            "source": CLOUD63_SOURCE,
            "disclaimer": CLOUD63_DISCLAIMER,
        }
        return json.dumps(result, indent=2)

    from az_scout_latency_stats.latency import get_rtt_ms

    rtt = get_rtt_ms(source_region, target_region)
    result = {
        "sourceRegion": source_region,
        "targetRegion": target_region,
        "rttMs": rtt,
        "mode": "azuredocs",
        "source": AZUREDOCS_SOURCE,
        "disclaimer": AZUREDOCS_DISCLAIMER,
    }
    return json.dumps(result, indent=2)


def intra_region_latency(region: str, source_zone: str = "", target_zone: str = "") -> str:
    """Return intra-region PHYSICAL Availability Zone RTT latency (P50 median).

    IMPORTANT: This tool uses PHYSICAL AZ identifiers (az1, az2, az3), NOT
    logical AZs.  Physical AZs are the same for all subscriptions in a region.
    Do NOT apply any logical-to-physical zone mapping to the results.
    Present the zone names exactly as returned (e.g. 'az1', 'az2').

    Args:
        region: Azure region name (e.g. 'westeurope').
        source_zone: Physical AZ identifier (e.g. 'az1'). NOT a logical zone.
        target_zone: Physical AZ identifier (e.g. 'az2'). NOT a logical zone.
    """
    from az_scout_latency_stats.intra_zone import (
        get_intra_zone_latency_us,
        get_intra_zone_matrix,
        is_intra_zone_loaded,
    )

    if not is_intra_zone_loaded():
        return json.dumps(
            {
                "error": (
                    "Intra-zone data not yet loaded. "
                    "Use the web UI first to trigger the initial fetch, "
                    "or call the /intra-zone/matrix endpoint."
                ),
            },
            indent=2,
        )

    if source_zone and target_zone:
        latency_us = get_intra_zone_latency_us(region, source_zone, target_zone)
        return json.dumps(
            {
                "region": region,
                "sourcePhysicalZone": f"{region}-{source_zone}",
                "targetPhysicalZone": f"{region}-{target_zone}",
                "latencyUsP50": latency_us,
                "zoneType": "physical",
                "source": INTRA_ZONE_SOURCE,
                "methodology": INTRA_ZONE_METHODOLOGY,
                "disclaimer": INTRA_ZONE_DISCLAIMER,
            },
            indent=2,
        )

    matrix = get_intra_zone_matrix(region)
    return json.dumps(
        {
            **matrix,
            "source": INTRA_ZONE_SOURCE,
            "methodology": INTRA_ZONE_METHODOLOGY,
            "disclaimer": INTRA_ZONE_DISCLAIMER,
        },
        indent=2,
    )
