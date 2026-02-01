"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from photosearch import __version__
from photosearch.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestStatusEndpoint:
    """Tests for the /status endpoint."""

    def test_status_returns_ok(self, client):
        """Test that status endpoint returns ok status."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_status_returns_version(self, client):
        """Test that status endpoint returns correct version."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == __version__

    def test_status_returns_indexed_count(self, client):
        """Test that status endpoint returns indexed count."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert "indexed_count" in data
        assert isinstance(data["indexed_count"], int)

    def test_status_returns_index_size(self, client):
        """Test that status endpoint returns index size."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert "index_size_mb" in data
        assert isinstance(data["index_size_mb"], float)


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_healthy(self, client):
        """Test that health endpoint returns healthy status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_api_info(self, client):
        """Test that root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "PhotoSearch API"
        assert data["version"] == __version__
        assert "docs" in data
        assert "status" in data
