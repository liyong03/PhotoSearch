"""BLIP model for generating image captions and extracting tags."""

import logging
import re
from pathlib import Path
from typing import Optional

import torch
from PIL import Image
from transformers import BlipForConditionalGeneration, BlipProcessor

from photosearch.utils.image import load_image

logger = logging.getLogger(__name__)


# Common words to exclude from tags
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "there", "here", "where", "when", "why", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "also", "now", "then", "once", "if", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "while", "this", "that", "these", "those", "it", "its",
    "what", "which", "who", "whom", "whose", "image", "photo", "picture",
    "showing", "shows", "seen", "see", "look", "looking", "looks",
}


class CaptionGenerator:
    """BLIP model wrapper for generating image captions and extracting tags."""

    def __init__(
        self,
        model_name: str = "Salesforce/blip-image-captioning-base",
        device: Optional[str] = None,
    ):
        """Initialize caption generator.

        Args:
            model_name: HuggingFace model name for BLIP.
            device: Device to run model on ("cpu", "cuda", "mps").
                   If None, automatically selects best available device.
        """
        self.model_name = model_name
        self.device = self._select_device(device)

        logger.info(f"Loading BLIP model: {model_name}")
        logger.info(f"Using device: {self.device}")

        self.processor = BlipProcessor.from_pretrained(model_name)
        self.model = BlipForConditionalGeneration.from_pretrained(model_name)

        # Move model to device
        self.model = self.model.to(self.device)
        self.model.eval()

        logger.info("BLIP model loaded successfully")

    def _select_device(self, device: Optional[str]) -> str:
        """Select the best available device.

        Args:
            device: Requested device or None for auto-selection.

        Returns:
            Device string ("cpu", "cuda", or "mps").
        """
        if device is not None:
            return device

        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"

    def generate_caption(
        self,
        image: Image.Image,
        max_length: int = 50,
        num_beams: int = 4,
    ) -> str:
        """Generate a caption for an image.

        Args:
            image: PIL Image to caption.
            max_length: Maximum length of generated caption.
            num_beams: Number of beams for beam search.

        Returns:
            Generated caption string.
        """
        # Ensure RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Process image
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Generate caption
        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_length=max_length,
                num_beams=num_beams,
            )

        # Decode caption
        caption = self.processor.decode(output_ids[0], skip_special_tokens=True)

        return caption.strip()

    def generate_caption_from_path(
        self,
        image_path: Path | str,
        max_length: int = 50,
        num_beams: int = 4,
    ) -> Optional[str]:
        """Generate a caption for an image file.

        Args:
            image_path: Path to the image file.
            max_length: Maximum length of generated caption.
            num_beams: Number of beams for beam search.

        Returns:
            Generated caption, or None if image cannot be loaded.
        """
        try:
            image = load_image(image_path)
            if image is None:
                return None
            return self.generate_caption(image, max_length, num_beams)
        except Exception as e:
            logger.warning(f"Failed to generate caption for {image_path}: {e}")
            return None

    def generate_captions_batch(
        self,
        images: list[Image.Image],
        max_length: int = 50,
        num_beams: int = 4,
    ) -> list[str]:
        """Generate captions for multiple images.

        Args:
            images: List of PIL Images to caption.
            max_length: Maximum length of generated captions.
            num_beams: Number of beams for beam search.

        Returns:
            List of generated caption strings.
        """
        captions = []

        # Process images one at a time to avoid memory issues
        # BLIP doesn't batch as efficiently as CLIP
        for image in images:
            caption = self.generate_caption(image, max_length, num_beams)
            captions.append(caption)

        return captions

    def extract_tags(self, caption: str, max_tags: int = 10) -> list[str]:
        """Extract relevant tags from a caption.

        Uses simple NLP heuristics to extract meaningful nouns and adjectives.

        Args:
            caption: Caption text to extract tags from.
            max_tags: Maximum number of tags to return.

        Returns:
            List of extracted tags (lowercase, deduplicated).
        """
        if not caption:
            return []

        # Lowercase and clean
        text = caption.lower().strip()

        # Remove punctuation except hyphens within words
        text = re.sub(r"[^\w\s-]", " ", text)

        # Split into words
        words = text.split()

        # Filter words
        tags = []
        seen = set()

        for word in words:
            # Skip short words
            if len(word) < 3:
                continue

            # Skip stop words
            if word in STOP_WORDS:
                continue

            # Skip numbers
            if word.isdigit():
                continue

            # Skip if already seen
            if word in seen:
                continue

            seen.add(word)
            tags.append(word)

            if len(tags) >= max_tags:
                break

        return tags

    def generate_caption_with_tags(
        self,
        image: Image.Image,
        max_length: int = 50,
        num_beams: int = 4,
        max_tags: int = 10,
    ) -> tuple[str, list[str]]:
        """Generate caption and extract tags in one call.

        Args:
            image: PIL Image to process.
            max_length: Maximum length of generated caption.
            num_beams: Number of beams for beam search.
            max_tags: Maximum number of tags to extract.

        Returns:
            Tuple of (caption, tags).
        """
        caption = self.generate_caption(image, max_length, num_beams)
        tags = self.extract_tags(caption, max_tags)
        return caption, tags

    def generate_caption_with_tags_from_path(
        self,
        image_path: Path | str,
        max_length: int = 50,
        num_beams: int = 4,
        max_tags: int = 10,
    ) -> Optional[tuple[str, list[str]]]:
        """Generate caption and extract tags for an image file.

        Args:
            image_path: Path to the image file.
            max_length: Maximum length of generated caption.
            num_beams: Number of beams for beam search.
            max_tags: Maximum number of tags to extract.

        Returns:
            Tuple of (caption, tags), or None if image cannot be loaded.
        """
        try:
            image = load_image(image_path)
            if image is None:
                return None
            return self.generate_caption_with_tags(image, max_length, num_beams, max_tags)
        except Exception as e:
            logger.warning(f"Failed to process {image_path}: {e}")
            return None
