"""Tests for BLIP caption generator."""

import logging
from pathlib import Path

import pytest
from PIL import Image

from photosearch.core.caption_generator import CaptionGenerator

logger = logging.getLogger(__name__)


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestModelLoading:
    """Tests for model loading."""

    def test_model_loading(self):
        """Test that BLIP model loads successfully."""
        generator = CaptionGenerator(device="cpu")

        assert generator is not None
        assert generator.model is not None
        assert generator.processor is not None

    def test_model_loading_with_device(self):
        """Test model loading with explicit device."""
        generator = CaptionGenerator(device="cpu")

        assert generator.device == "cpu"


class TestGenerateCaption:
    """Tests for caption generation."""

    @pytest.fixture(scope="class")
    def generator(self):
        """Create caption generator for tests."""
        return CaptionGenerator(device="cpu")

    def test_generate_caption(self, generator):
        """Test generating a caption for an image."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        image = Image.open(image_path)
        caption = generator.generate_caption(image)

        assert caption is not None
        assert isinstance(caption, str)
        assert len(caption) > 0

    def test_generate_caption_from_path(self, generator):
        """Test generating caption from file path."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)

        assert caption is not None
        assert isinstance(caption, str)
        assert len(caption) > 0

    def test_generate_caption_nonexistent_file(self, generator):
        """Test that nonexistent file returns None."""
        caption = generator.generate_caption_from_path("/nonexistent/image.jpg")

        assert caption is None

    def test_generate_caption_rgb_conversion(self, generator):
        """Test that non-RGB images are handled correctly."""
        # Create a grayscale image
        gray_image = Image.new("L", (100, 100), color=128)

        caption = generator.generate_caption(gray_image)

        assert caption is not None
        assert isinstance(caption, str)


class TestCaptionQuality:
    """Tests for caption quality and accuracy."""

    @pytest.fixture(scope="class")
    def generator(self):
        """Create caption generator for tests."""
        return CaptionGenerator(device="cpu")

    def test_sunset_image_caption(self, generator):
        """Test that sunset image caption contains relevant words."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)
        logger.info(f"sunset.jpg caption: {caption}")
        caption_lower = caption.lower()

        # Should contain sunset-related words
        sunset_words = ["sunset", "sun", "sky", "orange", "red", "clouds", "horizon", "evening", "dusk"]
        has_sunset_word = any(word in caption_lower for word in sunset_words)

        assert has_sunset_word, f"Caption '{caption}' should contain sunset-related words"

    def test_city_image_caption(self, generator):
        """Test that city image caption contains relevant words."""
        image_path = FIXTURES_DIR / "city.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)
        logger.info(f"city.jpg caption: {caption}")
        caption_lower = caption.lower()

        # Should contain city-related words
        city_words = ["city", "building", "buildings", "skyline", "urban", "street", "tower", "skyscraper"]
        has_city_word = any(word in caption_lower for word in city_words)

        assert has_city_word, f"Caption '{caption}' should contain city-related words"

    def test_nature_image_caption(self, generator):
        """Test that nature image caption contains relevant words."""
        image_path = FIXTURES_DIR / "nature.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)
        logger.info(f"nature.jpg caption: {caption}")
        caption_lower = caption.lower()

        # Should contain nature-related words
        nature_words = ["nature", "tree", "trees", "forest", "mountain", "green", "landscape", "grass", "field", "lake", "river", "water"]
        has_nature_word = any(word in caption_lower for word in nature_words)

        assert has_nature_word, f"Caption '{caption}' should contain nature-related words"

    def test_food_image_caption(self, generator):
        """Test that food image caption contains relevant words."""
        image_path = FIXTURES_DIR / "food.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)
        logger.info(f"food.jpg caption: {caption}")
        caption_lower = caption.lower()

        # Should contain food-related words
        food_words = ["food", "plate", "dish", "meal", "eat", "eating", "table", "restaurant", "bowl", "pizza", "salad", "sandwich", "bread", "meat", "vegetable"]
        has_food_word = any(word in caption_lower for word in food_words)

        assert has_food_word, f"Caption '{caption}' should contain food-related words"

    def test_animal_image_caption(self, generator):
        """Test that animal image caption contains relevant words."""
        image_path = FIXTURES_DIR / "animal.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)
        logger.info(f"animal.jpg caption: {caption}")
        caption_lower = caption.lower()

        # Should contain animal-related words
        animal_words = ["animal", "dog", "cat", "bird", "pet", "puppy", "kitten", "wildlife", "creature", "fur", "feather", "otter", "bear", "lion", "tiger", "elephant", "horse", "rabbit"]
        has_animal_word = any(word in caption_lower for word in animal_words)

        assert has_animal_word, f"Caption '{caption}' should contain animal-related words"

    def test_captions_are_grammatical(self, generator):
        """Test that generated captions are grammatically reasonable."""
        test_images = [
            FIXTURES_DIR / "sunset.jpg",
            FIXTURES_DIR / "city.jpg",
            FIXTURES_DIR / "nature.jpg",
        ]

        for image_path in test_images:
            if not image_path.exists():
                continue

            caption = generator.generate_caption_from_path(image_path)

            # Basic checks for grammatical structure
            # Captions should start with lowercase 'a' or another article/word
            # and should have reasonable length
            assert len(caption) >= 5, f"Caption too short: '{caption}'"
            assert len(caption) <= 200, f"Caption too long: '{caption}'"

            # Should contain at least one space (multiple words)
            assert " " in caption, f"Caption should have multiple words: '{caption}'"


class TestExtractTags:
    """Tests for tag extraction."""

    @pytest.fixture(scope="class")
    def generator(self):
        """Create caption generator for tests."""
        return CaptionGenerator(device="cpu")

    def test_extract_tags(self, generator):
        """Test extracting tags from a caption."""
        caption = "a beautiful sunset over the ocean with orange clouds"
        tags = generator.extract_tags(caption)

        assert isinstance(tags, list)
        assert len(tags) > 0

        # Should contain key nouns
        assert "sunset" in tags or "ocean" in tags or "clouds" in tags

    def test_extract_tags_filters_stop_words(self, generator):
        """Test that stop words are filtered out."""
        caption = "the cat is sitting on the mat"
        tags = generator.extract_tags(caption)

        # Stop words should not be in tags
        stop_words = ["the", "is", "on"]
        for word in stop_words:
            assert word not in tags

    def test_extract_tags_max_limit(self, generator):
        """Test that max_tags limit is respected."""
        caption = "a beautiful sunset over the ocean with orange clouds and mountains in the background"
        tags = generator.extract_tags(caption, max_tags=3)

        assert len(tags) <= 3

    def test_extract_tags_empty_caption(self, generator):
        """Test extracting tags from empty caption."""
        tags = generator.extract_tags("")

        assert tags == []

    def test_extract_tags_deduplication(self, generator):
        """Test that duplicate words are removed."""
        caption = "the dog and the dog playing with another dog"
        tags = generator.extract_tags(caption)

        # "dog" should only appear once
        assert tags.count("dog") == 1

    def test_extract_tags_lowercase(self, generator):
        """Test that tags are lowercase."""
        caption = "A Beautiful Sunset Over Mountains"
        tags = generator.extract_tags(caption)

        for tag in tags:
            assert tag == tag.lower()


class TestImageTypes:
    """Tests for handling various image types."""

    @pytest.fixture(scope="class")
    def generator(self):
        """Create caption generator for tests."""
        return CaptionGenerator(device="cpu")

    def test_jpeg_image(self, generator):
        """Test caption generation for JPEG image."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)
        assert caption is not None

    def test_png_image(self, generator):
        """Test caption generation for PNG image."""
        image_path = FIXTURES_DIR / "photo_no_exif.png"
        if not image_path.exists():
            pytest.skip("Test image not available")

        caption = generator.generate_caption_from_path(image_path)
        assert caption is not None

    def test_small_image(self, generator):
        """Test caption generation for small image."""
        # Create a small image
        small_image = Image.new("RGB", (32, 32), color=(255, 128, 0))

        caption = generator.generate_caption(small_image)
        assert caption is not None
        assert isinstance(caption, str)

    def test_large_image(self, generator):
        """Test caption generation for large image."""
        # Create a larger image
        large_image = Image.new("RGB", (1920, 1080), color=(0, 128, 255))

        caption = generator.generate_caption(large_image)
        assert caption is not None
        assert isinstance(caption, str)

    def test_rgba_image(self, generator):
        """Test caption generation for RGBA image (with alpha channel)."""
        # Create RGBA image
        rgba_image = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))

        caption = generator.generate_caption(rgba_image)
        assert caption is not None
        assert isinstance(caption, str)


