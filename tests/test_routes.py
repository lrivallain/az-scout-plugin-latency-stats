"""Tests for API routes — mode parameter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from az_scout_latency_stats.routes import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestLatencyMatrixAzuredocsMode:
    """Test /matrix endpoint in azuredocs mode."""

    def test_default_mode_is_azuredocs(self) -> None:
        resp = client.post("/matrix", json={"regions": ["francecentral", "westeurope"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "azuredocs"
        assert "source" in data

    def test_explicit_azuredocs_mode(self) -> None:
        resp = client.post(
            "/matrix",
            json={"regions": ["francecentral", "westeurope"], "mode": "azuredocs"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "azuredocs"


class TestLatencyMatrixCloud63Mode:
    """Test /matrix endpoint in cloud63 mode (with mocked fetch)."""

    def test_cloud63_mode_returns_cloud63(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        fake_records = [
            {
                "source": "francecentral",
                "destination": "westeurope",
                "latency": "12 ms",
                "timestamp": "2025-03-01T00:00:00Z",
            },
            {
                "source": "westeurope",
                "destination": "francecentral",
                "latency": "11 ms",
                "timestamp": "2025-03-01T00:00:00Z",
            },
        ]

        with patch.object(mod, "_fetch_cloud63_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = fake_records
            mod._cloud63_loaded = False
            mod._cloud63_loaded_at = 0.0

            resp = client.post(
                "/matrix",
                json={"regions": ["francecentral", "westeurope"], "mode": "cloud63"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "cloud63"
        assert "disclaimer" in data
        assert data["matrix"][0][1] is not None

        # Tear down
        with mod._cache_lock:
            mod._cloud63_pairs = {}
            mod._cloud63_loaded_at = 0.0
            mod._cloud63_loaded = False

    def test_invalid_mode_rejected(self) -> None:
        resp = client.post(
            "/matrix",
            json={"regions": ["francecentral"], "mode": "invalid"},
        )
        assert resp.status_code == 422


class TestLatencyPairs:
    """Test /pairs endpoint (unchanged, still basic only)."""

    def test_pairs_returns_list(self) -> None:
        resp = client.get("/pairs")
        assert resp.status_code == 200
        data = resp.json()
        assert "pairs" in data
        assert isinstance(data["pairs"], list)


class TestCloud63Regions:
    """Test /cloud63-regions endpoint."""

    def test_returns_region_list(self) -> None:
        import az_scout_latency_stats.cloud63 as mod

        fake_records = [
            {
                "source": "westeurope",
                "destination": "eastus",
                "latency": "75 ms",
                "timestamp": "2025-03-01T00:00:00Z",
            },
            {
                "source": "eastus",
                "destination": "westeurope",
                "latency": "76 ms",
                "timestamp": "2025-03-01T00:00:00Z",
            },
            {
                "source": "francecentral",
                "destination": "westeurope",
                "latency": "12 ms",
                "timestamp": "2025-03-01T00:00:00Z",
            },
        ]

        with patch.object(mod, "_fetch_cloud63_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = fake_records
            mod._cloud63_loaded = False
            mod._cloud63_loaded_at = 0.0

            resp = client.get("/cloud63-regions")

        assert resp.status_code == 200
        data = resp.json()
        assert "regions" in data
        regions = data["regions"]
        assert isinstance(regions, list)
        assert "westeurope" in regions
        assert "eastus" in regions
        assert "francecentral" in regions
        assert regions == sorted(regions)

        # Tear down
        with mod._cache_lock:
            mod._cloud63_pairs = {}
            mod._cloud63_loaded_at = 0.0
            mod._cloud63_loaded = False
