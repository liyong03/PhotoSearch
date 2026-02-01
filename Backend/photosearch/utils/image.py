"""Image loading and processing utilities."""

import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Register HEIF/HEIC support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass  # HEIC support will be limited

# Supported image extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tiff"}


def is_supported_image(file_path: Path | str) -> bool:
    """Check if a file is a supported image format.

    Args:
        file_path: Path to the file.

    Returns:
        True if the file extension is supported.
    """
    path = Path(file_path)
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def load_image(image_path: Path | str) -> Optional[Image.Image]:
    """Load an image file using Pillow.

    Handles HEIC conversion if pillow-heif is installed.

    Args:
        image_path: Path to the image file.

    Returns:
        PIL Image object, or None if loading fails.
    """
    image_path = Path(image_path)

    if not image_path.exists():
        logger.warning(f"Image file not found: {image_path}")
        return None

    try:
        img = Image.open(image_path)

        # Convert to RGB if necessary (for consistency)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        return img

    except Exception as e:
        logger.warning(f"Failed to load image {image_path}: {e}")
        return None


def get_image_dimensions(image_path: Path | str) -> Optional[tuple[int, int]]:
    """Get image dimensions without fully loading the image.

    Args:
        image_path: Path to the image file.

    Returns:
        Tuple of (width, height), or None if unable to determine.
    """
    image_path = Path(image_path)

    if not image_path.exists():
        return None

    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logger.warning(f"Failed to get dimensions for {image_path}: {e}")
        return None


def prepare_image_for_model(
    image: Image.Image,
    target_size: tuple[int, int] = (224, 224),
) -> Image.Image:
    """Prepare an image for ML model input.

    Resizes and ensures RGB format.

    Args:
        image: PIL Image to prepare.
        target_size: Target size as (width, height).

    Returns:
        Prepared PIL Image.
    """
    # Ensure RGB
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Resize maintaining aspect ratio, then center crop
    image.thumbnail((max(target_size), max(target_size)), Image.Resampling.LANCZOS)

    # If needed, pad or crop to exact size
    if image.size != target_size:
        # Create new image with target size
        new_image = Image.new("RGB", target_size, (128, 128, 128))
        # Paste original centered
        x = (target_size[0] - image.width) // 2
        y = (target_size[1] - image.height) // 2
        new_image.paste(image, (x, y))
        image = new_image

    return image


def scan_folder_for_images(
    folder_path: Path | str,
    recursive: bool = True,
) -> list[Path]:
    """Scan a folder for supported image files.

    Args:
        folder_path: Path to the folder to scan.
        recursive: Whether to scan subdirectories.

    Returns:
        List of paths to image files.
    """
    folder_path = Path(folder_path)

    if not folder_path.exists():
        logger.warning(f"Folder not found: {folder_path}")
        return []

    if not folder_path.is_dir():
        logger.warning(f"Not a directory: {folder_path}")
        return []

    images = []
    pattern = "**/*" if recursive else "*"

    for file_path in folder_path.glob(pattern):
        if file_path.is_file() and is_supported_image(file_path):
            images.append(file_path)

    # Sort by name for consistent ordering
    images.sort()

    logger.info(f"Found {len(images)} images in {folder_path}")
    return images
