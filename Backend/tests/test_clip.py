"""Tests for CLIP processor."""

import pytest
import numpy as np
from pathlib import Path
from PIL import Image

from photosearch.core.clip_processor import CLIPProcessor


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def clip_processor():
    """Create CLIP processor (shared across tests for efficiency)."""
    return CLIPProcessor(device="cpu")  # Use CPU for consistent testing


@pytest.fixture
def real_images():
    """Load real test images from fixtures."""
    images = {}
    for name in ["sunset.jpg", "city.jpg", "nature.jpg", "food.jpg", "animal.jpg"]:
        path = FIXTURES_DIR / name
        if path.exists():
            images[name] = Image.open(path)
    return images


class TestModelLoading:
    """Tests for model loading."""

    def test_model_loads_successfully(self, clip_processor):
        """Test that CLIP model loads without errors."""
        assert clip_processor.model is not None
        assert clip_processor.processor is not None

    def test_embedding_dimension(self, clip_processor):
        """Test that embedding dimension is correct (512 for base model)."""
        assert clip_processor.embedding_dim == 512

    def test_device_selection(self, clip_processor):
        """Test that device is properly selected."""
        assert clip_processor.device in ["cpu", "cuda", "mps"]


class TestImageEmbedding:
    """Tests for image embedding generation."""

    def test_generate_image_embedding(self, clip_processor, real_images):
        """Test generating embedding for a single image."""
        image = real_images.get("sunset.jpg")
        if image is None:
            pytest.skip("Test image not available")

        embedding = clip_processor.get_image_embedding(image)

        assert embedding is not None
        assert embedding.shape == (512,)
        assert embedding.dtype == np.float32 or embedding.dtype == np.float64

    def test_embedding_is_normalized(self, clip_processor, real_images):
        """Test that embeddings are L2 normalized."""
        image = real_images.get("sunset.jpg")
        if image is None:
            pytest.skip("Test image not available")

        embedding = clip_processor.get_image_embedding(image)
        norm = np.linalg.norm(embedding)

        assert abs(norm - 1.0) < 1e-5, f"Embedding norm should be 1.0, got {norm}"

    def test_embedding_from_path(self, clip_processor):
        """Test generating embedding from file path."""
        path = FIXTURES_DIR / "sunset.jpg"
        if not path.exists():
            pytest.skip("Test image not available")

        embedding = clip_processor.get_image_embedding_from_path(path)

        assert embedding is not None
        assert embedding.shape == (512,)

    def test_embedding_from_invalid_path(self, clip_processor):
        """Test that invalid path returns None."""
        embedding = clip_processor.get_image_embedding_from_path("/nonexistent/path.jpg")
        assert embedding is None

    def test_same_image_same_embedding(self, clip_processor, real_images):
        """Test that same image produces identical embedding."""
        image = real_images.get("sunset.jpg")
        if image is None:
            pytest.skip("Test image not available")

        embedding1 = clip_processor.get_image_embedding(image)
        embedding2 = clip_processor.get_image_embedding(image)

        similarity = CLIPProcessor.cosine_similarity(embedding1, embedding2)
        assert similarity > 0.999, f"Same image should have similarity ~1.0, got {similarity}"


class TestTextEmbedding:
    """Tests for text embedding generation."""

    def test_generate_text_embedding(self, clip_processor):
        """Test generating embedding for text."""
        embedding = clip_processor.get_text_embedding("a photo of a sunset")

        assert embedding is not None
        assert embedding.shape == (512,)

    def test_text_embedding_is_normalized(self, clip_processor):
        """Test that text embeddings are L2 normalized."""
        embedding = clip_processor.get_text_embedding("a beautiful landscape")
        norm = np.linalg.norm(embedding)

        assert abs(norm - 1.0) < 1e-5, f"Embedding norm should be 1.0, got {norm}"

    def test_different_texts_different_embeddings(self, clip_processor):
        """Test that different texts produce different embeddings."""
        embedding1 = clip_processor.get_text_embedding("a sunset on the beach")
        embedding2 = clip_processor.get_text_embedding("a cat sleeping on a couch")

        similarity = CLIPProcessor.cosine_similarity(embedding1, embedding2)
        assert similarity < 0.9, f"Different texts should have lower similarity, got {similarity}"