class TestBatchGeneration:
    """Tests for batch caption generation."""

    @pytest.fixture(scope="class")
    def generator(self):
        """Create caption generator for tests."""
        return CaptionGenerator(device="cpu")

    def test_generate_captions_batch(self, generator):
        """Test generating captions for multiple images."""
        # Create test images
        images = [
            Image.new("RGB", (100, 100), color=(255, 0, 0)),
            Image.new("RGB", (100, 100), color=(0, 255, 0)),
            Image.new("RGB", (100, 100), color=(0, 0, 255)),
        ]

        captions = generator.generate_captions_batch(images)

        assert len(captions) == 3
        for caption in captions:
            assert isinstance(caption, str)
            assert len(caption) > 0

    def test_generate_captions_batch_real_images(self, generator):
        """Test batch generation with real test images."""
        image_paths = [
            FIXTURES_DIR / "sunset.jpg",
            FIXTURES_DIR / "city.jpg",
            FIXTURES_DIR / "nature.jpg",
        ]

        images = []
        for path in image_paths:
            if path.exists():
                images.append(Image.open(path))

        if len(images) < 2:
            pytest.skip("Not enough test images available")

        captions = generator.generate_captions_batch(images)

        assert len(captions) == len(images)
        for caption in captions:
            assert isinstance(caption, str)
            assert len(caption) > 0


class TestCaptionWithTags:
    """Tests for combined caption and tag generation."""

    @pytest.fixture(scope="class")
    def generator(self):
        """Create caption generator for tests."""
        return CaptionGenerator(device="cpu")

    def test_generate_caption_with_tags(self, generator):
        """Test generating caption and tags together."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        image = Image.open(image_path)
        caption, tags = generator.generate_caption_with_tags(image)

        assert isinstance(caption, str)
        assert len(caption) > 0
        assert isinstance(tags, list)
        # Tags should be derived from the caption
        for tag in tags:
            assert tag.lower() in caption.lower() or tag in caption.lower()

    def test_generate_caption_with_tags_from_path(self, generator):
        """Test generating caption and tags from file path."""
        image_path = FIXTURES_DIR / "sunset.jpg"
        if not image_path.exists():
            pytest.skip("Test image not available")

        result = generator.generate_caption_with_tags_from_path(image_path)

        assert result is not None
        caption, tags = result
        assert isinstance(caption, str)
        assert isinstance(tags, list)

    def test_generate_caption_with_tags_nonexistent(self, generator):
        """Test that nonexistent file returns None."""
        result = generator.generate_caption_with_tags_from_path("/nonexistent/image.jpg")

        assert result is None
