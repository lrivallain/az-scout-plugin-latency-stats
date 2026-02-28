"""Tests for the latency stats plugin."""

from az_scout_latency_stats.latency import (
    get_latency_matrix,
    get_rtt_ms,
    list_known_pairs,
)


class TestGetRttMs:
    """Unit tests for get_rtt_ms."""

    def test_self_latency_is_zero(self) -> None:
        assert get_rtt_ms("francecentral", "francecentral") == 0

    def test_known_pair(self) -> None:
        rtt = get_rtt_ms("francecentral", "westeurope")
        assert rtt is not None
        assert isinstance(rtt, int)
        assert rtt > 0

    def test_symmetric(self) -> None:
        assert get_rtt_ms("eastus", "westeurope") == get_rtt_ms("westeurope", "eastus")

    def test_unknown_pair_returns_none(self) -> None:
        assert get_rtt_ms("francecentral", "nonexistentregion") is None

    def test_case_insensitive(self) -> None:
        assert get_rtt_ms("FranceCentral", "WestEurope") == get_rtt_ms(
            "francecentral", "westeurope"
        )


class TestListKnownPairs:
    """Unit tests for list_known_pairs."""

    def test_non_empty(self) -> None:
        pairs = list_known_pairs()
        assert len(pairs) > 10
        for p in pairs:
            assert "regionA" in p
            assert "regionB" in p
            assert "rttMs" in p

    def test_no_duplicates(self) -> None:
        pairs = list_known_pairs()
        keys = {(p["regionA"], p["regionB"]) for p in pairs}
        assert len(keys) == len(pairs)


class TestGetLatencyMatrix:
    """Unit tests for get_latency_matrix."""

    def test_two_regions(self) -> None:
        result = get_latency_matrix(["francecentral", "westeurope"])
        assert result["regions"] == ["francecentral", "westeurope"]
        matrix = result["matrix"]
        assert len(matrix) == 2
        assert len(matrix[0]) == 2
        # Diagonal = 0
        assert matrix[0][0] == 0
        assert matrix[1][1] == 0
        # Off-diagonal = known RTT
        assert matrix[0][1] is not None
        assert matrix[0][1] == matrix[1][0]

    def test_unknown_pair_in_matrix(self) -> None:
        result = get_latency_matrix(["francecentral", "nonexistentregion"])
        matrix = result["matrix"]
        assert matrix[0][1] is None
        assert matrix[1][0] is None

    def test_normalises_case(self) -> None:
        result = get_latency_matrix(["FranceCentral", "WestEurope"])
        assert result["regions"] == ["francecentral", "westeurope"]

    def test_single_region(self) -> None:
        result = get_latency_matrix(["eastus"])
        assert len(result["matrix"]) == 1
        assert result["matrix"][0][0] == 0

    def test_empty_regions(self) -> None:
        result = get_latency_matrix([])
        assert result["regions"] == []
        assert result["matrix"] == []
