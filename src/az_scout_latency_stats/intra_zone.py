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

import re
import statistics
import threading
import time
from collections import defaultdict
from typing import Any

from az_scout_latency_stats._log import logger

_INTRA_ZONE_API_URL = "https://fa-azure-network-benchmark.azurewebsites.net/api/data"
_CACHE_TTL = 86400  # 24h

_ROWKEY_REGION_MAP: dict[str, str] = {
    "ae": "australiaeast",
    "bec": "belgiumcentral",
    "brs": "brazilsouth",
    "clc": "chilecentral",
    "cnc": "canadacentral",
    "cus": "centralus",
    "ea": "eastasia",
    "eus2": "eastus2",
    "frc": "francecentral",
    "gwc": "germanywestcentral",
    "idc": "indonesiacentral",
    "ilc": "israelcentral",
    "inc": "indiacentral",
    "itn": "italynorth",
    "jpe": "japaneast",
    "jpw": "japanwest",
    "krc": "koreacentral",
    "mxc": "mexicocentral",
    "myw": "malaysiawest",
    "ne": "northeurope",
    "nwe": "norwayeast",
    "nzn": "newzealandnorth",
    "plc": "polandcentral",
    "san": "southafricanorth",
    "scus": "southcentralus",
    "sea": "southeastasia",
    "sdc": "swedencentral",
    "spc": "spaincentral",
    "szn": "switzerlandnorth",
    "uan": "uaenorth",
    "uks": "uksouth",
    "we": "westeurope",
    "wus2": "westus2",
    "wus3": "westus3",
}

_cache_lock = threading.Lock()
_intra_zone_pairs: dict[tuple[str, str, str], float] = {}
_intra_zone_loaded_at: float = 0.0
_intra_zone_loaded = False


def _parse_latency_us(value: Any) -> float | None:
    """Parse a latency value to microseconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        unit_raw = raw.lower().replace("µ", "u")
        m = re.search(r"([\d.]+)", unit_raw)
        if not m:
            return None
        try:
            parsed = float(m.group(1))
        except ValueError:
            return None
        if "us" in unit_raw:
            return parsed
        if "ns" in unit_raw:
            return parsed / 1000.0
        # Default to milliseconds if no explicit micro/nano unit
        return parsed * 1000.0
    return None


def _normalise_region(value: str) -> str:
    """Normalise region names."""
    return value.strip().lower().replace(" ", "")


def _normalise_zone(value: str) -> str:
    """Normalise zone names to stable labels (e.g. az1, az2, az3)."""
    raw = value.strip().lower()
    if not raw:
        return ""

    m = re.search(r"(\d+)$", raw)
    if m:
        return f"az{m.group(1)}"

    m2 = re.search(r"(?:az|zone|availabilityzone)[^\d]*(\d+)", raw)
    if m2:
        return f"az{m2.group(1)}"

    return raw.replace(" ", "")


def _extract_str(record: dict[str, Any], *keys: str) -> str:
    """Extract first non-empty string value from candidate keys."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_region(record: dict[str, Any]) -> str:
    """Extract region from likely field names."""
    direct = _extract_str(
        record,
        "region",
        "Region",
        "regionName",
        "RegionName",
        "azureRegion",
        "AzureRegion",
        "location",
        "Location",
        "sourceRegion",
        "SourceRegion",
        "destinationRegion",
        "DestinationRegion",
        "src_region",
        "dst_region",
        "rowKey",
        "RowKey",
    )
    if direct:
        normalized_direct = _normalise_region(direct)
        return _ROWKEY_REGION_MAP.get(normalized_direct, normalized_direct)

    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        nested = _extract_str(metadata, "region", "regionName", "location")
        if nested:
            return _normalise_region(nested)

    return ""


def _extract_zones(record: dict[str, Any]) -> tuple[str, str] | None:
    """Extract a zone pair from likely field names."""
    candidates = [
        ("sourceZone", "destinationZone"),
        ("SourceZone", "DestinationZone"),
        ("source_zone", "destination_zone"),
        ("sourceAvailabilityZone", "destinationAvailabilityZone"),
        ("SourceAvailabilityZone", "DestinationAvailabilityZone"),
        ("sourceAz", "destinationAz"),
        ("SourceAz", "DestinationAz"),
        ("azFrom", "azTo"),
        ("zoneA", "zoneB"),
        ("ZoneA", "ZoneB"),
        ("fromZone", "toZone"),
        ("Source", "Destination"),
    ]

    for key_a, key_b in candidates:
        a = _extract_str(record, key_a)
        b = _extract_str(record, key_b)
        if a and b:
            na = _normalise_zone(a)
            nb = _normalise_zone(b)
            if na and nb and na != nb:
                return (na, nb)

    zones = record.get("zones")
    if isinstance(zones, list) and len(zones) >= 2:
        a_raw = str(zones[0])
        b_raw = str(zones[1])
        na = _normalise_zone(a_raw)
        nb = _normalise_zone(b_raw)
        if na and nb and na != nb:
            return (na, nb)

    return None


