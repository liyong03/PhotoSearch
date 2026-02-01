"""Tests for location service (geocoding and reverse geocoding)."""

import logging
import time
from pathlib import Path

import pytest

from photosearch.core.location_service import (
    BoundingBox,
    GeocodingResult,
    LocationService,
    PlaceInfo,
)
from photosearch.utils.exif import extract_exif_data

logger = logging.getLogger(__name__)

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestBoundingBox:
    """Tests for BoundingBox dataclass."""

    def test_contains_point_inside(self):
        """Test that contains returns True for point inside bbox."""
        bbox = BoundingBox(min_lat=18.0, max_lat=22.0, min_lon=-160.0, max_lon=-154.0)

        # Point inside Hawaii
        assert bbox.contains(20.0, -157.0) is True

    def test_contains_point_outside(self):
        """Test that contains returns False for point outside bbox."""
        bbox = BoundingBox(min_lat=18.0, max_lat=22.0, min_lon=-160.0, max_lon=-154.0)

        # Point outside (San Francisco)
        assert bbox.contains(37.7749, -122.4194) is False

    def test_contains_point_on_boundary(self):
        """Test that contains returns True for point on boundary."""
        bbox = BoundingBox(min_lat=18.0, max_lat=22.0, min_lon=-160.0, max_lon=-154.0)

        # Points on boundary
        assert bbox.contains(18.0, -157.0) is True  # min_lat edge
        assert bbox.contains(22.0, -157.0) is True  # max_lat edge
        assert bbox.contains(20.0, -160.0) is True  # min_lon edge
        assert bbox.contains(20.0, -154.0) is True  # max_lon edge

    def test_to_dict(self):
        """Test conversion to dictionary."""
        bbox = BoundingBox(min_lat=18.0, max_lat=22.0, min_lon=-160.0, max_lon=-154.0)

        d = bbox.to_dict()

        assert d == {
            "min_lat": 18.0,
            "max_lat": 22.0,
            "min_lon": -160.0,
            "max_lon": -154.0,
        }


