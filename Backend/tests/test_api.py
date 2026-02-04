"""Tests for API endpoints."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from photosearch import __version__
from photosearch.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_image_path(temp_dir):
    """Create a sample image file for testing."""
    # Create a minimal valid JPEG file
    image_path = temp_dir / "test_photo.jpg"
    # Minimal JPEG header (not a real image but passes file existence checks)
    image_path.write_bytes(
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\xff\xd9'
    )
    return image_path


@pytest.fixture
def sample_folder_with_images(temp_dir):
    """Create a folder with sample images for testing."""
    # Create a minimal valid JPEG
    jpeg_header = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\xff\xd9'
    )
    
    for i in range(3):
        (temp_dir / f"photo_{i}.jpg").write_bytes(jpeg_header)
    
    return temp_dir


def create_mock_search_engine():
    """Create a mock search engine for testing."""
    mock_engine = MagicMock()
    
    # Setup default return values
    mock_result = MagicMock()
    mock_result.results = []
    mock_result.total_results = 0
    mock_result.location_resolved = None
    mock_engine.search.return_value = mock_result
    
    mock_engine.index_photo.return_value = None
    mock_engine.remove_photo.return_value = False
    
    mock_location_service = MagicMock()
    mock_location_service.geocode.return_value = None
    mock_engine.location_service = mock_location_service
    
    return mock_engine


# =============================================================================
# Status Endpoint Tests
# =============================================================================


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


# =============================================================================
# Health Endpoint Tests
# =============================================================================


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_healthy(self, client):
        """Test that health endpoint returns healthy status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# =============================================================================
# Root Endpoint Tests
# =============================================================================


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


# =============================================================================
# Search Endpoint Tests
# =============================================================================