def _extract_latency_sample(record: dict[str, Any]) -> float | None:
    """Extract a latency sample from likely field names."""
    for key in (
        "p50",
        "P50",
        "p50Ms",
        "P50Ms",
        "p50_ms",
        "latencyP50",
        "LatencyP50",
        "latency_p50",
        "median",
        "Median",
        "latency",
        "Latency",
        "latencyMs",
        "LatencyMs",
        "latency_ms",
        "value",
        "Value",
    ):
        parsed = _parse_latency_us(record.get(key))
        if parsed is not None:
            return parsed

    stats = record.get("stats")
    if isinstance(stats, dict):
        for key in ("p50", "median", "latencyMs"):
            parsed = _parse_latency_us(stats.get(key))
            if parsed is not None:
                return parsed

    return None


def _parse_endpoint_region_zone(value: str) -> tuple[str, str] | None:
    """Parse endpoint strings that may embed both region and AZ.

    Supported examples:
    - ``westeurope-1``
    - ``westeurope-az2``
    - ``westeurope-zone3``
    - ``westeurope az1``
    """
    raw = value.strip().lower()
    if not raw:
        return None

    compact = re.sub(r"\s+", "", raw)
    match = re.match(r"^([a-z0-9-]+?)[-_]?(?:az|zone)?(\d+)$", compact)
    if not match:
        return None

    region = _normalise_region(match.group(1).replace("-", ""))
    zone = f"az{match.group(2)}"
    if not region or not zone:
        return None
    return (region, zone)


def _extract_region_and_zones_from_endpoints(
    record: dict[str, Any],
) -> tuple[str, tuple[str, str]] | None:
    """Extract region and zone-pair from endpoint-style fields.

    This handles payloads where only ``source``/``destination`` strings exist
    and each string contains both region and zone.
    """
    endpoint_candidates = [
        ("source", "destination"),
        ("src", "dst"),
        ("from", "to"),
        ("fromEndpoint", "toEndpoint"),
        ("sourceEndpoint", "destinationEndpoint"),
    ]

    for source_key, destination_key in endpoint_candidates:
        source_raw = _extract_str(record, source_key)
        destination_raw = _extract_str(record, destination_key)
        if not source_raw or not destination_raw:
            continue

        source_parsed = _parse_endpoint_region_zone(source_raw)
        destination_parsed = _parse_endpoint_region_zone(destination_raw)
        if source_parsed is None or destination_parsed is None:
            continue

        source_region, source_zone = source_parsed
        destination_region, destination_zone = destination_parsed
        if source_region != destination_region:
            continue
        if source_zone == destination_zone:
            continue

        return (source_region, (source_zone, destination_zone))

    return None


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
    """Aggregate records and keep P50 RTT for each region/zone-pair.

    RTT is computed as:
    - P50(one-way zoneA→zoneB) + P50(one-way zoneB→zoneA)

    Pairs missing one direction are excluded.
    """
    grouped_directional: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    for rec in records:
        region = _extract_region(rec)
        zones = _extract_zones(rec)

        if not region or zones is None:
            endpoint_result = _extract_region_and_zones_from_endpoints(rec)
            if endpoint_result is not None:
                region, zones = endpoint_result

        if not region or zones is None:
            continue

        latency_sample = _extract_latency_sample(rec)
        if latency_sample is None:
            continue

        source_zone, target_zone = zones
        grouped_directional[(region, source_zone, target_zone)].append(latency_sample)

    directional_p50: dict[tuple[str, str, str], float] = {}
    for key, values in grouped_directional.items():
        directional_p50[key] = float(statistics.median(values))

    p50_pairs: dict[tuple[str, str, str], float] = {}
    for region, zone_a, zone_b in directional_p50:
        if zone_a >= zone_b:
            continue
        forward = directional_p50.get((region, zone_a, zone_b))
        reverse = directional_p50.get((region, zone_b, zone_a))
        if forward is None or reverse is None:
            continue
        p50_pairs[(region, zone_a, zone_b)] = forward + reverse

    return p50_pairs


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
