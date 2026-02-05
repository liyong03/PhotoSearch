"""EXIF data extraction utilities."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

logger = logging.getLogger(__name__)

# Register HEIF/HEIC support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    logger.debug("HEIF/HEIC support enabled")
except ImportError:
    logger.debug("pillow-heif not installed, HEIC support disabled")


@dataclass
class ExifData:
    """Extracted EXIF data from a photo."""

    timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


def _convert_to_degrees(value: tuple) -> float:
    """Convert GPS coordinates from degrees/minutes/seconds to decimal degrees.

    Args:
        value: Tuple of (degrees, minutes, seconds) as IFDRational or float.

    Returns:
        Decimal degrees as float.
    """
    try:
        # Handle IFDRational or tuple format
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, IndexError, ValueError) as e:
        logger.warning(f"Failed to convert GPS value {value}: {e}")
        return 0.0


def _get_gps_coords(gps_info: dict) -> tuple[Optional[float], Optional[float]]:
    """Extract latitude and longitude from GPS info dict.

    Args:
        gps_info: Dictionary of GPS EXIF tags.

    Returns:
        Tuple of (latitude, longitude) or (None, None) if not available.
    """
    try:
        # GPS tag IDs
        GPS_LATITUDE = 2
        GPS_LATITUDE_REF = 1
        GPS_LONGITUDE = 4
        GPS_LONGITUDE_REF = 3

        if GPS_LATITUDE not in gps_info or GPS_LONGITUDE not in gps_info:
            return None, None

        lat = _convert_to_degrees(gps_info[GPS_LATITUDE])
        lon = _convert_to_degrees(gps_info[GPS_LONGITUDE])

        # Apply direction reference
        if gps_info.get(GPS_LATITUDE_REF, "N") == "S":
            lat = -lat
        if gps_info.get(GPS_LONGITUDE_REF, "E") == "W":
            lon = -lon

        return lat, lon

    except Exception as e:
        logger.warning(f"Failed to extract GPS coordinates: {e}")
        return None, None


def _parse_exif_datetime(dt_str: str) -> Optional[datetime]:
    """Parse EXIF datetime string to datetime object.

    Args:
        dt_str: EXIF datetime string (format: "YYYY:MM:DD HH:MM:SS").

    Returns:
        datetime object or None if parsing fails.
    """
    if not dt_str:
        return None

    # EXIF datetime format
    formats = [
        "%Y:%m:%d %H:%M:%S",  # Standard EXIF format
        "%Y-%m-%d %H:%M:%S",  # Alternative format
        "%Y:%m:%d",  # Date only
        "%Y-%m-%d",  # Date only alternative
    ]

    for fmt in formats:
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue

    logger.warning(f"Failed to parse EXIF datetime: {dt_str}")
    return None


def extract_exif_data(image_path: Path | str) -> ExifData:
    """Extract EXIF metadata from an image file.

    Supports JPEG, PNG, HEIC, and other formats supported by Pillow.

    Args:
        image_path: Path to the image file.

    Returns:
        ExifData with extracted metadata. Fields will be None if not available.
    """
    image_path = Path(image_path)
    exif_data = ExifData()

    if not image_path.exists():
        logger.warning(f"Image file not found: {image_path}")
        return exif_data

    try:
        with Image.open(image_path) as img:
            # Get image dimensions
            exif_data.width = img.width
            exif_data.height = img.height

            # Try to get EXIF data
            exif = img.getexif()
            if not exif:
                logger.debug(f"No EXIF data found in {image_path}")
                return exif_data

            # Extract standard EXIF tags
            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)

                if tag_name == "DateTimeOriginal":
                    exif_data.timestamp = _parse_exif_datetime(str(value))
                elif tag_name == "DateTime" and exif_data.timestamp is None:
                    # Fallback to DateTime if DateTimeOriginal not available
                    exif_data.timestamp = _parse_exif_datetime(str(value))
                elif tag_name == "Make":
                    exif_data.camera_make = str(value).strip()
                elif tag_name == "Model":
                    exif_data.camera_model = str(value).strip()

            # Extract GPS data (stored in IFD)
            gps_ifd = exif.get_ifd(0x8825)  # GPSInfo IFD
            if gps_ifd:
                lat, lon = _get_gps_coords(gps_ifd)
                exif_data.latitude = lat
                exif_data.longitude = lon

    except Exception as e:
        logger.warning(f"Failed to extract EXIF from {image_path}: {e}")

    return exif_data


def get_file_timestamp(image_path: Path | str) -> Optional[datetime]:
    """Get timestamp from file modification time as fallback.

    Args:
        image_path: Path to the image file.

    Returns:
        datetime from file modification time, or None if file doesn't exist.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        return None

    try:
        mtime = image_path.stat().st_mtime
        return datetime.fromtimestamp(mtime)
    except Exception as e:
        logger.warning(f"Failed to get file timestamp for {image_path}: {e}")
        return None


def extract_metadata(image_path: Path | str) -> ExifData:
    """Extract metadata from image, with fallbacks for missing data.

    This is the main entry point for metadata extraction. It tries EXIF first,
    then falls back to file metadata.

    Args:
        image_path: Path to the image file.

    Returns:
        ExifData with best available metadata.
    """
    exif_data = extract_exif_data(image_path)

    # Fallback to file modification time if no EXIF timestamp
    if exif_data.timestamp is None:
        exif_data.timestamp = get_file_timestamp(image_path)

    return exif_data
