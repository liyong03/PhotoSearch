"""Location service for geocoding and reverse geocoding using Nominatim."""

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """Geographic bounding box."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        """Check if a point is within the bounding box.

        Args:
            lat: Latitude of the point.
            lon: Longitude of the point.

        Returns:
            True if the point is within the bounding box.
        """
        return (
            self.min_lat <= lat <= self.max_lat
            and self.min_lon <= lon <= self.max_lon
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "min_lat": self.min_lat,
            "max_lat": self.max_lat,
            "min_lon": self.min_lon,
            "max_lon": self.max_lon,
        }


@dataclass
class PlaceInfo:
    """Information about a geographic place."""

    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    place_name: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "place_name": self.place_name,
        }


@dataclass
class GeocodingResult:
    """Result of geocoding a place name."""

    name: str
    bounding_box: BoundingBox
    center_lat: float
    center_lon: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "bounding_box": self.bounding_box.to_dict(),
            "center": {
                "lat": self.center_lat,
                "lon": self.center_lon,
            },
        }


class LocationService:
    """Service for geocoding and reverse geocoding using Nominatim (OpenStreetMap).

    Implements caching and rate limiting to respect Nominatim usage policy.
    """

    # Nominatim requires max 1 request per second
    MIN_REQUEST_INTERVAL = 1.0

    def __init__(
        self,
        user_agent: str = "photosearch",
        cache_size: int = 1000,
        timeout: int = 10,
    ):
        """Initialize location service.

        Args:
            user_agent: User agent string for Nominatim requests.
            cache_size: Maximum number of geocoding results to cache.
            timeout: Request timeout in seconds.
        """
        self.geolocator = Nominatim(user_agent=user_agent, timeout=timeout)
        self.cache_size = cache_size
        self._last_request_time: float = 0

        # Create cached versions of methods
        self._geocode_cached = lru_cache(maxsize=cache_size)(self._geocode_impl)
        self._reverse_geocode_cached = lru_cache(maxsize=cache_size)(
            self._reverse_geocode_impl
        )

        logger.info(f"LocationService initialized with cache size {cache_size}")

    def _rate_limit(self) -> None:
        """Enforce rate limiting for Nominatim API."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            sleep_time = self.MIN_REQUEST_INTERVAL - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _geocode_impl(self, place_name: str) -> Optional[tuple]:
        """Internal implementation of geocoding (for caching).

        Returns tuple instead of dataclass for lru_cache compatibility.
        """
        self._rate_limit()

        try:
            location = self.geolocator.geocode(
                place_name,
                exactly_one=True,
                addressdetails=True,
            )

            if location is None:
                logger.debug(f"No results for place name: {place_name}")
                return None

            raw = location.raw
            if "boundingbox" not in raw:
                logger.debug(f"No bounding box for: {place_name}")
                return None

            bb = raw["boundingbox"]
            # Nominatim returns [min_lat, max_lat, min_lon, max_lon]
            return (
                place_name,
                float(bb[0]),  # min_lat
                float(bb[1]),  # max_lat
                float(bb[2]),  # min_lon
                float(bb[3]),  # max_lon
                location.latitude,
                location.longitude,
            )

        except GeocoderTimedOut:
            logger.warning(f"Geocoding timed out for: {place_name}")
            return None
        except GeocoderServiceError as e:
            logger.warning(f"Geocoding service error for {place_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error geocoding {place_name}: {e}")
            return None

    def geocode(self, place_name: str) -> Optional[GeocodingResult]:
        """Convert place name to bounding box and center coordinates.

        Args:
            place_name: Name of the place (e.g., "Hawaii", "San Francisco").

        Returns:
            GeocodingResult with bounding box and center, or None if not found.
        """
        result = self._geocode_cached(place_name.strip().lower())
        if result is None:
            return None

        _, min_lat, max_lat, min_lon, max_lon, center_lat, center_lon = result
        return GeocodingResult(
            name=place_name,
            bounding_box=BoundingBox(
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
            ),
            center_lat=center_lat,
            center_lon=center_lon,
        )

    def _reverse_geocode_impl(self, lat: float, lon: float) -> Optional[tuple]:
        """Internal implementation of reverse geocoding (for caching).

        Returns tuple instead of dataclass for lru_cache compatibility.
        Rounds coordinates to reduce cache misses for nearby points.
        """
        self._rate_limit()

        try:
            location = self.geolocator.reverse(
                f"{lat}, {lon}",
                exactly_one=True,
                addressdetails=True,
            )

            if location is None:
                logger.debug(f"No results for coordinates: ({lat}, {lon})")
                return None

            addr = location.raw.get("address", {})

            # Extract city (try multiple fields)
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
            )

            # Extract state/province
            state = addr.get("state") or addr.get("province") or addr.get("region")

            # Extract country
            country = addr.get("country")

            # Extract notable place name
            place_name = (
                addr.get("tourism")
                or addr.get("amenity")
                or addr.get("building")
                or addr.get("historic")
                or addr.get("natural")
            )

            return (city, state, country, place_name)

        except GeocoderTimedOut:
            logger.warning(f"Reverse geocoding timed out for: ({lat}, {lon})")
            return None
        except GeocoderServiceError as e:
            logger.warning(f"Reverse geocoding service error for ({lat}, {lon}): {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reverse geocoding ({lat}, {lon}): {e}")
            return None

    def reverse_geocode(self, lat: float, lon: float) -> Optional[PlaceInfo]:
        """Convert GPS coordinates to place information.

        Args:
            lat: Latitude.
            lon: Longitude.

        Returns:
            PlaceInfo with city, state, country, or None if not found.
        """
        # Round coordinates to 4 decimal places (~11m precision)
        # This improves cache hit rate for nearby coordinates
        rounded_lat = round(lat, 4)
        rounded_lon = round(lon, 4)

        result = self._reverse_geocode_cached(rounded_lat, rounded_lon)
        if result is None:
            return None

        city, state, country, place_name = result
        return PlaceInfo(
            city=city,
            state=state,
            country=country,
            place_name=place_name,
        )

    def get_bounding_box(self, place_name: str) -> Optional[BoundingBox]:
        """Get just the bounding box for a place name.

        Args:
            place_name: Name of the place.

        Returns:
            BoundingBox or None if not found.
        """
        result = self.geocode(place_name)
        if result is None:
            return None
        return result.bounding_box

    def clear_cache(self) -> None:
        """Clear all cached geocoding results."""
        self._geocode_cached.cache_clear()
        self._reverse_geocode_cached.cache_clear()
        logger.info("Location cache cleared")

    def cache_info(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache hit/miss statistics.
        """
        geocode_info = self._geocode_cached.cache_info()
        reverse_info = self._reverse_geocode_cached.cache_info()
        return {
            "geocode": {
                "hits": geocode_info.hits,
                "misses": geocode_info.misses,
                "size": geocode_info.currsize,
                "maxsize": geocode_info.maxsize,
            },
            "reverse_geocode": {
                "hits": reverse_info.hits,
                "misses": reverse_info.misses,
                "size": reverse_info.currsize,
                "maxsize": reverse_info.maxsize,
            },
        }
