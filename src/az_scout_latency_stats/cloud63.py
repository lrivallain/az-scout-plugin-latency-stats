"""Cloud63 latency data from the Azure Latency Test project.

Source: https://latency.azure.cloud63.fr/
API:    https://func-latency-api-001.azurewebsites.net/api/latency

The API returns a large JSON array of individual latency measurements.
Each record has ``source``, ``destination``, ``latency`` (string like
``"69.4 ms"``), and ``timestamp`` (ISO 8601).

Multiple measurements exist per pair — we keep only the **latest** one
for each (source, destination) pair.  Data is cached for 24 hours.
"""

import re
import threading
import time
from datetime import datetime

from az_scout_latency_stats._log import logger

_CLOUD63_API_URL = "https://func-latency-api-001.azurewebsites.net/api/latency"
_CLOUD63_PROJECT_URL = "https://latency.azure.cloud63.fr/"

# ---------------------------------------------------------------------------
# Cached Cloud63 data
# ---------------------------------------------------------------------------
_CACHE_TTL = 86400  # 24 hours
_cache_lock = threading.Lock()
_cloud63_pairs: dict[tuple[str, str], float] = {}
_cloud63_loaded_at: float = 0.0
_cloud63_loaded = False


def _parse_latency(val: str) -> float | None:
    """Parse a latency string like ``'69.4 ms'`` into a float."""
    m = re.match(r"([\d.]+)\s*ms", val.strip(), re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


async def _fetch_cloud63_data() -> list[dict[str, str]]:
    """Fetch the Cloud63 latency data from the remote API."""
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(_CLOUD63_API_URL)
        resp.raise_for_status()
        data: list[dict[str, str]] = resp.json()
        return data


def _process_records(records: list[dict[str, str]]) -> dict[tuple[str, str], float]:
    """Extract latest RTT per (source, destination) pair from raw records."""
    latest: dict[tuple[str, str], tuple[datetime, float]] = {}

    for rec in records:
        src = rec.get("source", "").strip().lower()
        dst = rec.get("destination", "").strip().lower()
        if not src or not dst or src == dst:
            continue

        rtt = _parse_latency(rec.get("latency", ""))
        if rtt is None:
            continue

        ts_str = rec.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.min

        key = (src, dst)
        existing = latest.get(key)
        if existing is None or ts > existing[0]:
            latest[key] = (ts, rtt)

    return {k: v[1] for k, v in latest.items()}


async def refresh_cloud63_data() -> None:
    """Fetch and cache Cloud63 latency data (if stale or not loaded)."""
    global _cloud63_pairs, _cloud63_loaded_at, _cloud63_loaded  # noqa: PLW0603

    now = time.monotonic()
    if _cloud63_loaded and (now - _cloud63_loaded_at) < _CACHE_TTL:
        return

    logger.info("Fetching Cloud63 latency data from %s", _CLOUD63_API_URL)
    records = await _fetch_cloud63_data()
    pairs = _process_records(records)

    with _cache_lock:
        _cloud63_pairs = pairs
        _cloud63_loaded_at = time.monotonic()
        _cloud63_loaded = True

    logger.info(
        "Cached %d Cloud63 latency pairs (%d raw records)",
        len(pairs),
        len(records),
    )


def get_cloud63_rtt_ms(region_a: str, region_b: str) -> int | None:
    """Return RTT (ms) between two regions from Cloud63 data, or None.

    Cloud63 measurements are **one-way** latencies.  A proper round-trip
    requires data in *both* directions (A→B **and** B→A).  The returned
    value is the sum of the two one-way latencies.  If either direction
    is missing, ``None`` is returned.
    """
    a = region_a.lower().strip()
    b = region_b.lower().strip()

    if a == b:
        return 0

    with _cache_lock:
        fwd = _cloud63_pairs.get((a, b))
        rev = _cloud63_pairs.get((b, a))

    if fwd is not None and rev is not None:
        return round(fwd + rev)

    return None


def get_cloud63_latency_matrix(
    region_names: list[str],
) -> dict[str, list[str] | list[list[int | None]]]:
    """Return a pairwise latency matrix from Cloud63 data."""
    normalised = [r.lower().strip() for r in region_names]
    matrix: list[list[int | None]] = []
    for a in normalised:
        row: list[int | None] = []
        for b in normalised:
            row.append(get_cloud63_rtt_ms(a, b))
        matrix.append(row)
    return {"regions": normalised, "matrix": matrix}


def is_cloud63_loaded() -> bool:
    """Return True if Cloud63 data has been loaded and is not stale."""
    return _cloud63_loaded and (time.monotonic() - _cloud63_loaded_at) < _CACHE_TTL


def get_cloud63_regions() -> list[str]:
    """Return sorted list of unique region names present in the Cloud63 data."""
    with _cache_lock:
        regions: set[str] = set()
        for src, dst in _cloud63_pairs:
            regions.add(src)
            regions.add(dst)
    return sorted(regions)


def prewarm_cloud63() -> None:
    """Trigger a background fetch of Cloud63 data without blocking the caller.

    Safe to call at import / plugin-instantiation time — the actual HTTP
    request runs in a daemon thread so it never delays application startup.
    """
    import asyncio
    import threading

    def _run() -> None:
        try:
            asyncio.run(refresh_cloud63_data())
        except Exception:
            logger.warning("Cloud63 prewarm failed — data will be fetched on first request")

    t = threading.Thread(target=_run, daemon=True, name="cloud63-prewarm")
    t.start()