class TestPlaceInfo:
    """Tests for PlaceInfo dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        place = PlaceInfo(
            city="San Francisco",
            state="California",
            country="United States",
            place_name="Golden Gate Bridge",
        )

        d = place.to_dict()

        assert d == {
            "city": "San Francisco",
            "state": "California",
            "country": "United States",
            "place_name": "Golden Gate Bridge",
        }

    def test_to_dict_with_none(self):
        """Test conversion with None values."""
        place = PlaceInfo(city="Tokyo", country="Japan")

        d = place.to_dict()

        assert d["city"] == "Tokyo"
        assert d["country"] == "Japan"
        assert d["state"] is None
        assert d["place_name"] is None


class TestGeocode:
    """Tests for geocoding (place name to coordinates)."""

    @pytest.fixture(scope="class")
    def location_service(self):
        """Create location service for tests."""
        return LocationService()

    def test_geocode_hawaii(self, location_service):
        """Test geocoding Hawaii."""
        result = location_service.geocode("Hawaii")

        assert result is not None
        assert isinstance(result, GeocodingResult)
        logger.info(f"Hawaii geocoding result: {result.to_dict()}")

        # Check bounding box is reasonable for Hawaii (includes all islands)
        bbox = result.bounding_box
        assert 18.0 < bbox.min_lat < 20.0
        assert 22.0 < bbox.max_lat < 30.0  # Includes Northwestern Hawaiian Islands
        assert -180.0 < bbox.min_lon < -154.0
        assert -156.0 < bbox.max_lon < -154.0

        # Check center is reasonable (Big Island area)
        assert 19.0 < result.center_lat < 22.0
        assert -160.0 < result.center_lon < -155.0

    def test_geocode_san_francisco(self, location_service):
        """Test geocoding San Francisco."""
        result = location_service.geocode("San Francisco, California")

        assert result is not None
        logger.info(f"San Francisco geocoding result: {result.to_dict()}")

        bbox = result.bounding_box
        # San Francisco approximate bounds (includes Farallon Islands)
        assert 37.5 < bbox.min_lat < 38.0
        assert 37.7 < bbox.max_lat < 38.0
        assert -124.0 < bbox.min_lon < -122.0
        assert -123.0 < bbox.max_lon < -122.0

    def test_geocode_tokyo(self, location_service):
        """Test geocoding Tokyo."""
        result = location_service.geocode("Tokyo, Japan")

        assert result is not None
        logger.info(f"Tokyo geocoding result: {result.to_dict()}")

        # Tokyo should be around 35.6N, 139.7E
        assert 35.0 < result.center_lat < 36.0
        assert 139.0 < result.center_lon < 140.0

    def test_geocode_unknown_location(self, location_service):
        """Test geocoding unknown location returns None."""
        result = location_service.geocode("NonexistentPlace12345XYZ")

        assert result is None

    def test_geocode_empty_string(self, location_service):
        """Test geocoding empty string."""
        result = location_service.geocode("")

        # Empty string should return None or handle gracefully
        # (Nominatim behavior may vary)
        assert result is None or isinstance(result, GeocodingResult)

    def test_get_bounding_box(self, location_service):
        """Test getting just the bounding box."""
        bbox = location_service.get_bounding_box("Paris, France")

        assert bbox is not None
        assert isinstance(bbox, BoundingBox)
        logger.info(f"Paris bounding box: {bbox.to_dict()}")

        # Paris should be around 48.8N, 2.3E
        assert 48.0 < bbox.min_lat < 49.0
        assert 2.0 < bbox.min_lon < 3.0


class TestReverseGeocode:
    """Tests for reverse geocoding (coordinates to place name)."""

    @pytest.fixture(scope="class")
    def location_service(self):
        """Create location service for tests."""
        return LocationService()

    def test_reverse_geocode_san_francisco(self, location_service):
        """Test reverse geocoding San Francisco coordinates."""
        # San Francisco coordinates
        result = location_service.reverse_geocode(37.7749, -122.4194)

        assert result is not None
        assert isinstance(result, PlaceInfo)
        logger.info(f"Reverse geocode (37.7749, -122.4194): {result.to_dict()}")

        # Should return San Francisco or California
        assert result.country is not None
        assert "United States" in result.country or "USA" in result.country

    def test_reverse_geocode_tokyo(self, location_service):
        """Test reverse geocoding Tokyo coordinates."""
        # Tokyo coordinates
        result = location_service.reverse_geocode(35.6762, 139.6503)

        assert result is not None
        logger.info(f"Reverse geocode Tokyo: {result.to_dict()}")

        assert result.country is not None
        # Nominatim may return country in local language (日本 = Japan)
        assert "Japan" in result.country or "日本" in result.country

    def test_reverse_geocode_ocean(self, location_service):
        """Test reverse geocoding coordinates in the ocean."""
        # Middle of Pacific Ocean
        result = location_service.reverse_geocode(0.0, -160.0)

        # Should return None or minimal info (no city/country)
        # Nominatim may return some info or None
        if result is not None:
            logger.info(f"Reverse geocode ocean: {result.to_dict()}")


class TestCache:
    """Tests for caching behavior."""

    def test_geocode_cache_hit(self):
        """Test that repeated geocode calls use cache."""
        service = LocationService()

        # First call - cache miss
        result1 = service.geocode("London, UK")
        info1 = service.cache_info()
        assert info1["geocode"]["misses"] == 1

        # Second call - cache hit
        result2 = service.geocode("London, UK")
        info2 = service.cache_info()
        assert info2["geocode"]["hits"] == 1
        assert info2["geocode"]["misses"] == 1

        # Results should be equal
        assert result1.center_lat == result2.center_lat
        assert result1.center_lon == result2.center_lon

    def test_reverse_geocode_cache_hit(self):
        """Test that repeated reverse geocode calls use cache."""
        service = LocationService()

        # First call - cache miss
        result1 = service.reverse_geocode(51.5074, -0.1278)  # London
        info1 = service.cache_info()
        assert info1["reverse_geocode"]["misses"] == 1

        # Second call with same coordinates - cache hit
        result2 = service.reverse_geocode(51.5074, -0.1278)
        info2 = service.cache_info()
        assert info2["reverse_geocode"]["hits"] == 1

    def test_reverse_geocode_coordinate_rounding(self):
        """Test that nearby coordinates hit same cache entry."""
        service = LocationService()

        # First call
        result1 = service.reverse_geocode(51.50741, -0.12781)
        info1 = service.cache_info()

        # Second call with very slightly different coordinates
        # Should hit cache due to rounding to 4 decimal places
        result2 = service.reverse_geocode(51.50742, -0.12782)
        info2 = service.cache_info()

        assert info2["reverse_geocode"]["hits"] == info1["reverse_geocode"]["hits"] + 1

    def test_clear_cache(self):
        """Test clearing the cache."""
        service = LocationService()

        # Make some requests
        service.geocode("Berlin, Germany")
        service.reverse_geocode(52.52, 13.405)

        # Clear cache
        service.clear_cache()
        info = service.cache_info()

        assert info["geocode"]["size"] == 0
        assert info["reverse_geocode"]["size"] == 0

    def test_cache_info(self):
        """Test cache info structure."""
        service = LocationService()

        info = service.cache_info()

        assert "geocode" in info
        assert "reverse_geocode" in info
        assert "hits" in info["geocode"]
        assert "misses" in info["geocode"]
        assert "size" in info["geocode"]
        assert "maxsize" in info["geocode"]


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    def test_rate_limiting_enforced(self):
        """Test that rate limiting delays requests appropriately."""
        service = LocationService()

        # Make two requests and measure time
        start = time.time()
        service.geocode("Rome, Italy")
        service.geocode("Madrid, Spain")
        elapsed = time.time() - start

        # Should take at least 1 second due to rate limiting
        assert elapsed >= 1.0, f"Rate limiting not enforced: {elapsed:.2f}s for 2 requests"

    def test_multiple_requests_dont_exceed_rate(self):
        """Test that multiple requests don't exceed 1/sec rate."""
        service = LocationService()

        # Make 3 requests
        start = time.time()
        service.geocode("Sydney, Australia")
        service.geocode("Melbourne, Australia")
        service.geocode("Brisbane, Australia")
        elapsed = time.time() - start

        # Should take at least 2 seconds (3 requests, 1/sec max)
        assert elapsed >= 2.0, f"Rate limit exceeded: {elapsed:.2f}s for 3 requests"


