"""Inter-region latency dataset based on Microsoft published statistics.

Source: https://learn.microsoft.com/en-us/azure/networking/azure-network-latency

The dataset is loaded from ``data/latency.csv`` — a full pairwise matrix
exported from the Azure Network Latency page.

The dataset is indicative — actual latency depends on network path, time of
day, and workload.  Always validate with in-tenant measurements using tools
like Latte, SockPerf, or Azure Connection Monitor.

Cache TTL: 24 hours (dataset is static, refreshed monthly by Microsoft).
"""

import csv
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Latency pairs loaded from CSV
# Source: Azure Network Latency page, median RTT values (ms).
# The CSV contains a full matrix; A→B and B→A may differ slightly.
# Pairs not present in the CSV return None (unknown).
# ---------------------------------------------------------------------------

_LATENCY_PAIRS: dict[tuple[str, str], int] = {}
_DATA_LOADED = False
_CSV_PATH = Path(__file__).parent / "data" / "latency.csv"


def _display_to_internal(name: str) -> str:
    """Convert a region display name (e.g. 'East US 2') to internal name ('eastus2')."""
    return name.strip().lower().replace(" ", "")


def _load_csv() -> None:
    """Load the latency CSV data into *_LATENCY_PAIRS* (once)."""
    global _DATA_LOADED  # noqa: PLW0603
    if _DATA_LOADED:
        return

    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # First column is "Source", remaining columns are destination regions.
        dest_regions = [_display_to_internal(h) for h in header[1:]]

        for row in reader:
            if not row or not row[0].strip():
                continue
            source = _display_to_internal(row[0])
            for i, cell in enumerate(row[1:]):
                cell = cell.strip()
                if not cell or i >= len(dest_regions):
                    continue
                dest = dest_regions[i]
                if source == dest:
                    continue  # self-latency handled separately
                try:
                    _LATENCY_PAIRS[(source, dest)] = int(cell)
                except ValueError:
                    logger.warning("Invalid latency value %r for %s -> %s", cell, source, dest)

    _DATA_LOADED = True
    logger.info("Loaded %d latency pairs from %s", len(_LATENCY_PAIRS), _CSV_PATH)


# ---------------------------------------------------------------------------
# Cache for runtime-added pairs (e.g. from future API integration)
# ---------------------------------------------------------------------------
_CACHE_TTL = 86400  # 24 hours
_cache: dict[str, tuple[float, int | None]] = {}


def _cache_key(a: str, b: str) -> str:
    parts = sorted([a.lower(), b.lower()])
    return f"{parts[0]}:{parts[1]}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_rtt_ms(region_a: str, region_b: str) -> int | None:
    """Return indicative round-trip time in milliseconds between two Azure regions.

    Returns ``None`` if the pair is not in the dataset.
    Self-latency (same region) returns 0.

    Source: https://learn.microsoft.com/en-us/azure/networking/azure-network-latency
    """
    _load_csv()

    a = region_a.lower().strip()
    b = region_b.lower().strip()

    if a == b:
        return 0

    # Check static dataset
    rtt = _LATENCY_PAIRS.get((a, b))
    if rtt is not None:
        return rtt

    # Check runtime cache
    ck = _cache_key(a, b)
    cached = _cache.get(ck)
    if cached is not None:
        ts, val = cached
        if time.monotonic() - ts < _CACHE_TTL:
            return val

    return None


def list_known_pairs() -> list[dict[str, str | int]]:
    """Return all known latency pairs for inspection."""
    _load_csv()

    seen: set[tuple[str, str]] = set()
    pairs: list[dict[str, str | int]] = []
    for (a, b), rtt in _LATENCY_PAIRS.items():
        key = (min(a, b), max(a, b))
        if key not in seen:
            seen.add(key)
            pairs.append({"regionA": key[0], "regionB": key[1], "rttMs": rtt})
    return sorted(pairs, key=lambda p: (p["regionA"], p["regionB"]))


def get_latency_matrix(
    region_names: list[str],
) -> dict[str, list[str] | list[list[int | None]]]:
    """Return a pairwise latency matrix for the given regions.

    Returns a dict with:
    - ``regions``: list of normalised region names
    - ``matrix``: 2D list where ``matrix[i][j]`` is the RTT in ms
      between ``regions[i]`` and ``regions[j]`` (``None`` if unknown).
    """
    _load_csv()

    normalised = [r.lower().strip() for r in region_names]
    matrix: list[list[int | None]] = []
    for a in normalised:
        row: list[int | None] = []
        for b in normalised:
            row.append(get_rtt_ms(a, b))
        matrix.append(row)
    return {"regions": normalised, "matrix": matrix}
