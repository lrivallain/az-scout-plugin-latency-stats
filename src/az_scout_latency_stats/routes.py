"""API routes for the latency stats plugin."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class LatencyMatrixRequest(BaseModel):
    """Request body for the latency matrix endpoint."""

    regions: list[str]


@router.post("/matrix")
async def latency_matrix(body: LatencyMatrixRequest) -> dict[str, object]:
    """Return a pairwise RTT latency matrix for the given regions.

    Available at ``/plugins/latency-stats/matrix``.
    Accepts a JSON body with ``{"regions": ["francecentral", "westeurope", ...]}``.
    """
    from az_scout_latency_stats.latency import get_latency_matrix

    result = get_latency_matrix(body.regions)
    return {
        **result,
        "source": "https://learn.microsoft.com/en-us/azure/networking/azure-network-latency",
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
        "source": "https://learn.microsoft.com/en-us/azure/networking/azure-network-latency",
    }
