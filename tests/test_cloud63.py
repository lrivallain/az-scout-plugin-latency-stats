"""Tests for the Cloud63 latency data module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from az_scout_latency_stats.cloud63 import (
    _parse_latency,
    _process_records,
    get_cloud63_latency_matrix,
    get_cloud63_regions,
    get_cloud63_rtt_ms,
    is_cloud63_loaded,
)

# ---------------------------------------------------------------------------
# _parse_latency
# ---------------------------------------------------------------------------


class TestParseLatency:
    """Unit tests for _parse_latency."""

    def test_integer_ms(self) -> None:
        assert _parse_latency("69 ms") == 69.0

    def test_float_ms(self) -> None:
        assert _parse_latency("69.4 ms") == 69.4

    def test_case_insensitive(self) -> None:
        assert _parse_latency("42.0 MS") == 42.0

    def test_extra_whitespace(self) -> None:
        assert _parse_latency("  12.5 ms  ") == 12.5

    def test_no_space(self) -> None:
        assert _parse_latency("10ms") == 10.0

    def test_invalid_string(self) -> None:
        assert _parse_latency("not a number") is None

    def test_empty_string(self) -> None:
        assert _parse_latency("") is None


# ---------------------------------------------------------------------------
# _process_records
# ---------------------------------------------------------------------------

_SAMPLE_RECORDS: list[dict[str, str]] = [
    {
        "source": "westeurope",
        "destination": "eastus",
        "latency": "80.0 ms",
        "timestamp": "2025-01-01T10:00:00Z",
    },
    {
        "source": "westeurope",
        "destination": "eastus",
        "latency": "75.5 ms",
        "timestamp": "2025-01-02T10:00:00Z",
    },
    {
        "source": "eastus",
        "destination": "westeurope",
        "latency": "76.0 ms",
        "timestamp": "2025-01-02T12:00:00Z",
    },
]


class TestProcessRecords:
    """Unit tests for _process_records."""

    def test_keeps_latest_per_pair(self) -> None:
        pairs = _process_records(_SAMPLE_RECORDS)
        # The second record (75.5 ms, Jan 2) should win over the first (80.0 ms, Jan 1)
        assert pairs[("westeurope", "eastus")] == 75.5

    def test_both_directions_stored(self) -> None:
        pairs = _process_records(_SAMPLE_RECORDS)
        assert ("westeurope", "eastus") in pairs
        assert ("eastus", "westeurope") in pairs

    def test_skips_self_pairs(self) -> None:
        records = [
            {
                "source": "eastus",
                "destination": "eastus",
                "latency": "0 ms",
                "timestamp": "2025-01-01T00:00:00Z",
            },
        ]
        pairs = _process_records(records)
        assert len(pairs) == 0

    def test_skips_invalid_latency(self) -> None:
        records = [
            {
                "source": "eastus",
                "destination": "westeurope",
                "latency": "N/A",
                "timestamp": "2025-01-01T00:00:00Z",
            },
        ]
        pairs = _process_records(records)
        assert len(pairs) == 0

    def test_empty_records(self) -> None:
        assert _process_records([]) == {}

    def test_normalises_case(self) -> None:
        records = [
            {
                "source": "WestEurope",
                "destination": "EastUS",
                "latency": "50 ms",
                "timestamp": "2025-01-01T00:00:00Z",
            },
        ]
        pairs = _process_records(records)
        assert ("westeurope", "eastus") in pairs

    def test_handles_missing_timestamp(self) -> None:
        records = [
            {
                "source": "eastus",
                "destination": "westeurope",
                "latency": "50 ms",
            },
        ]
        pairs = _process_records(records)
        assert pairs[("eastus", "westeurope")] == 50.0


# ---------------------------------------------------------------------------
# get_cloud63_rtt_ms / get_cloud63_latency_matrix (with pre-populated cache)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _populated_cache() -> None:  # type: ignore[misc]
    """Populate the module-level cache for testing."""
    import time

    import az_scout_latency_stats.cloud63 as mod

    with mod._cache_lock:
        mod._cloud63_pairs = {
            ("westeurope", "eastus"): 75.5,
            ("eastus", "westeurope"): 76.0,
            ("francecentral", "westeurope"): 12.0,
            ("westeurope", "francecentral"): 11.5,
            # northeurope→westeurope exists, but NOT the reverse → one-way only
            ("northeurope", "westeurope"): 8.0,
        }
        mod._cloud63_loaded_at = time.monotonic()
        mod._cloud63_loaded = True

    yield

    # Tear down — reset cache
    with mod._cache_lock:
        mod._cloud63_pairs = {}
        mod._cloud63_loaded_at = 0.0
        mod._cloud63_loaded = False


@pytest.mark.usefixtures("_populated_cache")
class TestGetCloud63RttMs:
    """Unit tests for get_cloud63_rtt_ms with pre-populated cache."""

    def test_known_pair_sums_both_directions(self) -> None:
        # westeurope→eastus = 75.5, eastus→westeurope = 76.0 → RTT = 152
        assert get_cloud63_rtt_ms("westeurope", "eastus") == 152

    def test_symmetric(self) -> None:
        # Order should not matter — same sum either way
        assert get_cloud63_rtt_ms("eastus", "westeurope") == 152

    def test_self_latency_is_zero(self) -> None:
        assert get_cloud63_rtt_ms("westeurope", "westeurope") == 0

    def test_one_way_only_returns_none(self) -> None:
        # northeurope→westeurope exists but westeurope→northeurope does not
        assert get_cloud63_rtt_ms("northeurope", "westeurope") is None

    def test_unknown_pair(self) -> None:
        assert get_cloud63_rtt_ms("eastus", "japaneast") is None

    def test_case_insensitive(self) -> None:
        assert get_cloud63_rtt_ms("WestEurope", "EastUS") == get_cloud63_rtt_ms(
            "westeurope", "eastus"
        )


@pytest.mark.usefixtures("_populated_cache")
class TestGetCloud63LatencyMatrix:
    """Unit tests for get_cloud63_latency_matrix."""

    def test_two_regions(self) -> None:
        result = get_cloud63_latency_matrix(["westeurope", "eastus"])
        assert result["regions"] == ["westeurope", "eastus"]
        matrix = result["matrix"]
        assert matrix[0][0] == 0  # self
        assert matrix[1][1] == 0  # self
        assert matrix[0][1] is not None
        assert matrix[1][0] is not None

    def test_unknown_pair_in_matrix(self) -> None:
        result = get_cloud63_latency_matrix(["westeurope", "japaneast"])
        matrix = result["matrix"]
        assert matrix[0][1] is None
        assert matrix[1][0] is None

    def test_empty_regions(self) -> None:
        result = get_cloud63_latency_matrix([])
        assert result["regions"] == []
        assert result["matrix"] == []


@pytest.mark.usefixtures("_populated_cache")
class TestIsCloud63Loaded:
    """Unit tests for is_cloud63_loaded."""

    def test_loaded(self) -> None:
        assert is_cloud63_loaded() is True

    def test_not_loaded(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        with mod._cache_lock:
            mod._cloud63_loaded = False
        assert is_cloud63_loaded() is False


# ---------------------------------------------------------------------------
# refresh_cloud63_data
# ---------------------------------------------------------------------------


class TestRefreshCloud63Data:
    """Tests for refresh_cloud63_data with mocked HTTP."""

    @pytest.mark.asyncio()
    async def test_fetches_and_caches(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        fake_records = [
            {
                "source": "westeurope",
                "destination": "eastus",
                "latency": "80 ms",
                "timestamp": "2025-03-01T00:00:00Z",
            },
        ]

        with patch.object(mod, "_fetch_cloud63_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = fake_records

            # Force stale cache
            mod._cloud63_loaded = False
            mod._cloud63_loaded_at = 0.0

            await mod.refresh_cloud63_data()

            mock_fetch.assert_awaited_once()
            assert mod._cloud63_loaded is True
            assert mod._cloud63_pairs[("westeurope", "eastus")] == 80.0

        # Tear down
        with mod._cache_lock:
            mod._cloud63_pairs = {}
            mod._cloud63_loaded_at = 0.0
            mod._cloud63_loaded = False

    @pytest.mark.asyncio()
    async def test_skips_when_cache_fresh(self) -> None:
        import time

        import az_scout_latency_stats.cloud63 as mod

        with mod._cache_lock:
            mod._cloud63_loaded = True
            mod._cloud63_loaded_at = time.monotonic()

        with patch.object(mod, "_fetch_cloud63_data", new_callable=AsyncMock) as mock_fetch:
            await mod.refresh_cloud63_data()
            mock_fetch.assert_not_awaited()

        # Tear down
        with mod._cache_lock:
            mod._cloud63_pairs = {}
            mod._cloud63_loaded_at = 0.0
            mod._cloud63_loaded = False


# ---------------------------------------------------------------------------
# get_cloud63_regions
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_populated_cache")
class TestGetCloud63Regions:
    """Tests for get_cloud63_regions()."""

    def test_returns_sorted_unique_regions(self) -> None:
        regions = get_cloud63_regions()
        assert regions == ["eastus", "francecentral", "northeurope", "westeurope"]

    def test_returns_empty_list_when_cache_empty(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        with mod._cache_lock:
            original_pairs = mod._cloud63_pairs.copy()
            mod._cloud63_pairs = {}

        try:
            assert get_cloud63_regions() == []
        finally:
            with mod._cache_lock:
                mod._cloud63_pairs = original_pairs
