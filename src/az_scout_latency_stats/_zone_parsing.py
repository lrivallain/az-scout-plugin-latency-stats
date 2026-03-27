"""Shared zone-parsing helpers for inter-zone and intra-zone modules.

Both modules hit the same upstream API and process the same record format.
This module centralises all field-extraction and normalisation logic so that
bug fixes and schema adaptations only need to be made in one place.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Any

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


def process_zone_records(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    """Aggregate records and return P50 RTT for each (region, zone_a, zone_b) key.

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