class TestBoundingBoxContains:
    """Tests for bounding box containment checks."""

    @pytest.fixture(scope="class")
    def location_service(self):
        """Create location service for tests."""
        return LocationService()

    def test_hawaii_bbox_contains_honolulu(self, location_service):
        """Test that Hawaii bbox contains Honolulu coordinates."""
        hawaii_result = location_service.geocode("Hawaii")
        assert hawaii_result is not None

        # Honolulu coordinates
        honolulu_lat = 21.3069
        honolulu_lon = -157.8583

        assert hawaii_result.bounding_box.contains(honolulu_lat, honolulu_lon), (
            f"Hawaii bbox should contain Honolulu ({honolulu_lat}, {honolulu_lon})"
        )

    def test_california_bbox_contains_la(self, location_service):
        """Test that California bbox contains Los Angeles."""
        ca_result = location_service.geocode("California, USA")
        assert ca_result is not None

        # Los Angeles coordinates
        la_lat = 34.0522
        la_lon = -118.2437

        assert ca_result.bounding_box.contains(la_lat, la_lon), (
            f"California bbox should contain Los Angeles ({la_lat}, {la_lon})"
        )

    def test_bbox_excludes_distant_point(self, location_service):
        """Test that bbox correctly excludes distant points."""
        hawaii_result = location_service.geocode("Hawaii")
        assert hawaii_result is not None

        # New York coordinates (should not be in Hawaii bbox)
        ny_lat = 40.7128
        ny_lon = -74.0060

        assert not hawaii_result.bounding_box.contains(ny_lat, ny_lon), (
            "Hawaii bbox should not contain New York"
        )


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture(scope="class")
    def location_service(self):
        """Create location service for tests."""
        return LocationService()

    def test_geocode_with_special_characters(self, location_service):
        """Test geocoding place names with special characters."""
        # Place with accents
        result = location_service.geocode("Zürich, Switzerland")

        # Should handle gracefully (may or may not find result)
        if result is not None:
            assert isinstance(result, GeocodingResult)
            logger.info(f"Zürich result: {result.to_dict()}")

    def test_geocode_case_insensitive(self, location_service):
        """Test that geocoding is case insensitive."""
        result1 = location_service.geocode("NEW YORK")
        result2 = location_service.geocode("new york")

        # Both should work (cache key is lowercased)
        if result1 is not None and result2 is not None:
            # Should be same result (from cache)
            assert result1.center_lat == result2.center_lat

    def test_reverse_geocode_extreme_coordinates(self, location_service):
        """Test reverse geocoding at extreme coordinates."""
        # North Pole
        result = location_service.reverse_geocode(90.0, 0.0)
        # May return None or some info, should not crash
        if result is not None:
            logger.info(f"North Pole result: {result.to_dict()}")

    def test_geocoding_result_to_dict(self, location_service):
        """Test GeocodingResult to_dict method."""
        result = location_service.geocode("Boston, Massachusetts")
        assert result is not None

        d = result.to_dict()

        assert "name" in d
        assert "bounding_box" in d
        assert "center" in d
        assert "lat" in d["center"]
        assert "lon" in d["center"]
        assert "min_lat" in d["bounding_box"]


