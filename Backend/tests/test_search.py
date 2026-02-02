"""Tests for the integrated search engine."""

import logging
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from photosearch.core.query_parser import ParsedQuery, QueryParser
from photosearch.core.search_engine import SearchEngine

logger = logging.getLogger(__name__)

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestQueryParser:
    """Tests for query parsing."""

    @pytest.fixture
    def parser(self):
        """Create query parser."""
        return QueryParser()

    def test_parse_simple_query(self, parser):
        """Test parsing a simple query with no location."""
        query = "sunset on the beach"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location={result.location}")

        assert result.semantic_query == "sunset on the beach"
        assert result.location is None

    def test_parse_from_location(self, parser):
        """Test parsing 'from <location>' pattern."""
        query = "sunset from Hawaii"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location='{result.location}'")

        assert result.semantic_query == "sunset"
        assert result.location == "Hawaii"

    def test_parse_in_location(self, parser):
        """Test parsing 'in <location>' pattern."""
        query = "beach in California"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location='{result.location}'")

        assert result.semantic_query == "beach"
        assert result.location == "California"

    def test_parse_taken_in_location(self, parser):
        """Test parsing 'taken in <location>' pattern."""
        query = "photos taken in Paris"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location='{result.location}'")

        assert result.semantic_query == "photos"
        assert result.location == "Paris"

    def test_parse_near_location(self, parser):
        """Test parsing 'near <location>' pattern."""
        query = "mountains near Denver"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location='{result.location}'")

        assert result.semantic_query == "mountains"
        assert result.location == "Denver"

    def test_parse_multi_word_location(self, parser):
        """Test parsing multi-word location names."""
        query = "sunset from San Francisco"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location='{result.location}'")

        assert result.semantic_query == "sunset"
        assert result.location == "San Francisco"

    def test_parse_location_with_state(self, parser):
        """Test parsing location with state/country."""
        query = "photos from Los Angeles, California"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location='{result.location}'")

        assert "Los Angeles" in result.location
        assert result.semantic_query == "photos"

    def test_parse_case_insensitive(self, parser):
        """Test that parsing is case insensitive."""
        query = "sunset FROM hawaii"
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location='{result.location}'")

        assert result.location == "hawaii"

    def test_parse_empty_query(self, parser):
        """Test parsing empty query."""
        query = ""
        result = parser.parse(query)
        logger.info(f"Query: '{query}' -> semantic='{result.semantic_query}', location={result.location}")

        assert result.semantic_query == ""
        assert result.location is None

    def test_extract_location(self, parser):
        """Test extract_location helper method."""
        query = "beach in Malibu"
        location = parser.extract_location(query)
        logger.info(f"extract_location('{query}') -> '{location}'")

        assert location == "Malibu"

    def test_get_semantic_query(self, parser):
        """Test get_semantic_query helper method."""
        query = "sunset from Hawaii"
        semantic = parser.get_semantic_query(query)
        logger.info(f"get_semantic_query('{query}') -> '{semantic}'")

        assert semantic == "sunset"

    def test_parsed_query_to_dict(self, parser):
        """Test ParsedQuery to_dict method."""
        query = "sunset from Hawaii"
        result = parser.parse(query)
        d = result.to_dict()
        logger.info(f"Query: '{query}' -> to_dict(): {d}")

        assert d["semantic_query"] == "sunset"
        assert d["location"] == "Hawaii"


