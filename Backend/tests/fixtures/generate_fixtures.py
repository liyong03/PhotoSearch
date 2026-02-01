#!/usr/bin/env python3
"""Generate test fixture images with EXIF data."""

from datetime import datetime
from io import BytesIO
from pathlib import Path

import piexif
from PIL import Image


FIXTURES_DIR = Path(__file__).parent


def create_gradient_image(width: int = 200, height: int = 150, color1: tuple = (255, 100, 50), color2: tuple = (50, 100, 255)) -> Image.Image:
    """Create a gradient test image."""
    img = Image.new("RGB", (width, height))
    for y in range(height):
        for x in range(width):
            r = int(color1[0] + (color2[0] - color1[0]) * x / width)
            g = int(color1[1] + (color2[1] - color1[1]) * y / height)
            b = int(color1[2] + (color2[2] - color1[2]) * (x + y) / (width + height))
            img.putpixel((x, y), (r, g, b))
    return img


def to_gps_dms(decimal_degrees: float) -> tuple:
    """Convert decimal degrees to EXIF GPS format (degrees, minutes, seconds as rationals)."""
    is_negative = decimal_degrees < 0
    decimal_degrees = abs(decimal_degrees)
    degrees = int(decimal_degrees)
    minutes_float = (decimal_degrees - degrees) * 60
    minutes = int(minutes_float)
    seconds_float = (minutes_float - minutes) * 60
    # Use rational representation (numerator, denominator)
    return (
        ((degrees, 1), (minutes, 1), (int(seconds_float * 1000), 1000)),
        is_negative
    )


def create_exif_bytes(
    timestamp: datetime | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    camera_make: str = "TestCamera",
    camera_model: str = "TestModel 1000",
) -> bytes:
    """Create EXIF bytes for embedding in JPEG."""
    exif_dict = {
        "0th": {},
        "Exif": {},
        "GPS": {},
        "1st": {},
        "thumbnail": None,
    }

    # Camera info
    exif_dict["0th"][piexif.ImageIFD.Make] = camera_make
    exif_dict["0th"][piexif.ImageIFD.Model] = camera_model
    exif_dict["0th"][piexif.ImageIFD.Software] = "PhotoSearch Test Generator"

    # Timestamp
    if timestamp:
        dt_str = timestamp.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str
        exif_dict["0th"][piexif.ImageIFD.DateTime] = dt_str

    # GPS
    if latitude is not None and longitude is not None:
        lat_dms, lat_south = to_gps_dms(latitude)
        lon_dms, lon_west = to_gps_dms(longitude)

        exif_dict["GPS"][piexif.GPSIFD.GPSVersionID] = (2, 3, 0, 0)
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_dms
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = "S" if lat_south else "N"
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon_dms
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = "W" if lon_west else "E"

    return piexif.dump(exif_dict)


def save_jpeg_with_exif(img: Image.Image, path: Path, exif_bytes: bytes) -> None:
    """Save image as JPEG with EXIF data."""
    img.save(path, format="JPEG", quality=85, exif=exif_bytes)
    print(f"  Created: {path.name}")


def generate_all_fixtures():
    """Generate all test fixture images."""
    print("Generating test fixtures...")

    # 1. Full EXIF - Hawaii sunset
    img = create_gradient_image(color1=(255, 150, 50), color2=(100, 50, 150))
    exif = create_exif_bytes(
        timestamp=datetime(2024, 6, 15, 18, 30, 0),
        latitude=21.2769,  # Waikiki Beach
        longitude=-157.8268,
        camera_make="Apple",
        camera_model="iPhone 15 Pro",
    )
    save_jpeg_with_exif(img, FIXTURES_DIR / "hawaii_sunset.jpg", exif)

    # 2. Full EXIF - Paris
    img = create_gradient_image(color1=(200, 200, 220), color2=(100, 120, 180))
    exif = create_exif_bytes(
        timestamp=datetime(2023, 4, 10, 14, 0, 0),
        latitude=48.8584,  # Eiffel Tower
        longitude=2.2945,
        camera_make="Canon",
        camera_model="EOS R5",
    )
    save_jpeg_with_exif(img, FIXTURES_DIR / "paris_tower.jpg", exif)

    # 3. Timestamp only (no GPS)
    img = create_gradient_image(color1=(100, 200, 100), color2=(50, 100, 50))
    exif = create_exif_bytes(
        timestamp=datetime(2022, 12, 25, 10, 30, 0),
        camera_make="Sony",
        camera_model="A7 IV",
    )
    save_jpeg_with_exif(img, FIXTURES_DIR / "christmas_morning.jpg", exif)

    # 4. GPS only (no timestamp)
    img = create_gradient_image(color1=(50, 150, 255), color2=(20, 80, 150))
    exif = create_exif_bytes(
        latitude=35.6762,  # Tokyo
        longitude=139.6503,
        camera_make="Nikon",
        camera_model="Z8",
    )
    save_jpeg_with_exif(img, FIXTURES_DIR / "tokyo_street.jpg", exif)

    # 5. Southern hemisphere (negative latitude)
    img = create_gradient_image(color1=(255, 200, 100), color2=(200, 150, 50))
    exif = create_exif_bytes(
        timestamp=datetime(2024, 1, 15, 9, 0, 0),
        latitude=-33.8688,  # Sydney Opera House
        longitude=151.2093,
        camera_make="Fujifilm",
        camera_model="X-T5",
    )
    save_jpeg_with_exif(img, FIXTURES_DIR / "sydney_opera.jpg", exif)

    # 6. No EXIF (PNG)
    img = create_gradient_image(color1=(128, 128, 128), color2=(64, 64, 64))
    path = FIXTURES_DIR / "no_exif.png"
    img.save(path, format="PNG")
    print(f"  Created: {path.name}")

    # 7. Minimal EXIF
    img = create_gradient_image(color1=(200, 100, 100), color2=(100, 50, 50))
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    exif_bytes = piexif.dump(exif_dict)
    save_jpeg_with_exif(img, FIXTURES_DIR / "minimal_exif.jpg", exif_bytes)

    print("\nDone! Generated 7 test fixtures.")


if __name__ == "__main__":
    generate_all_fixtures()