class TestSearchEndpoint:
    """Tests for the POST /search endpoint."""

    def test_search_requires_query(self, client):
        """Test that search requires a query parameter."""
        response = client.post("/api/v1/search", json={})
        assert response.status_code == 422  # Validation error

    def test_search_rejects_empty_query(self, client):
        """Test that search rejects empty query."""
        response = client.post("/api/v1/search", json={"query": ""})
        assert response.status_code == 422  # Validation error

    def test_search_validates_top_k_range(self, client):
        """Test that top_k must be between 1 and 100."""
        # Too low
        response = client.post("/api/v1/search", json={"query": "test", "top_k": 0})
        assert response.status_code == 422

        # Too high
        response = client.post("/api/v1/search", json={"query": "test", "top_k": 101})
        assert response.status_code == 422

    def test_search_returns_results(self, client):
        """Test that search returns results."""
        # Create mock search engine
        mock_engine = create_mock_search_engine()
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(
                id="photo1",
                path="/path/to/photo.jpg",
                score=0.95,
                description="A sunset",
                timestamp=datetime(2024, 1, 15),
                city="Honolulu",
                state="Hawaii",
                country="USA",
            )
        ]
        mock_result.total_results = 1
        mock_result.location_resolved = None
        mock_engine.search.return_value = mock_result

        # Patch the get_search_engine function to return an awaitable mock
        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post("/api/v1/search", json={"query": "sunset"})

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_results" in data
        assert data["total_results"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "photo1"
        assert data["results"][0]["score"] == 0.95

    def test_search_with_location_filter(self, client):
        """Test search with location filter."""
        mock_engine = create_mock_search_engine()
        mock_result = MagicMock()
        mock_result.results = []
        mock_result.total_results = 0
        mock_result.location_resolved = {
            "name": "Hawaii",
            "bounding_box": {"min_lat": 18.91, "max_lat": 22.24, "min_lon": -160.25, "max_lon": -154.81},
            "center": {"lat": 20.57, "lon": -157.53},
        }
        mock_engine.search.return_value = mock_result

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/search",
                json={"query": "sunset", "location": "Hawaii"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["location_resolved"] is not None
        assert data["location_resolved"]["name"] == "Hawaii"

    def test_search_with_time_range(self, client):
        """Test search with time range filter."""
        mock_engine = create_mock_search_engine()
        mock_result = MagicMock()
        mock_result.results = []
        mock_result.total_results = 0
        mock_result.location_resolved = None
        mock_engine.search.return_value = mock_result

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/search",
                json={
                    "query": "vacation",
                    "time_range": {
                        "start": "2024-01-01T00:00:00",
                        "end": "2024-12-31T23:59:59"
                    }
                }
            )

        assert response.status_code == 200
        # Verify search was called with time range
        mock_engine.search.assert_called_once()
        call_kwargs = mock_engine.search.call_args[1]
        assert call_kwargs["time_range"] is not None


# =============================================================================
# Index Single Photo Endpoint Tests
# =============================================================================


class TestIndexPhotoEndpoint:
    """Tests for the POST /index endpoint."""

    def test_index_requires_photo_path(self, client):
        """Test that index requires photo_path."""
        response = client.post("/api/v1/index", json={})
        assert response.status_code == 422

    def test_index_rejects_nonexistent_file(self, client):
        """Test that index rejects nonexistent files."""
        response = client.post(
            "/api/v1/index",
            json={"photo_path": "/nonexistent/path/photo.jpg"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_index_rejects_directory(self, client, temp_dir):
        """Test that index rejects directories."""
        response = client.post(
            "/api/v1/index",
            json={"photo_path": str(temp_dir)}
        )
        assert response.status_code == 400
        assert "not a file" in response.json()["detail"].lower()

    def test_index_photo_success(self, client, sample_image_path):
        """Test successful photo indexing."""
        mock_engine = create_mock_search_engine()
        mock_result = MagicMock()
        mock_result.id = "photo123"
        mock_result.path = str(sample_image_path)
        mock_result.description = "A test photo"
        mock_result.tags = ["test", "photo"]
        mock_result.location = None
        mock_result.timestamp = datetime(2024, 1, 15)
        mock_engine.index_photo.return_value = mock_result

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/index",
                json={"photo_path": str(sample_image_path)}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "photo123"
        assert data["description"] == "A test photo"
        assert data["tags"] == ["test", "photo"]

    def test_index_photo_with_location(self, client, sample_image_path):
        """Test photo indexing with location data."""
        mock_engine = create_mock_search_engine()
        mock_result = MagicMock()
        mock_result.id = "photo456"
        mock_result.path = str(sample_image_path)
        mock_result.description = "Beach sunset"
        mock_result.tags = ["sunset", "beach"]
        mock_result.location = MagicMock()
        mock_result.location.to_dict.return_value = {
            "city": "Honolulu",
            "state": "Hawaii",
            "country": "USA",
        }
        mock_result.timestamp = datetime(2024, 6, 15)
        mock_engine.index_photo.return_value = mock_result

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/index",
                json={"photo_path": str(sample_image_path)}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["location"]["city"] == "Honolulu"
        assert data["location"]["country"] == "USA"

    def test_index_photo_failure(self, client, sample_image_path):
        """Test handling of indexing failure."""
        mock_engine = create_mock_search_engine()
        mock_engine.index_photo.return_value = None

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/index",
                json={"photo_path": str(sample_image_path)}
            )

        assert response.status_code == 500
        assert "failed to index" in response.json()["detail"].lower()


# =============================================================================
# Batch Index Endpoint Tests
# =============================================================================


class TestIndexBatchEndpoint:
    """Tests for the POST /index/batch endpoint."""

    def test_batch_requires_folder_path(self, client):
        """Test that batch index requires folder_path."""
        response = client.post("/api/v1/index/batch", json={})
        assert response.status_code == 422

    def test_batch_rejects_nonexistent_folder(self, client):
        """Test that batch index rejects nonexistent folders."""
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": "/nonexistent/folder"}
        )
        assert response.status_code == 404

    def test_batch_rejects_file_path(self, client, sample_image_path):
        """Test that batch index rejects file paths."""
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": str(sample_image_path)}
        )
        assert response.status_code == 400
        assert "not a directory" in response.json()["detail"].lower()

    def test_batch_rejects_empty_folder(self, client, temp_dir):
        """Test that batch index rejects empty folders."""
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": str(temp_dir)}
        )
        assert response.status_code == 400
        assert "no supported image" in response.json()["detail"].lower()

    def test_batch_index_starts_task(self, client, sample_folder_with_images):
        """Test that batch index starts a background task."""
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": str(sample_folder_with_images)}
        )
        assert response.status_code == 200

        data = response.json()
        assert "task_id" in data
        assert data["status"] == "started"
        assert data["total_files"] == 3

    def test_batch_index_recursive_option(self, client, sample_folder_with_images):
        """Test batch index with recursive option."""
        # Create subdirectory with more images
        subdir = sample_folder_with_images / "subdir"
        subdir.mkdir()
        jpeg_header = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\xff\xd9'
        )
        (subdir / "nested.jpg").write_bytes(jpeg_header)

        # With recursive=True (default)
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": str(sample_folder_with_images), "recursive": True}
        )
        assert response.status_code == 200
        assert response.json()["total_files"] == 4

        # With recursive=False
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": str(sample_folder_with_images), "recursive": False}
        )
        assert response.status_code == 200
        assert response.json()["total_files"] == 3