class TestTextImageMatching:
    """Tests for text-image similarity matching with real photos."""

    def test_sunset_query_matches_sunset_image(self, clip_processor):
        """Test that 'sunset' query matches sunset image best."""
        sunset_path = FIXTURES_DIR / "sunset.jpg"
        city_path = FIXTURES_DIR / "city.jpg"

        if not sunset_path.exists() or not city_path.exists():
            pytest.skip("Test images not available")

        sunset_emb = clip_processor.get_image_embedding_from_path(sunset_path)
        city_emb = clip_processor.get_image_embedding_from_path(city_path)
        query_emb = clip_processor.get_text_embedding("a beautiful sunset over the ocean")

        sunset_score = CLIPProcessor.cosine_similarity(query_emb, sunset_emb)
        city_score = CLIPProcessor.cosine_similarity(query_emb, city_emb)

        assert sunset_score > city_score, (
            f"'sunset' query should match sunset.jpg better. "
            f"Sunset: {sunset_score:.3f}, City: {city_score:.3f}"
        )

    def test_city_query_matches_city_image(self, clip_processor):
        """Test that 'city' query matches city image best."""
        city_path = FIXTURES_DIR / "city.jpg"
        nature_path = FIXTURES_DIR / "nature.jpg"

        if not city_path.exists() or not nature_path.exists():
            pytest.skip("Test images not available")

        city_emb = clip_processor.get_image_embedding_from_path(city_path)
        nature_emb = clip_processor.get_image_embedding_from_path(nature_path)
        query_emb = clip_processor.get_text_embedding("city skyline with tall buildings")

        city_score = CLIPProcessor.cosine_similarity(query_emb, city_emb)
        nature_score = CLIPProcessor.cosine_similarity(query_emb, nature_emb)

        assert city_score > nature_score, (
            f"'city' query should match city.jpg better. "
            f"City: {city_score:.3f}, Nature: {nature_score:.3f}"
        )

    def test_nature_query_matches_nature_image(self, clip_processor):
        """Test that 'nature' query matches nature image best."""
        nature_path = FIXTURES_DIR / "nature.jpg"
        food_path = FIXTURES_DIR / "food.jpg"

        if not nature_path.exists() or not food_path.exists():
            pytest.skip("Test images not available")

        nature_emb = clip_processor.get_image_embedding_from_path(nature_path)
        food_emb = clip_processor.get_image_embedding_from_path(food_path)
        query_emb = clip_processor.get_text_embedding("nature landscape with mountains or forest")

        nature_score = CLIPProcessor.cosine_similarity(query_emb, nature_emb)
        food_score = CLIPProcessor.cosine_similarity(query_emb, food_emb)

        assert nature_score > food_score, (
            f"'nature' query should match nature.jpg better. "
            f"Nature: {nature_score:.3f}, Food: {food_score:.3f}"
        )

    def test_food_query_matches_food_image(self, clip_processor):
        """Test that 'food' query matches food image best."""
        food_path = FIXTURES_DIR / "food.jpg"
        animal_path = FIXTURES_DIR / "animal.jpg"

        if not food_path.exists() or not animal_path.exists():
            pytest.skip("Test images not available")

        food_emb = clip_processor.get_image_embedding_from_path(food_path)
        animal_emb = clip_processor.get_image_embedding_from_path(animal_path)
        query_emb = clip_processor.get_text_embedding("delicious food on a plate")

        food_score = CLIPProcessor.cosine_similarity(query_emb, food_emb)
        animal_score = CLIPProcessor.cosine_similarity(query_emb, animal_emb)

        assert food_score > animal_score, (
            f"'food' query should match food.jpg better. "
            f"Food: {food_score:.3f}, Animal: {animal_score:.3f}"
        )

    def test_animal_query_matches_animal_image(self, clip_processor):
        """Test that 'animal' query matches animal image best."""
        animal_path = FIXTURES_DIR / "animal.jpg"
        sunset_path = FIXTURES_DIR / "sunset.jpg"

        if not animal_path.exists() or not sunset_path.exists():
            pytest.skip("Test images not available")

        animal_emb = clip_processor.get_image_embedding_from_path(animal_path)
        sunset_emb = clip_processor.get_image_embedding_from_path(sunset_path)
        query_emb = clip_processor.get_text_embedding("a cute animal or pet")

        animal_score = CLIPProcessor.cosine_similarity(query_emb, animal_emb)
        sunset_score = CLIPProcessor.cosine_similarity(query_emb, sunset_emb)

        assert animal_score > sunset_score, (
            f"'animal' query should match animal.jpg better. "
            f"Animal: {animal_score:.3f}, Sunset: {sunset_score:.3f}"
        )

    def test_query_ranks_all_images_correctly(self, clip_processor):
        """Test that each query ranks its target image as #1."""
        images = {
            "sunset.jpg": "a beautiful sunset over the ocean",
            "city.jpg": "city skyline with tall buildings",
            "nature.jpg": "nature landscape with mountains or forest",
            "food.jpg": "delicious food on a plate",
            "animal.jpg": "a cute animal or pet",
        }

        # Load all embeddings
        embeddings = {}
        for name in images.keys():
            path = FIXTURES_DIR / name
            if path.exists():
                embeddings[name] = clip_processor.get_image_embedding_from_path(path)

        if len(embeddings) < 5:
            pytest.skip("Not all test images available")

        # Test each query
        for target_name, query_text in images.items():
            query_emb = clip_processor.get_text_embedding(query_text)

            # Calculate scores for all images
            scores = {
                name: CLIPProcessor.cosine_similarity(query_emb, emb)
                for name, emb in embeddings.items()
            }

            # Find best match
            best_match = max(scores, key=scores.get)
            assert best_match == target_name, (
                f"Query '{query_text}' should match {target_name}, "
                f"but matched {best_match}. Scores: {scores}"
            )


