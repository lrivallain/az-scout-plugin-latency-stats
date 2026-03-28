"""Intra-region (Availability Zone) latency data.

Source: https://fa-azure-network-benchmark.azurewebsites.net/api/data

The upstream format can evolve. This module therefore uses tolerant field
extraction and keeps only records that clearly describe:
- a region,
- two distinct zones within that region,
- a latency sample in microseconds.

When multiple samples exist for a zone pair, the module returns P50 (median).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from az_scout_latency_stats._log import logger
from az_scout_latency_stats._zone_parsing import (
    _normalise_region,
    _normalise_zone,
    _parse_latency_us,  # noqa: F401  # re-exported for test compatibility
    process_zone_records,
)

_INTRA_ZONE_API_URL = "https://fa-azure-network-benchmark.azurewebsites.net/api/data"
_CACHE_TTL = 86400  # 24h

_cache_lock = threading.Lock()
_intra_zone_pairs: dict[tuple[str, str, str], float] = {}
_intra_zone_loaded_at: float = 0.0
_intra_zone_loaded = False


async def _fetch_intra_zone_data() -> list[dict[str, Any]]:
    """Fetch the intra-zone latency dataset from the remote API."""
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(_INTRA_ZONE_API_URL)
        resp.raise_for_status()
        payload = resp.json()

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def _process_intra_zone_records(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    """Aggregate records and keep P50 RTT for each region/zone-pair."""
    return process_zone_records(records)


async def refresh_intra_zone_data() -> None:
    """Fetch and cache intra-zone data (if stale or not loaded)."""
    global _intra_zone_pairs, _intra_zone_loaded_at, _intra_zone_loaded  # noqa: PLW0603

    now = time.monotonic()
    if _intra_zone_loaded and (now - _intra_zone_loaded_at) < _CACHE_TTL:
        return

    logger.info("Fetching intra-zone latency data from %s", _INTRA_ZONE_API_URL)
    records = await _fetch_intra_zone_data()
    pairs = _process_intra_zone_records(records)

    with _cache_lock:
        _intra_zone_pairs = pairs
        _intra_zone_loaded_at = time.monotonic()
        _intra_zone_loaded = True

    logger.info(
        "Cached %d intra-zone pairs (%d raw records)",
        len(pairs),
        len(records),
    )


def is_intra_zone_loaded() -> bool:
    """Return True when intra-zone cache is loaded and fresh."""
    return _intra_zone_loaded and (time.monotonic() - _intra_zone_loaded_at) < _CACHE_TTL


def get_intra_zone_regions() -> list[str]:
    """Return sorted list of regions available in intra-zone cache."""
    with _cache_lock:
        return sorted({region for region, _, _ in _intra_zone_pairs})


def get_intra_zone_latency_us(region: str, zone_a: str, zone_b: str) -> float | None:
    """Return P50 RTT for a zone pair within a region (in microseconds)."""
    normalized_region = _normalise_region(region)
    normalized_a = _normalise_zone(zone_a)
    normalized_b = _normalise_zone(zone_b)

    if not normalized_region or not normalized_a or not normalized_b:
        return None
    if normalized_a == normalized_b:
        return 0.0

    zone_1, zone_2 = sorted((normalized_a, normalized_b))
    key = (normalized_region, zone_1, zone_2)
    with _cache_lock:
        return _intra_zone_pairs.get(key)


def get_intra_zone_matrix(region: str) -> dict[str, Any]:
    """Return full intra-zone matrix for a region in microseconds."""
    normalized_region = _normalise_region(region)
    with _cache_lock:
        region_pairs = {
            (zone_a, zone_b): latency
            for (r, zone_a, zone_b), latency in _intra_zone_pairs.items()
            if r == normalized_region
        }

    zones_set: set[str] = set()
    for zone_a, zone_b in region_pairs:
        zones_set.add(zone_a)
        zones_set.add(zone_b)
    zones = sorted(zones_set)
    full_zones = [f"{normalized_region}-{z}" for z in zones]

    matrix: list[list[float | None]] = []
    for zone_row in zones:
        row: list[float | None] = []
        for zone_col in zones:
            if zone_row == zone_col:
                row.append(0.0)
            else:
                zone_1, zone_2 = sorted((zone_row, zone_col))
                row.append(region_pairs.get((zone_1, zone_2)))
        matrix.append(row)

    pairs = [
        {
            "zoneA": f"{normalized_region}-{zone_a}",
            "zoneB": f"{normalized_region}-{zone_b}",
            "latencyUsP50": latency,
        }
        for (zone_a, zone_b), latency in sorted(region_pairs.items())
    ]

    return {
        "region": normalized_region,
        "zones": full_zones,
        "matrix": matrix,
        "pairs": pairs,
    }


def prewarm_intra_zone() -> None:
    """Trigger background intra-zone fetch without blocking startup."""
    import asyncio
    import threading

    def _run() -> None:
        try:
            asyncio.run(refresh_intra_zone_data())
        except Exception:
            logger.warning("Intra-zone prewarm failed — data will be fetched on first request")

    thread = threading.Thread(target=_run, daemon=True, name="intra-zone-prewarm")
    thread.start()