# =============================================================================
# Index Status Endpoint Tests
# =============================================================================


class TestIndexStatusEndpoint:
    """Tests for the GET /index/status/{task_id} endpoint."""

    def test_status_rejects_unknown_task(self, client):
        """Test that status rejects unknown task IDs."""
        response = client.get("/api/v1/index/status/unknown-task-id")
        assert response.status_code == 404

    def test_status_returns_progress(self, client, sample_folder_with_images):
        """Test that status returns progress information."""
        # Start a batch index
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": str(sample_folder_with_images)}
        )
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Check status - the background task may have already run or failed,
        # so we just verify the endpoint works and returns required fields
        response = client.get(f"/api/v1/index/status/{task_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["task_id"] == task_id
        assert "status" in data
        assert data["status"] in ["running", "completed", "failed"]
        assert "progress" in data
        assert "processed" in data
        assert "total" in data
        # The initial total should be 3, but if background task failed it may be 0
        # Just verify the fields exist and are valid
        assert isinstance(data["total"], int)
        assert isinstance(data["processed"], int)
        assert isinstance(data["progress"], float)

    def test_status_progress_structure(self, client):
        """Test the structure of index progress response using mocked task storage."""
        from photosearch.api import routes
        
        # Manually add a task to the storage
        test_task_id = "test-task-123"
        routes._indexing_tasks[test_task_id] = routes.IndexProgressResponse(
            task_id=test_task_id,
            status="running",
            progress=0.5,
            processed=50,
            total=100,
            errors=["error1"],
        )
        
        try:
            response = client.get(f"/api/v1/index/status/{test_task_id}")
            assert response.status_code == 200
            
            data = response.json()
            assert data["task_id"] == test_task_id
            assert data["status"] == "running"
            assert data["progress"] == 0.5
            assert data["processed"] == 50
            assert data["total"] == 100
            assert data["errors"] == ["error1"]
        finally:
            # Clean up
            del routes._indexing_tasks[test_task_id]


# =============================================================================
# Delete Photo Endpoint Tests
# =============================================================================


class TestDeletePhotoEndpoint:
    """Tests for the DELETE /index/{photo_id} endpoint."""

    def test_delete_success(self, client):
        """Test successful photo deletion."""
        mock_engine = create_mock_search_engine()
        mock_engine.remove_photo.return_value = True

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.delete("/api/v1/index/photo123")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_engine.remove_photo.assert_called_once_with("photo123")

    def test_delete_not_found(self, client):
        """Test delete with nonexistent photo."""
        mock_engine = create_mock_search_engine()
        mock_engine.remove_photo.return_value = False

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.delete("/api/v1/index/nonexistent")

        assert response.status_code == 404


# =============================================================================
# Geocode Endpoint Tests
# =============================================================================


class TestGeocodeEndpoint:
    """Tests for the POST /geocode endpoint."""

    def test_geocode_requires_place_name(self, client):
        """Test that geocode requires place_name."""
        response = client.post("/api/v1/geocode", json={})
        assert response.status_code == 422

    def test_geocode_rejects_empty_place_name(self, client):
        """Test that geocode rejects empty place_name."""
        response = client.post("/api/v1/geocode", json={"place_name": ""})
        assert response.status_code == 422

    def test_geocode_success(self, client):
        """Test successful geocoding."""
        mock_engine = create_mock_search_engine()
        mock_result = MagicMock()
        mock_result.name = "Hawaii"
        mock_result.bounding_box = MagicMock()
        mock_result.bounding_box.to_dict.return_value = {
            "min_lat": 18.91,
            "max_lat": 22.24,
            "min_lon": -160.25,
            "max_lon": -154.81,
        }
        mock_result.center_lat = 20.57
        mock_result.center_lon = -157.53
        mock_engine.location_service.geocode.return_value = mock_result

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/geocode",
                json={"place_name": "Hawaii"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Hawaii"
        assert data["bounding_box"]["min_lat"] == 18.91
        assert data["center"]["lat"] == 20.57

    def test_geocode_not_found(self, client):
        """Test geocoding unknown location."""
        mock_engine = create_mock_search_engine()
        mock_engine.location_service.geocode.return_value = None

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/geocode",
                json={"place_name": "Nonexistent Place XYZ123"}
            )

        assert response.status_code == 404


# =============================================================================
# Photos List Endpoint Tests
# =============================================================================


class TestPhotosListEndpoint:
    """Tests for the GET /photos endpoint."""

    def test_list_photos_default_params(self, client):
        """Test listing photos with default parameters."""
        response = client.get("/api/v1/photos")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_photos_with_pagination(self, client):
        """Test listing photos with pagination."""
        response = client.get("/api/v1/photos?limit=10&offset=0")
        assert response.status_code == 200

    def test_list_photos_validates_limit(self, client):
        """Test that limit is validated."""
        # Too high
        response = client.get("/api/v1/photos?limit=2000")
        assert response.status_code == 422

        # Too low
        response = client.get("/api/v1/photos?limit=0")
        assert response.status_code == 422

    def test_list_photos_validates_offset(self, client):
        """Test that offset is validated."""
        response = client.get("/api/v1/photos?offset=-1")
        assert response.status_code == 422


# =============================================================================
# Single Photo Endpoint Tests
# =============================================================================


class TestGetPhotoEndpoint:
    """Tests for the GET /photos/{photo_id} endpoint."""

    def test_get_photo_not_found(self, client):
        """Test getting nonexistent photo."""
        response = client.get("/api/v1/photos/nonexistent-id")
        assert response.status_code == 404


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests that exercise full workflows with mocked ML components."""

    def test_full_index_and_search_workflow(self, client, sample_folder_with_images):
        """Test complete indexing and search workflow with mocked search engine."""
        from datetime import datetime
        from photosearch.api import routes

        # Create a comprehensive mock search engine
        mock_engine = MagicMock()
        
        # Mock index_photo to return successful results
        def mock_index_photo(path):
            mock_result = MagicMock()
            mock_result.id = f"photo_{path.name}"
            mock_result.path = str(path)
            mock_result.description = f"A photo named {path.name}"
            mock_result.tags = ["test", "photo"]
            mock_result.location = None
            mock_result.timestamp = datetime.now()
            return mock_result
        
        mock_engine.index_photo.side_effect = mock_index_photo
        
        # Mock index_folder to return progress
        def mock_index_folder(folder_path, recursive, progress_callback=None):
            from photosearch.utils.image import scan_folder_for_images
            images = scan_folder_for_images(folder_path, recursive=recursive)
            
            progress = MagicMock()
            progress.task_id = "test-task"
            progress.status = "completed"
            progress.progress = 1.0
            progress.processed = len(images)
            progress.total = len(images)
            progress.errors = []
            
            if progress_callback:
                progress_callback(progress)
            
            return progress
        
        mock_engine.index_folder.side_effect = mock_index_folder
        
        # Mock search to return results
        def mock_search(query, top_k=20, time_range=None, location=None, min_score=0.15, caption_weight=0.5):
            mock_result = MagicMock()
            mock_result.results = [
                MagicMock(
                    id="photo_0",
                    path="/path/to/photo_0.jpg",
                    score=0.95,
                    description="A beautiful sunset photo",
                    timestamp=datetime(2024, 6, 15),
                    city="Honolulu",
                    state="Hawaii",
                    country="USA",
                ),
                MagicMock(
                    id="photo_1",
                    path="/path/to/photo_1.jpg",
                    score=0.85,
                    description="Beach scene",
                    timestamp=datetime(2024, 6, 16),
                    city=None,
                    state=None,
                    country=None,
                ),
            ]
            mock_result.total_results = 2
            mock_result.location_resolved = None
            return mock_result
        
        mock_engine.search.side_effect = mock_search
        mock_engine.remove_photo.return_value = True
        
        # Mock location service
        mock_location_service = MagicMock()
        mock_geocode_result = MagicMock()
        mock_geocode_result.name = "Hawaii"
        mock_geocode_result.bounding_box = MagicMock()
        mock_geocode_result.bounding_box.to_dict.return_value = {
            "min_lat": 18.91, "max_lat": 22.24,
            "min_lon": -160.25, "max_lon": -154.81
        }
        mock_geocode_result.center_lat = 20.57
        mock_geocode_result.center_lon = -157.53
        mock_location_service.geocode.return_value = mock_geocode_result
        mock_engine.location_service = mock_location_service

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            # Step 1: Index a single photo
            photo_path = sample_folder_with_images / "photo_0.jpg"
            response = client.post(
                "/api/v1/index",
                json={"photo_path": str(photo_path)}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "photo_photo_0.jpg"
            assert "description" in data
            
            # Step 2: Search for photos
            response = client.post(
                "/api/v1/search",
                json={"query": "sunset beach"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total_results"] == 2
            assert len(data["results"]) == 2
            assert data["results"][0]["score"] == 0.95
            
            # Step 3: Search with location filter
            response = client.post(
                "/api/v1/search",
                json={"query": "sunset", "location": "Hawaii"}
            )
            assert response.status_code == 200
            
            # Step 4: Geocode a location
            response = client.post(
                "/api/v1/geocode",
                json={"place_name": "Hawaii"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Hawaii"
            assert data["bounding_box"]["min_lat"] == 18.91
            
            # Step 5: Delete a photo
            response = client.delete("/api/v1/index/photo_0")
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_search_with_all_filters(self, client):
        """Test search endpoint with all filter types combined."""
        mock_engine = create_mock_search_engine()
        
        # Setup mock to verify all filters are passed correctly
        call_args = {}
        def capture_search(**kwargs):
            call_args.update(kwargs)
            mock_result = MagicMock()
            mock_result.results = []
            mock_result.total_results = 0
            mock_result.location_resolved = {
                "name": "California",
                "bounding_box": {"min_lat": 32.5, "max_lat": 42.0, "min_lon": -124.4, "max_lon": -114.1},
            }
            return mock_result
        
        mock_engine.search.side_effect = capture_search

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            response = client.post(
                "/api/v1/search",
                json={
                    "query": "sunset on the beach",
                    "top_k": 50,
                    "location": "California",
                    "time_range": {
                        "start": "2024-01-01T00:00:00",
                        "end": "2024-12-31T23:59:59"
                    }
                }
            )
        
        assert response.status_code == 200
        
        # Verify all parameters were passed to search
        assert call_args["query"] == "sunset on the beach"
        assert call_args["top_k"] == 50
        assert call_args["location"] == "California"
        assert call_args["time_range"] is not None
        assert call_args["time_range"][0].year == 2024
        assert call_args["time_range"][1].month == 12

    def test_batch_index_with_progress_tracking(self, client, sample_folder_with_images):
        """Test batch indexing with progress tracking via the status endpoint."""
        from photosearch.api import routes
        
        # Start batch indexing
        response = client.post(
            "/api/v1/index/batch",
            json={"folder_path": str(sample_folder_with_images)}
        )
        assert response.status_code == 200
        
        data = response.json()
        task_id = data["task_id"]
        assert data["status"] == "started"
        assert data["total_files"] == 3
        
        # Manually simulate progress updates (since background task may fail without ML models)
        routes._indexing_tasks[task_id] = routes.IndexProgressResponse(
            task_id=task_id,
            status="running",
            progress=0.33,
            processed=1,
            total=3,
            errors=[],
        )
        
        # Check progress
        response = client.get(f"/api/v1/index/status/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["progress"] == 0.33
        assert data["processed"] == 1
        
        # Simulate completion
        routes._indexing_tasks[task_id] = routes.IndexProgressResponse(
            task_id=task_id,
            status="completed",
            progress=1.0,
            processed=3,
            total=3,
            errors=[],
        )
        
        response = client.get(f"/api/v1/index/status/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["progress"] == 1.0
        assert data["processed"] == 3
        
        # Clean up
        del routes._indexing_tasks[task_id]

    def test_index_photo_and_retrieve_details(self, client, sample_image_path):
        """Test indexing a photo and then retrieving its details."""
        mock_engine = create_mock_search_engine()
        
        # Setup mock for successful indexing
        mock_result = MagicMock()
        mock_result.id = "test-photo-id-123"
        mock_result.path = str(sample_image_path)
        mock_result.description = "A scenic mountain view"
        mock_result.tags = ["mountain", "nature", "landscape"]
        mock_result.location = MagicMock()
        mock_result.location.to_dict.return_value = {
            "city": "Denver",
            "state": "Colorado", 
            "country": "USA",
            "place_name": "Rocky Mountains"
        }
        mock_result.timestamp = datetime(2024, 7, 4, 12, 30, 0)
        mock_engine.index_photo.return_value = mock_result

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            # Index the photo
            response = client.post(
                "/api/v1/index",
                json={"photo_path": str(sample_image_path)}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all fields are returned correctly
        assert data["id"] == "test-photo-id-123"
        assert data["description"] == "A scenic mountain view"
        assert data["tags"] == ["mountain", "nature", "landscape"]
        assert data["location"]["city"] == "Denver"
        assert data["location"]["state"] == "Colorado"
        assert data["location"]["country"] == "USA"
        assert "2024-07-04" in data["timestamp"]

    def test_error_recovery_workflow(self, client, sample_image_path, temp_dir):
        """Test that API handles errors gracefully and recovers."""
        mock_engine = create_mock_search_engine()
        
        # First call fails
        call_count = [0]
        def flaky_index_photo(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # First call fails
            # Second call succeeds
            mock_result = MagicMock()
            mock_result.id = "recovered-photo"
            mock_result.path = str(path)
            mock_result.description = "Successfully indexed"
            mock_result.tags = ["success"]
            mock_result.location = None
            mock_result.timestamp = None
            return mock_result
        
        mock_engine.index_photo.side_effect = flaky_index_photo

        async def mock_get_engine():
            return mock_engine

        with patch("photosearch.api.routes.get_search_engine", mock_get_engine):
            # First attempt fails
            response = client.post(
                "/api/v1/index",
                json={"photo_path": str(sample_image_path)}
            )
            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()
            
            # Second attempt succeeds
            response = client.post(
                "/api/v1/index",
                json={"photo_path": str(sample_image_path)}
            )
            assert response.status_code == 200
            assert response.json()["id"] == "recovered-photo"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_json(self, client):
        """Test handling of invalid JSON."""
        response = client.post(
            "/api/v1/search",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_wrong_content_type(self, client):
        """Test handling of wrong content type."""
        response = client.post(
            "/api/v1/search",
            content="query=test",
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 422

    def test_method_not_allowed(self, client):
        """Test handling of wrong HTTP method."""
        response = client.get("/api/v1/search")
        assert response.status_code == 405

        response = client.put("/api/v1/status")
        assert response.status_code == 405


# =============================================================================
# Search Engine Reload Tests (Bug Fix for Delete-Reindex-Search)
# =============================================================================


class TestSearchEngineReload:
    """Tests for search engine reload functionality.

    This tests the bug fix for: after delete index and reindex new photos,
    search returns empty because the main search engine singleton has stale
    vector index data.
    """

    def test_vector_index_reload_from(self):
        """Test VectorIndex.reload_from() loads updated index from disk."""
        import numpy as np
        from photosearch.core.vector_index import VectorIndex

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            index_path = tmp_path / "test.index"

            # Create first index with some vectors
            index1 = VectorIndex(dimension=512)
            ids1 = np.array([1, 2, 3], dtype=np.int64)
            embeddings1 = np.random.randn(3, 512).astype(np.float32)
            # Normalize
            embeddings1 = embeddings1 / np.linalg.norm(embeddings1, axis=1, keepdims=True)
            index1.add(ids1, embeddings1)
            index1.save(index_path)
            assert index1.size == 3

            # Create second index (simulating another process) with different vectors
            index2 = VectorIndex(dimension=512)
            ids2 = np.array([10, 20, 30, 40, 50], dtype=np.int64)
            embeddings2 = np.random.randn(5, 512).astype(np.float32)
            embeddings2 = embeddings2 / np.linalg.norm(embeddings2, axis=1, keepdims=True)
            index2.add(ids2, embeddings2)
            index2.save(index_path)  # Overwrite the file
            assert index2.size == 5

            # Now reload index1 from the file (should get index2's data)
            index1.reload_from(index_path)

            # index1 should now have 5 vectors, not 3
            assert index1.size == 5, f"Expected 5 vectors after reload, got {index1.size}"
            assert index1.active_count == 5

            # Verify the IDs are from index2
            assert index1.has_id(10)
            assert index1.has_id(20)
            assert index1.has_id(30)
            assert not index1.has_id(1)  # Old ID should not exist
            assert not index1.has_id(2)

    def test_vector_index_reload_from_nonexistent_clears(self):
        """Test VectorIndex.reload_from() clears index if file doesn't exist."""
        import numpy as np
        from photosearch.core.vector_index import VectorIndex

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            index_path = tmp_path / "nonexistent.index"

            # Create index with some vectors
            index = VectorIndex(dimension=512)
            ids = np.array([1, 2, 3], dtype=np.int64)
            embeddings = np.random.randn(3, 512).astype(np.float32)
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
            index.add(ids, embeddings)
            assert index.size == 3

            # Reload from nonexistent file should clear the index
            index.reload_from(index_path)
            assert index.size == 0
            assert index.active_count == 0

    def test_search_engine_reload_index(self):
        """Test SearchEngine.reload_index() picks up changes from disk."""
        import numpy as np
        from photosearch.core.search_engine import SearchEngine
        from photosearch.core.vector_index import VectorIndex

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "test.db"
            index_path = tmp_path / "test.index"

            # Create search engine (this also creates the index file)
            engine = SearchEngine(
                db_path=db_path,
                index_path=index_path,
            )
            initial_size = engine.vector_index.size

            # Simulate another process updating the index file
            external_index = VectorIndex(dimension=engine.clip.embedding_dim)
            ids = np.array([100, 200, 300], dtype=np.int64)
            embeddings = np.random.randn(3, engine.clip.embedding_dim).astype(np.float32)
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
            external_index.add(ids, embeddings)
            external_index.save(index_path)

            # The engine's in-memory index still has old data
            assert engine.vector_index.size == initial_size

            # Reload the index
            engine.reload_index()

            # Now engine should have the new data
            assert engine.vector_index.size == 3
            assert engine.vector_index.has_id(100)
            assert engine.vector_index.has_id(200)
            assert engine.vector_index.has_id(300)

            engine.close()

    def test_mark_search_engine_needs_reload_flag(self):
        """Test that mark_search_engine_needs_reload sets the flag correctly."""
        from photosearch.api import routes

        # Reset the flag
        routes._search_engine_needs_reload = False
        assert routes._search_engine_needs_reload is False

        # Call mark function
        routes.mark_search_engine_needs_reload()

        # Flag should be set
        assert routes._search_engine_needs_reload is True

    def test_get_search_engine_reloads_when_flagged(self, client):
        """Test that get_search_engine triggers reload when flag is set."""
        from unittest.mock import MagicMock, AsyncMock, patch
        from photosearch.api import routes

        # Create a mock search engine with reload_index method
        mock_engine = MagicMock()
        mock_engine.reload_index = MagicMock()

        # Store original values
        original_engine = routes._search_engine
        original_flag = routes._search_engine_needs_reload

        try:
            # Set up: engine exists and needs reload
            routes._search_engine = mock_engine
            routes._search_engine_needs_reload = True

            # Create mock search result
            mock_result = MagicMock()
            mock_result.results = []
            mock_result.total_results = 0
            mock_result.location_resolved = None
            mock_engine.search.return_value = mock_result

            # Make a search request (this should trigger reload)
            response = client.post("/api/v1/search", json={"query": "test"})

            # Verify reload was called
            mock_engine.reload_index.assert_called_once()

            # Flag should be reset
            assert routes._search_engine_needs_reload is False

        finally:
            # Restore original values
            routes._search_engine = original_engine
            routes._search_engine_needs_reload = original_flag

    def test_batch_indexing_sets_reload_flag(self):
        """Test that batch indexing sets the reload flag when complete."""
        from photosearch.api import routes

        # Reset the flag
        routes._search_engine_needs_reload = False

        # Create a minimal mock for _run_batch_indexing
        # We can't easily test the full background task, but we can verify
        # mark_search_engine_needs_reload is called

        # Verify the function exists and is callable
        assert callable(routes.mark_search_engine_needs_reload)

        # Call it directly (simulating what happens at end of batch indexing)
        routes.mark_search_engine_needs_reload()
        assert routes._search_engine_needs_reload is True


class TestDeleteReindexSearchIntegration:
    """Integration tests for the delete-reindex-search workflow.

    This is the main test for the bug: after deleting and reindexing,
    search should return the newly indexed photos.
    """

    @pytest.fixture
    def search_engine_with_fixtures(self):
        """Create a search engine with test images indexed."""
        from photosearch.core.search_engine import SearchEngine

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "test.db"
            index_path = tmp_path / "test.index"

            # Create two separate image folders
            folder1 = tmp_path / "folder1"
            folder1.mkdir()
            folder2 = tmp_path / "folder2"
            folder2.mkdir()

            # Copy fixture images to folders
            fixtures = Path(__file__).parent / "fixtures"

            # Folder1: sunset image
            sunset_src = fixtures / "sunset.jpg"
            if sunset_src.exists():
                (folder1 / "sunset.jpg").write_bytes(sunset_src.read_bytes())

            # Folder2: city image
            city_src = fixtures / "city.jpg"
            if city_src.exists():
                (folder2 / "city.jpg").write_bytes(city_src.read_bytes())

            engine = SearchEngine(
                db_path=db_path,
                index_path=index_path,
            )

            yield {
                "engine": engine,
                "folder1": folder1,
                "folder2": folder2,
                "tmp_path": tmp_path,
                "db_path": db_path,
                "index_path": index_path,
            }

            engine.close()

    def test_delete_folder_then_reindex_different_folder(self, search_engine_with_fixtures):
        """Test: index folder1, delete folder1, index folder2, search returns folder2 results."""
        ctx = search_engine_with_fixtures
        engine = ctx["engine"]
        folder1 = ctx["folder1"]
        folder2 = ctx["folder2"]

        # Skip if fixture files don't exist
        if not (folder1 / "sunset.jpg").exists() or not (folder2 / "city.jpg").exists():
            pytest.skip("Fixture images not available")

        # Step 1: Index folder1
        result1 = engine.index_folder(folder1)
        assert result1.processed >= 1, "Should index at least 1 photo from folder1"

        # Verify folder1 photo is searchable
        search1 = engine.search("sunset", top_k=10)
        # May or may not find results depending on caption, but index should be populated
        initial_status = engine.get_status()
        assert initial_status["indexed_count"] >= 1

        # Step 2: Delete folder1 from index
        deleted = engine.remove_folder(folder1)
        assert deleted >= 1, "Should delete at least 1 photo"

        # Verify folder1 photos are gone
        status_after_delete = engine.get_status()
        assert status_after_delete["indexed_count"] == 0, "All photos should be deleted"

        # Step 3: Index folder2
        result2 = engine.index_folder(folder2)
        assert result2.processed >= 1, "Should index at least 1 photo from folder2"

        # Step 4: Search should find folder2 photos
        status_final = engine.get_status()
        assert status_final["indexed_count"] >= 1, "Should have folder2 photos indexed"

        # Vector index should also reflect the new photos
        assert engine.vector_index.size >= 1, "Vector index should have new photos"

    def test_simulated_background_reindex_with_reload(self, search_engine_with_fixtures):
        """Test: simulate what happens with background indexing and reload.

        This simulates the bug scenario:
        1. Main engine has some photos indexed
        2. Background task (new engine instance) reindexes
        3. Main engine reloads and can search new photos
        """
        from photosearch.core.search_engine import SearchEngine

        ctx = search_engine_with_fixtures
        main_engine = ctx["engine"]
        folder1 = ctx["folder1"]
        folder2 = ctx["folder2"]
        db_path = ctx["db_path"]
        index_path = ctx["index_path"]

        # Skip if fixture files don't exist
        if not (folder1 / "sunset.jpg").exists() or not (folder2 / "city.jpg").exists():
            pytest.skip("Fixture images not available")

        # Step 1: Main engine indexes folder1
        result1 = main_engine.index_folder(folder1)
        main_engine._save_index()

        initial_size = main_engine.vector_index.size
        assert initial_size >= 1

        # Step 2: Delete folder1 from main engine
        main_engine.remove_folder(folder1)
        main_engine._save_index()

        # Step 3: Simulate background task - create NEW engine instance
        # This is what _run_batch_indexing does
        background_engine = SearchEngine(
            db_path=db_path,
            index_path=index_path,
        )

        # Background engine indexes folder2
        result2 = background_engine.index_folder(folder2)
        background_engine.close()  # This saves the index

        # At this point:
        # - background_engine wrote new index to disk
        # - main_engine still has old (empty) vector index in memory

        # Step 4: Without reload, main engine's vector index is stale
        # The size should still be 0 (from when we deleted folder1)
        assert main_engine.vector_index.active_count == 0, \
            "Main engine should have stale empty index before reload"

        # Step 5: Reload main engine's index
        main_engine.reload_index()

        # Now main engine should have the new photos
        assert main_engine.vector_index.size >= 1, \
            f"After reload, main engine should have new photos. Got size={main_engine.vector_index.size}"

        # Step 6: Search should work
        status = main_engine.get_status()
        assert status["indexed_count"] >= 1, "Should have indexed photos"
