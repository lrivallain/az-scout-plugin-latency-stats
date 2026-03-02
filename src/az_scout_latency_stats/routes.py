"""API routes for the latency stats plugin."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_AZUREDOCS_SOURCE = "https://learn.microsoft.com/en-us/azure/networking/azure-network-latency"
_CLOUD63_SOURCE = "https://latency.azure.cloud63.fr/"


class LatencyMatrixRequest(BaseModel):
    """Request body for the latency matrix endpoint."""

    regions: list[str]
    mode: Literal["azuredocs", "cloud63"] = "azuredocs"


@router.post("/matrix")
async def latency_matrix(body: LatencyMatrixRequest) -> dict[str, object]:
    """Return a pairwise RTT latency matrix for the given regions.

    Available at ``/plugins/latency-stats/matrix``.
    Accepts a JSON body with ``{"regions": [...], "mode": "azuredocs"|"cloud63"}``.
    """
    if body.mode == "cloud63":
        from az_scout_latency_stats.cloud63 import (
            get_cloud63_latency_matrix,
            refresh_cloud63_data,
        )

        await refresh_cloud63_data()
        result = get_cloud63_latency_matrix(body.regions)
        return {
            **result,
            "mode": "cloud63",
            "source": _CLOUD63_SOURCE,
            "disclaimer": (
                "Cloud63 latency values are crowd-sourced measurements. "
                "Validate with in-tenant measurements."
            ),
        }

    from az_scout_latency_stats.latency import get_latency_matrix

    result = get_latency_matrix(body.regions)
    return {
        **result,
        "mode": "azuredocs",
        "source": _AZUREDOCS_SOURCE,
        "disclaimer": (
            "Latency values are indicative and must be validated with in-tenant measurements."
        ),
    }


@router.get("/pairs")
async def latency_pairs() -> dict[str, object]:
    """Return all known latency pairs.

    Available at ``/plugins/latency-stats/pairs``.
    """
    from az_scout_latency_stats.latency import list_known_pairs

    return {
        "pairs": list_known_pairs(),
        "source": _AZUREDOCS_SOURCE,
    }


@router.get("/cloud63-regions")
async def cloud63_regions() -> dict[str, object]:
    """Return the list of regions available in the Cloud63 data.

    Available at ``/plugins/latency-stats/cloud63-regions``.
    Triggers a data fetch if the cache is empty or stale.
    """
    from az_scout_latency_stats.cloud63 import (
        get_cloud63_regions,
        refresh_cloud63_data,
    )

    await refresh_cloud63_data()
    return {"regions": get_cloud63_regions()}