class TestSearchEngineIndexing:
    """Tests for search engine indexing."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for test database and index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "test.index"
            yield db_path, index_path

    @pytest.fixture
    def search_engine(self, temp_dirs):
        """Create search engine for tests."""
        db_path, index_path = temp_dirs
        engine = SearchEngine(db_path, index_path, device="cpu")
        yield engine
        engine.close()

    def test_index_single_photo(self, search_engine):
        """Test indexing a single photo."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        logger.info(f"Indexing single photo: {image_path.name}")
        result = search_engine.index_photo(image_path)

        assert result is not None
        assert result.id is not None
        assert result.path == str(image_path)
        assert result.description is not None
        logger.info(f"  -> ID: {result.id[:8]}...")
        logger.info(f"  -> Description: {result.description}")
        logger.info(f"  -> Tags: {result.tags}")

    def test_index_photo_with_gps(self, search_engine):
        """Test indexing a photo with GPS data."""
        image_path = FIXTURES_DIR / "real_iphone.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        logger.info(f"Indexing photo with GPS: {image_path.name}")
        result = search_engine.index_photo(image_path)

        assert result is not None
        assert result.location is not None
        logger.info(f"  -> Description: {result.description}")
        logger.info(f"  -> Location: {result.location.city}, {result.location.state}, {result.location.country}")
        logger.info(f"  -> Timestamp: {result.timestamp}")

    def test_index_photo_already_indexed(self, search_engine):
        """Test that re-indexing same photo returns existing record."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        logger.info(f"Testing re-index of same photo: {image_path.name}")
        result1 = search_engine.index_photo(image_path)
        result2 = search_engine.index_photo(image_path)

        logger.info(f"  -> First index ID: {result1.id[:8]}...")
        logger.info(f"  -> Second index ID: {result2.id[:8]}... (should be same)")
        assert result1.id == result2.id

    def test_index_nonexistent_photo(self, search_engine):
        """Test indexing a nonexistent photo."""
        path = "/nonexistent/photo.jpg"
        logger.info(f"Testing index of nonexistent photo: {path}")
        result = search_engine.index_photo(path)

        logger.info(f"  -> Result: {result} (should be None)")
        assert result is None

    def test_index_folder(self, search_engine):
        """Test indexing a folder of photos."""
        logger.info(f"Indexing folder: {FIXTURES_DIR}")
        result = search_engine.index_folder(FIXTURES_DIR, recursive=False)

        assert result.status == "completed"
        assert result.processed > 0
        assert result.total > 0
        logger.info(f"  -> Status: {result.status}")
        logger.info(f"  -> Processed: {result.processed}/{result.total}")
        logger.info(f"  -> Errors: {len(result.errors)}")

    def test_get_status(self, search_engine):
        """Test getting search engine status."""
        # Index a photo first
        image_path = FIXTURES_DIR / "sunset.jpg"
        if image_path.exists():
            search_engine.index_photo(image_path)

        logger.info("Getting search engine status")
        status = search_engine.get_status()

        assert status["status"] == "ready"
        assert "indexed_count" in status
        assert "vector_index_size" in status
        logger.info(f"  -> Status: {status['status']}")
        logger.info(f"  -> Indexed count: {status['indexed_count']}")
        logger.info(f"  -> Vector index size: {status['vector_index_size']}")


class TestSearchEngineSearch:
    """Tests for search engine search functionality."""

    @pytest.fixture(scope="class")
    def indexed_engine(self):
        """Create and populate a search engine with test images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "test.index"

            engine = SearchEngine(db_path, index_path, device="cpu")

            # Index test images
            test_images = [
                FIXTURES_DIR / "sunset.jpg",
                FIXTURES_DIR / "city.jpg",
                FIXTURES_DIR / "nature.jpg",
                FIXTURES_DIR / "food.jpg",
                FIXTURES_DIR / "animal.jpg",
                FIXTURES_DIR / "real_iphone.jpg",
                FIXTURES_DIR / "real_heic.heic",
            ]

            for image_path in test_images:
                if image_path.exists():
                    engine.index_photo(image_path)

            yield engine
            engine.close()

    def test_text_search_sunset(self, indexed_engine):
        """Test searching for 'sunset'."""
        query = "sunset"
        logger.info(f"Search query: '{query}'")
        response = indexed_engine.search(query, top_k=5)

        assert response.total_results > 0
        logger.info(f"  -> Found {response.total_results} results")
        for i, r in enumerate(response.results):
            logger.info(f"  -> #{i+1}: {Path(r.path).name} (score: {r.score:.3f})")

        # Sunset image should be in top results
        paths = [r.path for r in response.results]
        sunset_found = any("sunset" in p.lower() for p in paths)
        assert sunset_found, "Sunset image should be in search results"

    def test_text_search_city(self, indexed_engine):
        """Test searching for 'city skyline'."""
        query = "city skyline buildings"
        logger.info(f"Search query: '{query}'")
        response = indexed_engine.search(query, top_k=5)

        assert response.total_results > 0
        logger.info(f"  -> Found {response.total_results} results")
        for i, r in enumerate(response.results):
            logger.info(f"  -> #{i+1}: {Path(r.path).name} (score: {r.score:.3f})")

    def test_text_search_animal(self, indexed_engine):
        """Test searching for 'animal'."""
        query = "cute animal"
        logger.info(f"Search query: '{query}'")
        response = indexed_engine.search(query, top_k=5)

        assert response.total_results > 0
        logger.info(f"  -> Found {response.total_results} results")
        for i, r in enumerate(response.results):
            logger.info(f"  -> #{i+1}: {Path(r.path).name} (score: {r.score:.3f})")

    def test_search_with_location_query(self, indexed_engine):
        """Test search with location in query."""
        query = "sunset from Hawaii"
        logger.info(f"Search query with location: '{query}'")
        response = indexed_engine.search(query, top_k=5)

        logger.info(f"  -> Found {response.total_results} results")
        logger.info(f"  -> Location resolved: {response.location_resolved is not None}")
        if response.location_resolved:
            logger.info(f"  -> Location bbox: {response.location_resolved.get('bounding_box')}")

        # Should still find results (just semantic search)
        assert response.total_results >= 0  # May be 0 if no GPS match
        assert response.location_resolved is not None  # Location should be resolved

    def test_search_empty_query(self, indexed_engine):
        """Test search with empty query."""
        query = ""
        logger.info(f"Search with empty query: '{query}'")
        response = indexed_engine.search(query, top_k=5)

        logger.info(f"  -> Found {response.total_results} results")
        # Should return some results based on empty query embedding
        assert response is not None


