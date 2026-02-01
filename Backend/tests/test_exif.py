"""Tests for EXIF extraction utilities."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photosearch.utils.exif import (
    extract_exif_data,
    extract_metadata,
    get_file_timestamp,
)
from photosearch.utils.image import (
    load_image,
    get_image_dimensions,
    is_supported_image,
    scan_folder_for_images,
)


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestExtractExifData:
    """Tests for extract_exif_data function."""

    def test_extract_full_exif_hawaii(self):
        """Test extracting full EXIF data from Hawaii photo."""
        exif = extract_exif_data(FIXTURES_DIR / "hawaii_sunset.jpg")

        # Timestamp
        assert exif.timestamp is not None
        assert exif.timestamp.year == 2024
        assert exif.timestamp.month == 6
        assert exif.timestamp.day == 15
        assert exif.timestamp.hour == 18
        assert exif.timestamp.minute == 30

        # GPS - Waikiki Beach coordinates
        assert exif.latitude is not None
        assert exif.longitude is not None
        assert abs(exif.latitude - 21.2769) < 0.01
        assert abs(exif.longitude - (-157.8268)) < 0.01

        # Camera info
        assert exif.camera_make == "Apple"
        assert exif.camera_model == "iPhone 15 Pro"

        # Dimensions
        assert exif.width == 200
        assert exif.height == 150

    def test_extract_full_exif_paris(self):
        """Test extracting EXIF from Paris photo."""
        exif = extract_exif_data(FIXTURES_DIR / "paris_tower.jpg")

        assert exif.timestamp.year == 2023
        assert exif.timestamp.month == 4
        # Eiffel Tower coordinates
        assert abs(exif.latitude - 48.8584) < 0.01
        assert abs(exif.longitude - 2.2945) < 0.01
        assert exif.camera_make == "Canon"

    def test_extract_timestamp_only(self):
        """Test extracting from photo with only timestamp (no GPS)."""
        exif = extract_exif_data(FIXTURES_DIR / "christmas_morning.jpg")

        assert exif.timestamp is not None
        assert exif.timestamp.year == 2022
        assert exif.timestamp.month == 12
        assert exif.timestamp.day == 25
        assert exif.latitude is None
        assert exif.longitude is None
        assert exif.camera_make == "Sony"

    def test_extract_gps_only(self):
        """Test extracting from photo with only GPS (no timestamp)."""
        exif = extract_exif_data(FIXTURES_DIR / "tokyo_street.jpg")

        assert exif.timestamp is None
        # Tokyo coordinates
        assert exif.latitude is not None
        assert abs(exif.latitude - 35.6762) < 0.01
        assert abs(exif.longitude - 139.6503) < 0.01

    def test_extract_southern_hemisphere(self):
        """Test GPS extraction for southern hemisphere (negative latitude)."""
        exif = extract_exif_data(FIXTURES_DIR / "sydney_opera.jpg")

        # Sydney - negative latitude
        assert exif.latitude is not None
        assert exif.latitude < 0  # Southern hemisphere
        assert abs(exif.latitude - (-33.8688)) < 0.01
        assert abs(exif.longitude - 151.2093) < 0.01

    def test_no_exif_png(self):
        """Test handling PNG image without EXIF data."""
        exif = extract_exif_data(FIXTURES_DIR / "no_exif.png")

        assert exif.timestamp is None
        assert exif.latitude is None
        assert exif.longitude is None
        assert exif.camera_make is None
        # Dimensions should still be available
        assert exif.width == 200
        assert exif.height == 150

    def test_minimal_exif(self):
        """Test handling image with minimal/empty EXIF."""
        exif = extract_exif_data(FIXTURES_DIR / "minimal_exif.jpg")

        assert exif.timestamp is None
        assert exif.latitude is None
        assert exif.width == 200

    def test_nonexistent_file(self):
        """Test handling non-existent file."""
        exif = extract_exif_data("/nonexistent/path/image.jpg")

        assert exif.timestamp is None
        assert exif.latitude is None
        assert exif.width is None

    def test_corrupted_file(self, temp_dir):
        """Test handling corrupted file gracefully."""
        corrupted = temp_dir / "corrupted.jpg"
        corrupted.write_bytes(b"This is not a valid image file")

        exif = extract_exif_data(corrupted)

        # Should return empty ExifData, not crash
        assert exif.timestamp is None
        assert exif.latitude is None
        assert exif.width is None


class TestExtractMetadata:
    """Tests for extract_metadata function with fallbacks."""

    def test_uses_exif_timestamp(self):
        """Test that EXIF timestamp is used when available."""
        exif = extract_metadata(FIXTURES_DIR / "hawaii_sunset.jpg")

        assert exif.timestamp is not None
        assert exif.timestamp.year == 2024

    def test_fallback_to_file_timestamp(self):
        """Test fallback to file modification time."""
        exif = extract_metadata(FIXTURES_DIR / "no_exif.png")

        # Should have a timestamp from file mtime
        assert exif.timestamp is not None


class TestGetFileTimestamp:
    """Tests for get_file_timestamp function."""

    def test_get_file_timestamp(self):
        """Test getting file modification timestamp."""
        ts = get_file_timestamp(FIXTURES_DIR / "no_exif.png")

        assert ts is not None
        assert isinstance(ts, datetime)

    def test_nonexistent_file(self):
        """Test handling non-existent file."""
        ts = get_file_timestamp("/nonexistent/path.jpg")

        assert ts is None


class TestLoadImage:
    """Tests for load_image function."""

    def test_load_jpeg(self):
        """Test loading JPEG image."""
        img = load_image(FIXTURES_DIR / "hawaii_sunset.jpg")

        assert img is not None
        assert img.size == (200, 150)
        assert img.mode == "RGB"

    def test_load_png(self):
        """Test loading PNG image."""
        img = load_image(FIXTURES_DIR / "no_exif.png")

        assert img is not None
        assert img.size == (200, 150)

    def test_load_nonexistent(self):
        """Test loading non-existent file."""
        img = load_image("/nonexistent/path.jpg")

        assert img is None

    def test_load_corrupted(self, temp_dir):
        """Test loading corrupted file."""
        corrupted = temp_dir / "corrupted.jpg"
        corrupted.write_bytes(b"not an image")

        img = load_image(corrupted)

        assert img is None


class TestGetImageDimensions:
    """Tests for get_image_dimensions function."""

    def test_get_dimensions(self):
        """Test getting image dimensions."""
        dims = get_image_dimensions(FIXTURES_DIR / "hawaii_sunset.jpg")

        assert dims == (200, 150)

    def test_nonexistent_file(self):
        """Test handling non-existent file."""
        dims = get_image_dimensions("/nonexistent/path.jpg")

        assert dims is None


class TestIsSupportedImage:
    """Tests for is_supported_image function."""

    def test_supported_extensions(self):
        """Test recognized image extensions."""
        assert is_supported_image("photo.jpg") is True
        assert is_supported_image("photo.JPEG") is True
        assert is_supported_image("photo.png") is True
        assert is_supported_image("photo.heic") is True
        assert is_supported_image("photo.HEIF") is True
        assert is_supported_image("photo.webp") is True

    def test_unsupported_extensions(self):
        """Test unsupported file types."""
        assert is_supported_image("document.pdf") is False
        assert is_supported_image("video.mp4") is False
        assert is_supported_image("text.txt") is False


class TestScanFolderForImages:
    """Tests for scan_folder_for_images function."""

    def test_scan_fixtures_folder(self):
        """Test scanning the fixtures folder."""
        images = scan_folder_for_images(FIXTURES_DIR, recursive=False)

        # Should find our generated fixtures (excluding README.md and .py)
        assert len(images) >= 7
        assert all(is_supported_image(p) for p in images)

    def test_scan_recursive(self, temp_dir):
        """Test recursive folder scanning."""
        # Create nested structure
        subdir = temp_dir / "subdir"
        subdir.mkdir()

        img = Image.new("RGB", (10, 10), (255, 0, 0))
        img.save(temp_dir / "root.jpg")
        img.save(subdir / "nested.jpg")

        images = scan_folder_for_images(temp_dir, recursive=True)
        assert len(images) == 2

        images_flat = scan_folder_for_images(temp_dir, recursive=False)
        assert len(images_flat) == 1

    def test_scan_nonexistent_folder(self):
        """Test scanning non-existent folder."""
        images = scan_folder_for_images("/nonexistent/folder")

        assert images == []


class TestRealWorldPhotos:
    """Integration tests with real-world photos if available."""

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "real_iphone.jpg").exists(),
        reason="Real iPhone photo not available"
    )
    def test_real_iphone_photo(self):
        """Test with real iPhone photo (add real_iphone.jpg to fixtures)."""
        exif = extract_exif_data(FIXTURES_DIR / "real_iphone.jpg")

        # Real iPhone photos should have timestamp and GPS
        assert exif.timestamp is not None
        assert exif.timestamp.year == 2017
        assert exif.timestamp.month == 3
        assert exif.timestamp.day == 28

        # Camera info
        assert exif.camera_make == "Apple"
        assert "iPhone" in exif.camera_model

        # GPS - Mountain View/Sunnyvale area, California
        assert exif.latitude is not None
        assert exif.longitude is not None
        assert abs(exif.latitude - 37.404) < 0.01
        assert abs(exif.longitude - (-122.035)) < 0.01

        # Dimensions
        assert exif.width == 4032
        assert exif.height == 3024

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "real_heic.heic").exists(),
        reason="Real HEIC photo not available"
    )
    def test_real_heic_photo(self):
        """Test with real HEIC photo (add real_heic.heic to fixtures)."""
        exif = extract_exif_data(FIXTURES_DIR / "real_heic.heic")

        # Should be able to read HEIC
        assert exif.width == 4032
        assert exif.height == 3024

        # Timestamp
        assert exif.timestamp is not None

        # Camera info
        assert exif.camera_make == "Apple"
        assert "iPhone" in exif.camera_model

        # GPS - San Jose area, California
        assert exif.latitude is not None
        assert exif.longitude is not None
        assert abs(exif.latitude - 37.276) < 0.01
        assert abs(exif.longitude - (-121.826)) < 0.01
