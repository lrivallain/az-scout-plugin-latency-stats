"""Tests for intra-zone latency data module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from az_scout_latency_stats.intra_zone import (
    _parse_latency_us,
    _process_intra_zone_records,
    get_intra_zone_latency_us,
    get_intra_zone_matrix,
    get_intra_zone_regions,
    is_intra_zone_loaded,
)


class TestParseMs:
    """Unit tests for latency parser."""

    def test_parse_numeric_string(self) -> None:
        assert _parse_latency_us("12.5 ms") == 12500.0

    def test_parse_int(self) -> None:
        assert _parse_latency_us(9) == 9.0

    def test_parse_invalid(self) -> None:
        assert _parse_latency_us("n/a") is None

    def test_parse_microseconds_to_ms(self) -> None:
        assert _parse_latency_us("186 us") == 186.0


class TestProcessIntraZoneRecords:
    """Unit tests for record processing and P50 RTT aggregation."""

    def test_aggregates_p50_for_pair(self) -> None:
        records = [
            {
                "region": "westeurope",
                "sourceZone": "1",
                "destinationZone": "2",
                "latency": "1.2 ms",
            },
            {
                "region": "westeurope",
                "sourceZone": "2",
                "destinationZone": "1",
                "latency": "1.8 ms",
            },
            {
                "region": "westeurope",
                "sourceZone": "az1",
                "destinationZone": "az2",
                "latency": "2.4 ms",
            },
        ]

        pairs = _process_intra_zone_records(records)

        # RTT = P50(az1→az2=[1200,2400]) + P50(az2→az1=[1800]) = 1800 + 1800
        assert pairs[("westeurope", "az1", "az2")] == 3600.0

    def test_skips_missing_fields(self) -> None:
        records = [
            {"region": "westeurope", "sourceZone": "1", "destinationZone": "2"},
            {"sourceZone": "1", "destinationZone": "2", "latency": "1.0 ms"},
        ]

        assert _process_intra_zone_records(records) == {}

    def test_extracts_from_endpoint_style_records(self) -> None:
        records = [
            {
                "source": "westeurope-az1",
                "destination": "westeurope-az2",
                "latencyP50": 1.1,
            },
            {
                "source": "westeurope-az2",
                "destination": "westeurope-az1",
                "latencyP50": 1.2,
            },
            {
                "source": "westeurope-zone2",
                "destination": "westeurope-zone3",
                "latencyP50": "1.3 ms",
            },
            {
                "source": "westeurope-zone3",
                "destination": "westeurope-zone2",
                "latencyP50": "1.5 ms",
            },
        ]

        pairs = _process_intra_zone_records(records)

        assert pairs[("westeurope", "az1", "az2")] == 1.1 + 1.2
        assert pairs[("westeurope", "az2", "az3")] == 1300.0 + 1500.0

    def test_extracts_from_rowkey_source_destination_shape(self) -> None:
        records = [
            {
                "RowKey": "frc",
                "Source": "az1",
                "Destination": "az3",
                "Latency": "186 us",
            },
            {
                "RowKey": "frc",
                "Source": "az1",
                "Destination": "az3",
                "Latency": "214 us",
            },
            {
                "RowKey": "frc",
                "Source": "az3",
                "Destination": "az1",
                "Latency": "220 us",
            },
            {
                "RowKey": "frc",
                "Source": "az3",
                "Destination": "az1",
                "Latency": "228 us",
            },
        ]

        pairs = _process_intra_zone_records(records)

        # RTT = P50(az1→az3=[186,214]) + P50(az3→az1=[220,228]) = 200 + 224
        assert pairs[("francecentral", "az1", "az3")] == 424.0

    def test_preserves_microsecond_precision_without_rounding(self) -> None:
        records = [
            {
                "RowKey": "sdc",
                "Source": "az1",
                "Destination": "az2",
                "Latency": "216.12 us",
            },
            {
                "RowKey": "sdc",
                "Source": "az1",
                "Destination": "az2",
                "Latency": "216.18 us",
            },
            {
                "RowKey": "sdc",
                "Source": "az2",
                "Destination": "az1",
                "Latency": "113.03 us",
            },
            {
                "RowKey": "sdc",
                "Source": "az2",
                "Destination": "az1",
                "Latency": "113.07 us",
            },
        ]

        pairs = _process_intra_zone_records(records)

        # RTT = P50(216.12,216.18) + P50(113.03,113.07) = 216.15 + 113.05
        assert pairs[("swedencentral", "az1", "az2")] == pytest.approx(329.2)


@pytest.fixture()
def _populated_intra_cache() -> None:  # type: ignore[misc]
    """Populate intra-zone module cache for tests."""
    import time

    import az_scout_latency_stats.intra_zone as mod

    with mod._cache_lock:
        mod._intra_zone_pairs = {
            ("westeurope", "az1", "az2"): 1200.0,
            ("westeurope", "az1", "az3"): 1500.0,
            ("westeurope", "az2", "az3"): 1300.0,
        }
        mod._intra_zone_loaded_at = time.monotonic()
        mod._intra_zone_loaded = True

    yield

    with mod._cache_lock:
        mod._intra_zone_pairs = {}
        mod._intra_zone_loaded_at = 0.0
        mod._intra_zone_loaded = False


@pytest.mark.usefixtures("_populated_intra_cache")
class TestIntraZoneQueries:
    """Unit tests for intra-zone query functions."""

    def test_get_intra_zone_latency(self) -> None:
        assert get_intra_zone_latency_us("westeurope", "az1", "az2") == 1200.0
        assert get_intra_zone_latency_us("westeurope", "zone1", "zone2") == 1200.0

    def test_get_intra_zone_matrix(self) -> None:
        result = get_intra_zone_matrix("westeurope")

        assert result["region"] == "westeurope"
        assert result["zones"] == ["westeurope-az1", "westeurope-az2", "westeurope-az3"]
        matrix = result["matrix"]
        assert matrix[0][0] == 0.0
        assert matrix[0][1] == 1200.0
        assert matrix[1][2] == 1300.0
        assert result["pairs"][0]["latencyUsP50"] > 0

    def test_get_regions(self) -> None:
        assert get_intra_zone_regions() == ["westeurope"]

    def test_loaded_state(self) -> None:
        assert is_intra_zone_loaded() is True


class TestRefreshIntraZone:
    """Unit tests for intra-zone refresh with mocked HTTP."""

    @pytest.mark.asyncio()
    async def test_fetches_and_caches(self) -> None:
        import az_scout_latency_stats.intra_zone as mod

        fake_records = [
            {
                "region": "westeurope",
                "sourceZone": "1",
                "destinationZone": "2",
                "latency": "1.1 ms",
            },
            {
                "region": "westeurope",
                "sourceZone": "2",
                "destinationZone": "1",
                "latency": "1.4 ms",
            },
        ]

        with patch.object(mod, "_fetch_intra_zone_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = fake_records
            mod._intra_zone_loaded = False
            mod._intra_zone_loaded_at = 0.0

            await mod.refresh_intra_zone_data()

            mock_fetch.assert_awaited_once()
            assert mod._intra_zone_loaded is True
            assert mod._intra_zone_pairs[("westeurope", "az1", "az2")] == 2500.0

        with mod._cache_lock:
            mod._intra_zone_pairs = {}
            mod._intra_zone_loaded_at = 0.0
            mod._intra_zone_loaded = False