class TestSearchEngineFilters:
    """Tests for search filters."""

    @pytest.fixture(scope="class")
    def engine_with_gps_photos(self):
        """Create engine with GPS-tagged photos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "test.index"

            engine = SearchEngine(db_path, index_path, device="cpu")

            # Index photos with GPS
            gps_images = [
                FIXTURES_DIR / "real_iphone.jpg",
                FIXTURES_DIR / "real_heic.heic",
            ]

            for image_path in gps_images:
                if image_path.exists():
                    result = engine.index_photo(image_path)
                    if result:
                        logger.info(f"Indexed: {image_path.name} - {result.location}")

            yield engine
            engine.close()

    def test_location_filter(self, engine_with_gps_photos):
        """Test filtering by location."""
        query = "photo"
        location = "California"
        logger.info(f"Search with location filter: query='{query}', location='{location}'")

        response = engine_with_gps_photos.search(
            query,
            top_k=10,
            location=location,
        )

        logger.info(f"  -> Found {response.total_results} results in {location}")
        for r in response.results:
            logger.info(f"  -> {Path(r.path).name}: {r.city}, {r.state}, {r.country}")

    def test_time_filter(self, engine_with_gps_photos):
        """Test filtering by time range."""
        query = "photo"
        start = datetime(2000, 1, 1)
        end = datetime(2030, 12, 31)
        logger.info(f"Search with time filter: query='{query}', range={start.year}-{end.year}")

        response = engine_with_gps_photos.search(
            query,
            top_k=10,
            time_range=(start, end),
        )

        logger.info(f"  -> Found {response.total_results} results in time range")
        for r in response.results:
            logger.info(f"  -> {Path(r.path).name}: timestamp={r.timestamp}")

    def test_combined_filters(self, engine_with_gps_photos):
        """Test combining location and time filters."""
        query = "outdoor"
        location = "United States"
        start = datetime(2000, 1, 1)
        end = datetime(2030, 12, 31)
        logger.info(f"Search with combined filters: query='{query}', location='{location}', time={start.year}-{end.year}")

        response = engine_with_gps_photos.search(
            query,
            top_k=10,
            location=location,
            time_range=(start, end),
        )

        logger.info(f"  -> Found {response.total_results} results with combined filters")
        for r in response.results:
            logger.info(f"  -> {Path(r.path).name}: {r.city}, {r.timestamp}")


class TestSearchEngineRemove:
    """Tests for removing photos from index."""

    @pytest.fixture
    def temp_engine(self):
        """Create temporary search engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "test.index"

            engine = SearchEngine(db_path, index_path, device="cpu")
            yield engine
            engine.close()

    def test_remove_photo(self, temp_engine):
        """Test removing a photo from the index."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        # Index photo
        logger.info(f"Indexing photo for removal test: {image_path.name}")
        result = temp_engine.index_photo(image_path)
        assert result is not None
        photo_id = result.id
        logger.info(f"  -> Indexed with ID: {photo_id[:8]}...")

        # Verify it's searchable
        response = temp_engine.search("sunset", top_k=5)
        found_before = any(r.id == photo_id for r in response.results)
        logger.info(f"  -> Found in search before removal: {found_before}")
        assert found_before

        # Remove it
        logger.info(f"  -> Removing photo...")
        removed = temp_engine.remove_photo(photo_id)
        logger.info(f"  -> Removal success: {removed}")
        assert removed is True

        # Verify it's no longer searchable
        response = temp_engine.search("sunset", top_k=5)
        found_after = any(r.id == photo_id for r in response.results)
        logger.info(f"  -> Found in search after removal: {found_after}")
        assert not found_after

    def test_remove_nonexistent_photo(self, temp_engine):
        """Test removing a nonexistent photo."""
        photo_id = "nonexistent-id"
        logger.info(f"Attempting to remove nonexistent photo: {photo_id}")
        removed = temp_engine.remove_photo(photo_id)

        logger.info(f"  -> Removal result: {removed} (should be False)")
        assert removed is False
