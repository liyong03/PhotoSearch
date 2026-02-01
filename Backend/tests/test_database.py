"""Tests for database operations."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from photosearch.database import Database
from photosearch.models import PhotoCreate, PhotoUpdate


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield Database(db_path)


@pytest.fixture
def sample_photo():
    """Create a sample photo for testing."""
    return PhotoCreate(
        file_path="/path/to/photo.jpg",
        filename="photo.jpg",
        timestamp=datetime(2024, 6, 15, 14, 30, 0),
        latitude=21.3069,
        longitude=-157.8583,
        city="Honolulu",
        state="Hawaii",
        country="USA",
        place_name="Waikiki Beach",
        description="A beautiful sunset over the ocean with palm trees",
        tags=["sunset", "beach", "ocean", "hawaii"],
    )


class TestDatabaseCreation:
    """Tests for database creation and schema."""

    def test_create_database(self, db):
        """Test that database is created with correct schema."""
        # Database should be created
        assert db.db_path.exists()

        # Should have photos table
        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='photos'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_create_database_with_fts(self, db):
        """Test that FTS virtual table is created."""
        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='photos_fts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_create_database_with_embeddings_table(self, db):
        """Test that embeddings table is created."""
        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
        )
        assert cursor.fetchone() is not None
        conn.close()


class TestPhotoInsert:
    """Tests for inserting photo records."""

    def test_insert_photo(self, db, sample_photo):
        """Test inserting a photo record."""
        photo = db.create_photo(sample_photo)

        assert photo.id is not None
        assert photo.file_path == sample_photo.file_path
        assert photo.filename == sample_photo.filename
        assert photo.timestamp == sample_photo.timestamp
        assert photo.latitude == sample_photo.latitude
        assert photo.longitude == sample_photo.longitude
        assert photo.city == sample_photo.city
        assert photo.description == sample_photo.description
        assert photo.tags == sample_photo.tags
        assert photo.indexed_at is not None

    def test_insert_photo_minimal(self, db):
        """Test inserting a photo with minimal fields."""
        photo_create = PhotoCreate(
            file_path="/path/to/minimal.jpg",
            filename="minimal.jpg",
        )
        photo = db.create_photo(photo_create)

        assert photo.id is not None
        assert photo.file_path == "/path/to/minimal.jpg"
        assert photo.timestamp is None
        assert photo.latitude is None
        assert photo.tags == []

    def test_insert_duplicate_path_fails(self, db, sample_photo):
        """Test that inserting duplicate file path fails."""
        db.create_photo(sample_photo)

        with pytest.raises(Exception):  # sqlite3.IntegrityError
            db.create_photo(sample_photo)


class TestPhotoQuery:
    """Tests for querying photo records."""

    def test_get_photo_by_id(self, db, sample_photo):
        """Test retrieving a photo by ID."""
        created = db.create_photo(sample_photo)
        retrieved = db.get_photo(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.file_path == created.file_path

    def test_get_photo_by_path(self, db, sample_photo):
        """Test retrieving a photo by file path."""
        created = db.create_photo(sample_photo)
        retrieved = db.get_photo_by_path(sample_photo.file_path)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.file_path == sample_photo.file_path

    def test_get_nonexistent_photo(self, db):
        """Test retrieving a non-existent photo returns None."""
        retrieved = db.get_photo("nonexistent-id")
        assert retrieved is None

    def test_get_nonexistent_path(self, db):
        """Test retrieving by non-existent path returns None."""
        retrieved = db.get_photo_by_path("/nonexistent/path.jpg")
        assert retrieved is None


class TestPhotoUpdate:
    """Tests for updating photo records."""

    def test_update_photo(self, db, sample_photo):
        """Test updating a photo record."""
        created = db.create_photo(sample_photo)

        update = PhotoUpdate(
            description="Updated description",
            city="Maui",
        )
        updated = db.update_photo(created.id, update)

        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.city == "Maui"
        # Unchanged fields should remain
        assert updated.file_path == created.file_path
        assert updated.latitude == created.latitude

    def test_update_photo_tags(self, db, sample_photo):
        """Test updating photo tags."""
        created = db.create_photo(sample_photo)

        update = PhotoUpdate(tags=["new", "tags"])
        updated = db.update_photo(created.id, update)

        assert updated is not None
        assert updated.tags == ["new", "tags"]

    def test_update_nonexistent_photo(self, db):
        """Test updating a non-existent photo returns None."""
        update = PhotoUpdate(description="test")
        result = db.update_photo("nonexistent-id", update)
        assert result is None


class TestPhotoDelete:
    """Tests for deleting photo records."""

    def test_delete_photo(self, db, sample_photo):
        """Test deleting a photo record."""
        created = db.create_photo(sample_photo)

        result = db.delete_photo(created.id)
        assert result is True

        # Should no longer exist
        retrieved = db.get_photo(created.id)
        assert retrieved is None

    def test_delete_nonexistent_photo(self, db):
        """Test deleting a non-existent photo returns False."""
        result = db.delete_photo("nonexistent-id")
        assert result is False


class TestPhotoList:
    """Tests for listing photos."""

    def test_list_photos(self, db):
        """Test listing photos with pagination."""
        # Create multiple photos
        for i in range(5):
            db.create_photo(
                PhotoCreate(
                    file_path=f"/path/to/photo{i}.jpg",
                    filename=f"photo{i}.jpg",
                )
            )

        photos = db.list_photos(limit=3)
        assert len(photos) == 3

    def test_list_photos_offset(self, db):
        """Test listing photos with offset."""
        # Create multiple photos
        for i in range(5):
            db.create_photo(
                PhotoCreate(
                    file_path=f"/path/to/photo{i}.jpg",
                    filename=f"photo{i}.jpg",
                )
            )

        photos = db.list_photos(limit=10, offset=2)
        assert len(photos) == 3

    def test_count_photos(self, db):
        """Test counting photos."""
        assert db.count_photos() == 0

        for i in range(3):
            db.create_photo(
                PhotoCreate(
                    file_path=f"/path/to/photo{i}.jpg",
                    filename=f"photo{i}.jpg",
                )
            )

        assert db.count_photos() == 3


class TestFullTextSearch:
    """Tests for full-text search."""

    def test_fts_search_description(self, db):
        """Test full-text search on description."""
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/sunset.jpg",
                filename="sunset.jpg",
                description="A beautiful sunset over the ocean",
            )
        )
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/cat.jpg",
                filename="cat.jpg",
                description="A cute cat sleeping on a couch",
            )
        )

        results = db.search_fts("sunset")
        assert len(results) == 1
        assert results[0].filename == "sunset.jpg"

    def test_fts_search_city(self, db):
        """Test full-text search on city."""
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/hawaii.jpg",
                filename="hawaii.jpg",
                city="Honolulu",
            )
        )
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/paris.jpg",
                filename="paris.jpg",
                city="Paris",
            )
        )

        results = db.search_fts("Honolulu")
        assert len(results) == 1
        assert results[0].city == "Honolulu"

    def test_fts_search_no_results(self, db, sample_photo):
        """Test full-text search with no matches."""
        db.create_photo(sample_photo)

        results = db.search_fts("nonexistent")
        assert len(results) == 0


class TestLocationSearch:
    """Tests for location-based search."""

    def test_search_by_location(self, db):
        """Test searching photos by bounding box."""
        # Hawaii photo
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/hawaii.jpg",
                filename="hawaii.jpg",
                latitude=21.3069,
                longitude=-157.8583,
            )
        )
        # Paris photo
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/paris.jpg",
                filename="paris.jpg",
                latitude=48.8566,
                longitude=2.3522,
            )
        )

        # Search Hawaii bounding box
        results = db.search_by_location(
            min_lat=18.0,
            max_lat=23.0,
            min_lon=-161.0,
            max_lon=-154.0,
        )
        assert len(results) == 1
        assert results[0].filename == "hawaii.jpg"


class TestTimeSearch:
    """Tests for time-based search."""

    def test_search_by_time_range(self, db):
        """Test searching photos by time range."""
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/old.jpg",
                filename="old.jpg",
                timestamp=datetime(2020, 1, 1),
            )
        )
        db.create_photo(
            PhotoCreate(
                file_path="/path/to/new.jpg",
                filename="new.jpg",
                timestamp=datetime(2024, 6, 15),
            )
        )

        results = db.search_by_time_range(
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 12, 31),
        )
        assert len(results) == 1
        assert results[0].filename == "new.jpg"


class TestBulkOperations:
    """Tests for bulk operations."""

    def test_get_photos_by_ids(self, db):
        """Test getting multiple photos by IDs."""
        created_ids = []
        for i in range(5):
            photo = db.create_photo(
                PhotoCreate(
                    file_path=f"/path/to/photo{i}.jpg",
                    filename=f"photo{i}.jpg",
                )
            )
            created_ids.append(photo.id)

        # Get subset
        photos = db.get_photos_by_ids(created_ids[:3])
        assert len(photos) == 3

    def test_get_all_file_paths(self, db):
        """Test getting all indexed file paths."""
        paths = {f"/path/to/photo{i}.jpg" for i in range(5)}
        for path in paths:
            db.create_photo(
                PhotoCreate(
                    file_path=path,
                    filename=path.split("/")[-1],
                )
            )

        result = db.get_all_file_paths()
        assert result == paths


class TestEmbeddingMapping:
    """Tests for embedding index mapping."""

    def test_save_embedding_mapping(self, db, sample_photo):
        """Test saving embedding mapping."""
        photo = db.create_photo(sample_photo)
        db.save_embedding_mapping(photo.id, 42)

        mapping = db.get_embedding_mapping([42])
        assert mapping[42] == photo.id

    def test_get_embedding_mapping_multiple(self, db):
        """Test getting multiple embedding mappings."""
        photos = []
        for i in range(3):
            photo = db.create_photo(
                PhotoCreate(
                    file_path=f"/path/to/photo{i}.jpg",
                    filename=f"photo{i}.jpg",
                )
            )
            photos.append(photo)
            db.save_embedding_mapping(photo.id, i)

        mapping = db.get_embedding_mapping([0, 1, 2])
        assert len(mapping) == 3
        for i, photo in enumerate(photos):
            assert mapping[i] == photo.id
