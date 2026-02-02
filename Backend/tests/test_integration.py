"""Integration tests for CLIP + FAISS pipeline."""

from pathlib import Path

import numpy as np
import pytest

from photosearch.core.clip_processor import CLIPProcessor
from photosearch.core.vector_index import VectorIndex


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestCLIPFAISSIntegration:
    """Integration tests for CLIP embeddings with FAISS vector search."""

    @pytest.fixture(scope="class")
    def clip_processor(self):
        """Create CLIP processor for integration tests."""
        return CLIPProcessor(device="cpu", local_files_only=True)

    @pytest.fixture(scope="class")
    def test_images(self):
        """Get paths to test images."""
        return {
            "sunset": FIXTURES_DIR / "sunset.jpg",
            "city": FIXTURES_DIR / "city.jpg",
            "nature": FIXTURES_DIR / "nature.jpg",
            "food": FIXTURES_DIR / "food.jpg",
            "animal": FIXTURES_DIR / "animal.jpg",
        }

    def test_clip_faiss_integration(self, clip_processor, test_images):
        """Test complete CLIP + FAISS integration workflow.

        This test:
        1. Generates embeddings for 5 test images using CLIP
        2. Adds embeddings to FAISS index
        3. Searches with text query "sunset"
        4. Verifies sunset image is ranked first
        """
        # Skip if test images are missing
        available_images = {
            name: path for name, path in test_images.items() if path.exists()
        }
        if len(available_images) < 5:
            pytest.skip("Not all test images available")

        # Step 1: Generate embeddings for test images
        image_names = list(available_images.keys())
        embeddings = []
        for name in image_names:
            emb = clip_processor.get_image_embedding_from_path(available_images[name])
            assert emb is not None, f"Failed to generate embedding for {name}"
            embeddings.append(emb)

        embeddings = np.array(embeddings, dtype=np.float32)

        # Step 2: Add to FAISS index
        index = VectorIndex(dimension=clip_processor.embedding_dim)
        ids = np.arange(len(image_names), dtype=np.int64)
        index.add(ids, embeddings)

        assert index.size == len(image_names)

        # Step 3: Search with text query "sunset"
        query_embedding = clip_processor.get_text_embedding("sunset")
        result_ids, scores = index.search(query_embedding, k=5)

        # Step 4: Verify sunset image is ranked first
        sunset_idx = image_names.index("sunset")
        assert result_ids[0] == sunset_idx, (
            f"Expected sunset (ID {sunset_idx}) as top result for 'sunset' query, "
            f"but got ID {result_ids[0]} ({image_names[result_ids[0]]})"
        )

        # Verify scores are in descending order
        assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)), (
            "Search results should be ordered by descending similarity score"
        )

    def test_semantic_search_accuracy(self, clip_processor, test_images):
        """Test that semantic queries find the correct images."""
        available_images = {
            name: path for name, path in test_images.items() if path.exists()
        }
        if len(available_images) < 5:
            pytest.skip("Not all test images available")

        # Generate embeddings and build index
        image_names = list(available_images.keys())
        embeddings = []
        for name in image_names:
            emb = clip_processor.get_image_embedding_from_path(available_images[name])
            embeddings.append(emb)

        index = VectorIndex(dimension=clip_processor.embedding_dim)
        ids = np.arange(len(image_names), dtype=np.int64)
        index.add(ids, np.array(embeddings, dtype=np.float32))

        # Test various semantic queries
        test_queries = {
            "sunset": "a beautiful sunset over the ocean",
            "city": "city skyline with buildings",
            "nature": "nature landscape with trees",
            "food": "delicious food on a plate",
            "animal": "a cute animal",
        }

        for expected_match, query_text in test_queries.items():
            query_embedding = clip_processor.get_text_embedding(query_text)
            result_ids, _ = index.search(query_embedding, k=1)

            expected_idx = image_names.index(expected_match)
            assert result_ids[0] == expected_idx, (
                f"Query '{query_text}' should find '{expected_match}' "
                f"but found '{image_names[result_ids[0]]}'"
            )

    def test_index_persistence_preserves_search_quality(self, clip_processor, test_images, tmp_path):
        """Test that save/load preserves search quality."""
        available_images = {
            name: path for name, path in test_images.items() if path.exists()
        }
        if len(available_images) < 5:
            pytest.skip("Not all test images available")

        # Build index
        image_names = list(available_images.keys())
        embeddings = []
        for name in image_names:
            emb = clip_processor.get_image_embedding_from_path(available_images[name])
            embeddings.append(emb)

        index = VectorIndex(dimension=clip_processor.embedding_dim)
        ids = np.arange(len(image_names), dtype=np.int64)
        index.add(ids, np.array(embeddings, dtype=np.float32))

        # Search before save
        query = clip_processor.get_text_embedding("sunset on beach")
        original_ids, original_scores = index.search(query, k=5)

        # Save and reload
        index_path = tmp_path / "test.index"
        index.save(index_path)
        loaded_index = VectorIndex.load(index_path)

        # Search after load
        loaded_ids, loaded_scores = loaded_index.search(query, k=5)

        # Results should be identical
        np.testing.assert_array_equal(original_ids, loaded_ids)
        np.testing.assert_array_almost_equal(original_scores, loaded_scores, decimal=5)

    def test_batch_indexing_performance(self, clip_processor, test_images):
        """Test that batch operations work efficiently."""
        available_images = {
            name: path for name, path in test_images.items() if path.exists()
        }
        if len(available_images) < 5:
            pytest.skip("Not all test images available")

        # Generate embeddings
        image_names = list(available_images.keys())
        embeddings = []
        for name in image_names:
            emb = clip_processor.get_image_embedding_from_path(available_images[name])
            embeddings.append(emb)

        # Create index and add all at once (batch operation)
        index = VectorIndex(dimension=clip_processor.embedding_dim)
        ids = np.arange(len(image_names), dtype=np.int64)
        embeddings_array = np.array(embeddings, dtype=np.float32)

        # Batch add should work
        index.add(ids, embeddings_array)
        assert index.size == len(image_names)

        # Batch search should work
        queries = np.array([
            clip_processor.get_text_embedding("sunset"),
            clip_processor.get_text_embedding("city"),
        ], dtype=np.float32)
        result_ids, scores = index.search_batch(queries, k=3)

        assert result_ids.shape == (2, 3)
        assert scores.shape == (2, 3)