class TestBatchProcessing:
    """Tests for batch embedding generation."""

    def test_batch_image_embeddings(self, clip_processor, real_images):
        """Test generating embeddings for multiple images at once."""
        images = list(real_images.values())
        if len(images) < 2:
            pytest.skip("Not enough test images")

        embeddings = clip_processor.get_image_embeddings_batch(images)

        assert embeddings.shape == (len(images), 512)

        # Check all are normalized
        norms = np.linalg.norm(embeddings, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)

    def test_batch_text_embeddings(self, clip_processor):
        """Test generating embeddings for multiple texts."""
        texts = [
            "a sunset on the beach",
            "a city skyline at night",
            "mountains covered in snow",
        ]

        embeddings = clip_processor.get_text_embeddings_batch(texts)

        assert embeddings.shape == (3, 512)

        # Check all are normalized
        norms = np.linalg.norm(embeddings, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)

    def test_batch_matches_single(self, clip_processor, real_images):
        """Test that batch processing gives same results as single processing."""
        images = list(real_images.values())[:2]
        if len(images) < 2:
            pytest.skip("Not enough test images")

        # Single processing
        single_embeddings = [clip_processor.get_image_embedding(img) for img in images]

        # Batch processing
        batch_embeddings = clip_processor.get_image_embeddings_batch(images)

        # Compare
        for i, (single, batch) in enumerate(zip(single_embeddings, batch_embeddings)):
            similarity = CLIPProcessor.cosine_similarity(single, batch)
            assert similarity > 0.999, f"Batch embedding {i} should match single embedding"


class TestCosineSimilarity:
    """Tests for cosine similarity computation."""

    def test_identical_embeddings(self, clip_processor):
        """Test similarity of identical embeddings."""
        embedding = clip_processor.get_text_embedding("test text")
        similarity = CLIPProcessor.cosine_similarity(embedding, embedding)

        assert abs(similarity - 1.0) < 1e-5

    def test_batch_cosine_similarity(self, clip_processor):
        """Test batch cosine similarity computation."""
        texts = ["sunset", "beach", "mountain", "city"]
        embeddings = clip_processor.get_text_embeddings_batch(texts)
        query = clip_processor.get_text_embedding("ocean sunset")

        similarities = CLIPProcessor.batch_cosine_similarity(query, embeddings)

        assert similarities.shape == (4,)
        # "sunset" and "beach" should be more similar to "ocean sunset"
        assert similarities[0] > similarities[3], "sunset should be more similar than city"


class TestRealPhotos:
    """Integration tests with real-world photos."""

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "real_iphone.jpg").exists(),
        reason="Real iPhone photo not available"
    )
    def test_real_iphone_photo_embedding(self, clip_processor):
        """Test embedding generation for real iPhone photo."""
        embedding = clip_processor.get_image_embedding_from_path(
            FIXTURES_DIR / "real_iphone.jpg"
        )

        assert embedding is not None
        assert embedding.shape == (512,)
        assert abs(np.linalg.norm(embedding) - 1.0) < 1e-5

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "real_heic.heic").exists(),
        reason="Real HEIC photo not available"
    )
    def test_real_heic_photo_embedding(self, clip_processor):
        """Test embedding generation for real HEIC photo."""
        embedding = clip_processor.get_image_embedding_from_path(
            FIXTURES_DIR / "real_heic.heic"
        )

        assert embedding is not None
        assert embedding.shape == (512,)

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "animal.jpg").exists(),
        reason="Animal photo not available"
    )
    def test_animal_photo_has_exif(self, clip_processor):
        """Test that animal.jpg (Canon EOS) works and has EXIF."""
        from photosearch.utils.exif import extract_exif_data

        path = FIXTURES_DIR / "animal.jpg"
        exif = extract_exif_data(path)

        # Check EXIF was extracted
        assert exif.camera_make == "Canon"
        assert "EOS" in exif.camera_model
        assert exif.timestamp is not None

        # Check embedding works
        embedding = clip_processor.get_image_embedding_from_path(path)
        assert embedding is not None
        assert embedding.shape == (512,)