class TestRealPhotoIntegration:
    """Integration tests using real photos with GPS data."""

    @pytest.fixture(scope="class")
    def location_service(self):
        """Create location service for tests."""
        return LocationService()

    def test_reverse_geocode_real_iphone_photo(self, location_service):
        """Test reverse geocoding GPS coordinates from real iPhone photo."""
        image_path = FIXTURES_DIR / "real_iphone.jpg"
        if not image_path.exists():
            pytest.skip("real_iphone.jpg not available")

        # Extract GPS from EXIF
        exif_data = extract_exif_data(image_path)
        logger.info(f"real_iphone.jpg EXIF: lat={exif_data.latitude}, lon={exif_data.longitude}")

        if exif_data.latitude is None or exif_data.longitude is None:
            pytest.skip("real_iphone.jpg has no GPS data")

        # Reverse geocode
        result = location_service.reverse_geocode(exif_data.latitude, exif_data.longitude)

        assert result is not None
        logger.info(f"real_iphone.jpg location: {result.to_dict()}")

        # Should have at least country
        assert result.country is not None or result.city is not None or result.state is not None

    def test_reverse_geocode_real_heic_photo(self, location_service):
        """Test reverse geocoding GPS coordinates from real HEIC photo."""
        image_path = FIXTURES_DIR / "real_heic.heic"
        if not image_path.exists():
            pytest.skip("real_heic.heic not available")

        # Extract GPS from EXIF
        exif_data = extract_exif_data(image_path)
        logger.info(f"real_heic.heic EXIF: lat={exif_data.latitude}, lon={exif_data.longitude}")

        if exif_data.latitude is None or exif_data.longitude is None:
            pytest.skip("real_heic.heic has no GPS data")

        # Reverse geocode
        result = location_service.reverse_geocode(exif_data.latitude, exif_data.longitude)

        assert result is not None
        logger.info(f"real_heic.heic location: {result.to_dict()}")

        # Should have at least country
        assert result.country is not None or result.city is not None or result.state is not None

    def test_photo_location_in_geocoded_bbox(self, location_service):
        """Test that photo GPS coordinates fall within geocoded location bbox."""
        image_path = FIXTURES_DIR / "real_iphone.jpg"
        if not image_path.exists():
            pytest.skip("real_iphone.jpg not available")

        # Extract GPS from EXIF
        exif_data = extract_exif_data(image_path)
        if exif_data.latitude is None or exif_data.longitude is None:
            pytest.skip("real_iphone.jpg has no GPS data")

        # Reverse geocode to get location name
        place_info = location_service.reverse_geocode(exif_data.latitude, exif_data.longitude)
        if place_info is None:
            pytest.skip("Could not reverse geocode photo location")

        # Try to geocode the country or state to get a bounding box
        search_location = place_info.country or place_info.state or place_info.city
        if search_location is None:
            pytest.skip("No location name available")

        geocode_result = location_service.geocode(search_location)
        if geocode_result is None:
            pytest.skip(f"Could not geocode {search_location}")

        # Photo coordinates should be within the geocoded bounding box
        logger.info(f"Photo at ({exif_data.latitude}, {exif_data.longitude})")
        logger.info(f"Location '{search_location}' bbox: {geocode_result.bounding_box.to_dict()}")

        assert geocode_result.bounding_box.contains(exif_data.latitude, exif_data.longitude), (
            f"Photo location ({exif_data.latitude}, {exif_data.longitude}) "
            f"should be within {search_location} bounding box"
        )
