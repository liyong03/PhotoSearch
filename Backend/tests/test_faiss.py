"""Tests for FAISS vector index."""

import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from photosearch.core.vector_index import VectorIndex


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def create_random_embeddings(n: int, dim: int = 512, seed: int = 42) -> np.ndarray:
    """Create random normalized embeddings for testing."""
    rng = np.random.default_rng(seed)
    embeddings = rng.standard_normal((n, dim)).astype(np.float32)
    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms
    return embeddings


class TestCreateIndex:
    """Tests for index creation."""

    def test_create_index(self):
        """Test creating empty FAISS index."""
        index = VectorIndex(dimension=512)

        assert index is not None
        assert index.dimension == 512
        assert index.size == 0

    def test_create_index_custom_dimension(self):
        """Test creating index with custom dimension."""
        index = VectorIndex(dimension=768)

        assert index.dimension == 768
        assert index.size == 0


class TestAddEmbeddings:
    """Tests for adding embeddings."""

    def test_add_single_embedding(self):
        """Test adding a single embedding."""
        index = VectorIndex()
        embedding = create_random_embeddings(1)[0]

        index.add_single(id=1, embedding=embedding)

        assert index.size == 1
        assert index.has_id(1)

    def test_add_multiple_embeddings(self):
        """Test adding multiple embeddings at once."""
        index = VectorIndex()
        n = 100
        ids = np.arange(n, dtype=np.int64)
        embeddings = create_random_embeddings(n)

        index.add(ids, embeddings)

        assert index.size == n
        for i in range(n):
            assert index.has_id(i)

    def test_add_embeddings_incremental(self):
        """Test adding embeddings incrementally."""
        index = VectorIndex()

        # Add first batch
        ids1 = np.array([1, 2, 3], dtype=np.int64)
        embeddings1 = create_random_embeddings(3, seed=1)
        index.add(ids1, embeddings1)
        assert index.size == 3

        # Add second batch
        ids2 = np.array([10, 20, 30], dtype=np.int64)
        embeddings2 = create_random_embeddings(3, seed=2)
        index.add(ids2, embeddings2)
        assert index.size == 6

        # Verify all IDs exist
        for id in [1, 2, 3, 10, 20, 30]:
            assert index.has_id(id)

    def test_add_empty_raises_nothing(self):
        """Test that adding empty arrays does nothing."""
        index = VectorIndex()

        ids = np.array([], dtype=np.int64)
        embeddings = np.zeros((0, 512), dtype=np.float32)

        index.add(ids, embeddings)
        assert index.size == 0

    def test_add_mismatched_lengths_raises(self):
        """Test that mismatched IDs and embeddings raises error."""
        index = VectorIndex()

        ids = np.array([1, 2, 3], dtype=np.int64)
        embeddings = create_random_embeddings(2)

        with pytest.raises(ValueError, match="must match"):
            index.add(ids, embeddings)

    def test_add_wrong_dimension_raises(self):
        """Test that wrong embedding dimension raises error."""
        index = VectorIndex(dimension=512)

        ids = np.array([1], dtype=np.int64)
        embeddings = create_random_embeddings(1, dim=768)

        with pytest.raises(ValueError, match="must be 512"):
            index.add(ids, embeddings)


class TestSearch:
    """Tests for similarity search."""

    def test_search_returns_correct_results(self):
        """Test that search returns the most similar items."""
        index = VectorIndex()

        # Add embeddings
        n = 10
        ids = np.arange(n, dtype=np.int64)
        embeddings = create_random_embeddings(n)
        index.add(ids, embeddings)

        # Query with one of the embeddings - should return itself as top result
        query = embeddings[5]
        result_ids, scores = index.search(query, k=3)

        assert len(result_ids) == 3
        assert result_ids[0] == 5  # Top match should be itself
        assert scores[0] > 0.99  # High similarity score

    def test_search_empty_index(self):
        """Test search on empty index."""
        index = VectorIndex()
        query = create_random_embeddings(1)[0]

        result_ids, scores = index.search(query, k=10)

        assert len(result_ids) == 0
        assert len(scores) == 0

    def test_search_k_larger_than_index(self):
        """Test search when k > index size."""
        index = VectorIndex()

        ids = np.array([1, 2, 3], dtype=np.int64)
        embeddings = create_random_embeddings(3)
        index.add(ids, embeddings)

        query = embeddings[0]
        result_ids, scores = index.search(query, k=100)

        # Should return only 3 results
        assert len(result_ids) == 3

    def test_search_similarity_ordering(self):
        """Test that results are ordered by similarity."""
        index = VectorIndex()

        # Create embeddings where we know the similarity
        base = create_random_embeddings(1)[0]

        # Create variations with known similarity
        embeddings = np.array([
            base,  # ID 0: identical
            base + 0.1 * create_random_embeddings(1, seed=1)[0],  # ID 1: small change
            base + 0.5 * create_random_embeddings(1, seed=2)[0],  # ID 2: medium change
            create_random_embeddings(1, seed=3)[0],  # ID 3: random (low similarity)
        ])
        # Re-normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms

        ids = np.array([0, 1, 2, 3], dtype=np.int64)
        index.add(ids, embeddings.astype(np.float32))

        result_ids, scores = index.search(base, k=4)

        # Results should be ordered by similarity (highest first)
        assert result_ids[0] == 0  # Identical
        assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))

    def test_search_batch(self):
        """Test batch search with multiple queries."""
        index = VectorIndex()

        n = 100
        ids = np.arange(n, dtype=np.int64)
        embeddings = create_random_embeddings(n)
        index.add(ids, embeddings)

        # Query with multiple embeddings
        queries = embeddings[[10, 20, 30]]
        result_ids, scores = index.search_batch(queries, k=5)

        assert result_ids.shape == (3, 5)
        assert scores.shape == (3, 5)

        # Each query's top result should be itself
        assert result_ids[0, 0] == 10
        assert result_ids[1, 0] == 20
        assert result_ids[2, 0] == 30


class TestPersistence:
    """Tests for saving and loading index."""

    def test_save_and_load(self):
        """Test saving and loading index preserves data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "test.index"

            # Create and populate index
            index = VectorIndex()
            ids = np.array([1, 2, 3, 4, 5], dtype=np.int64)
            embeddings = create_random_embeddings(5)
            index.add(ids, embeddings)

            # Save
            index.save(index_path)
            assert index_path.exists()

            # Load
            loaded = VectorIndex.load(index_path)

            assert loaded.size == 5
            assert loaded.dimension == 512

            # Verify embeddings are preserved
            for i, id in enumerate(ids):
                assert loaded.has_id(id)
                original = index.get_embedding(id)
                loaded_emb = loaded.get_embedding(id)
                assert np.allclose(original, loaded_emb, atol=1e-5)

    def test_load_nonexistent_raises(self):
        """Test loading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            VectorIndex.load("/nonexistent/path.index")

    def test_save_creates_parent_dirs(self):
        """Test that save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "nested" / "dirs" / "test.index"

            index = VectorIndex()
            index.add_single(1, create_random_embeddings(1)[0])
            index.save(index_path)

            assert index_path.exists()

    def test_search_after_load(self):
        """Test that search works correctly after loading."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "test.index"

            # Create index with known data
            index = VectorIndex()
            ids = np.arange(100, dtype=np.int64)
            embeddings = create_random_embeddings(100)
            index.add(ids, embeddings)

            # Get search results before save
            query = embeddings[42]
            original_ids, original_scores = index.search(query, k=5)

            # Save and reload
            index.save(index_path)
            loaded = VectorIndex.load(index_path)

            # Search should give same results
            loaded_ids, loaded_scores = loaded.search(query, k=5)

            np.testing.assert_array_equal(original_ids, loaded_ids)
            np.testing.assert_array_almost_equal(original_scores, loaded_scores)


class TestRemoveEmbedding:
    """Tests for removing embeddings (soft delete)."""

    def test_remove_single(self):
        """Test removing a single embedding."""
        index = VectorIndex()
        ids = np.array([1, 2, 3, 4, 5], dtype=np.int64)
        embeddings = create_random_embeddings(5)
        index.add(ids, embeddings)

        removed = index.remove([3])

        assert removed == 1
        # Note: size stays 5 (soft delete), but ID is not accessible
        assert not index.has_id(3)
        assert index.has_id(1)
        assert index.has_id(5)

    def test_remove_multiple(self):
        """Test removing multiple embeddings."""
        index = VectorIndex()
        ids = np.arange(10, dtype=np.int64)
        embeddings = create_random_embeddings(10)
        index.add(ids, embeddings)

        removed = index.remove([2, 4, 6, 8])

        assert removed == 4
        # Note: size stays 10 (soft delete)

        for id in [2, 4, 6, 8]:
            assert not index.has_id(id)
        for id in [0, 1, 3, 5, 7, 9]:
            assert index.has_id(id)

    def test_remove_nonexistent(self):
        """Test removing non-existent IDs."""
        index = VectorIndex()
        ids = np.array([1, 2, 3], dtype=np.int64)
        embeddings = create_random_embeddings(3)
        index.add(ids, embeddings)

        # Try to remove non-existent ID
        removed = index.remove([999])

        assert removed == 0
        assert index.size == 3

    def test_remove_not_in_search_results(self):
        """Test that removed IDs don't appear in search results."""
        index = VectorIndex()
        ids = np.arange(100, dtype=np.int64)
        embeddings = create_random_embeddings(100)
        index.add(ids, embeddings)

        # Remove ID 42
        index.remove([42])

        # Query with embedding that was ID 42 (should find similar ones)
        query = embeddings[42]
        result_ids, _ = index.search(query, k=10)

        assert 42 not in result_ids

    def test_clear_removes_all(self):
        """Test that clear removes all embeddings."""
        index = VectorIndex()
        ids = np.arange(100, dtype=np.int64)
        embeddings = create_random_embeddings(100)
        index.add(ids, embeddings)

        index.clear()

        assert index.size == 0


class TestLargeIndex:
    """Performance tests for large indices."""

    def test_large_index_search_performance(self):
        """Test that search is fast on large index (10k vectors)."""
        index = VectorIndex()

        # Add 10k embeddings
        n = 10000
        ids = np.arange(n, dtype=np.int64)
        embeddings = create_random_embeddings(n)
        index.add(ids, embeddings)

        # Time search
        query = create_random_embeddings(1, seed=999)[0]

        # Warm up
        index.search(query, k=100)

        # Timed search
        start = time.perf_counter()
        for _ in range(10):
            result_ids, scores = index.search(query, k=100)
        elapsed = (time.perf_counter() - start) / 10 * 1000  # ms per search

        assert index.size == n
        assert len(result_ids) == 100
        assert elapsed < 50, f"Search took {elapsed:.1f}ms, should be < 50ms"

    def test_large_index_add_performance(self):
        """Test adding to large index is reasonably fast."""
        index = VectorIndex()

        # Add in batches
        batch_size = 1000
        n_batches = 10

        start = time.perf_counter()
        for i in range(n_batches):
            ids = np.arange(i * batch_size, (i + 1) * batch_size, dtype=np.int64)
            embeddings = create_random_embeddings(batch_size, seed=i)
            index.add(ids, embeddings)
        elapsed = time.perf_counter() - start

        assert index.size == batch_size * n_batches
        assert elapsed < 5, f"Adding 10k vectors took {elapsed:.1f}s, should be < 5s"


class TestGetEmbedding:
    """Tests for retrieving embeddings by ID."""

    def test_get_embedding(self):
        """Test retrieving an embedding by ID."""
        index = VectorIndex()
        embeddings = create_random_embeddings(5)
        ids = np.array([10, 20, 30, 40, 50], dtype=np.int64)
        index.add(ids, embeddings)

        retrieved = index.get_embedding(30)

        assert retrieved is not None
        np.testing.assert_array_almost_equal(retrieved, embeddings[2])

    def test_get_nonexistent_embedding(self):
        """Test retrieving non-existent embedding returns None."""
        index = VectorIndex()
        embeddings = create_random_embeddings(3)
        ids = np.array([1, 2, 3], dtype=np.int64)
        index.add(ids, embeddings)

        retrieved = index.get_embedding(999)

        assert retrieved is None


class TestIntegrationWithCLIP:
    """Integration tests with CLIP processor using real images."""

    @pytest.fixture(scope="class")
    def clip_processor(self):
        """Create CLIP processor for integration tests."""
        from photosearch.core.clip_processor import CLIPProcessor
        return CLIPProcessor(device="cpu")

    @pytest.fixture(scope="class")
    def image_embeddings(self, clip_processor):
        """Load real image embeddings."""
        images = {
            "sunset": FIXTURES_DIR / "sunset.jpg",
            "city": FIXTURES_DIR / "city.jpg",
            "nature": FIXTURES_DIR / "nature.jpg",
            "food": FIXTURES_DIR / "food.jpg",
            "animal": FIXTURES_DIR / "animal.jpg",
        }
        embeddings = {}
        for name, path in images.items():
            if path.exists():
                emb = clip_processor.get_image_embedding_from_path(path)
                if emb is not None:
                    embeddings[name] = emb
        return embeddings

    def test_add_real_image_embeddings(self, clip_processor, image_embeddings):
        """Test adding real CLIP embeddings to index."""
        if len(image_embeddings) < 5:
            pytest.skip("Not all test images available")

        index = VectorIndex(dimension=clip_processor.embedding_dim)

        # Add embeddings with IDs
        ids = np.arange(len(image_embeddings), dtype=np.int64)
        embeddings = np.array(list(image_embeddings.values()), dtype=np.float32)
        index.add(ids, embeddings)

        assert index.size == len(image_embeddings)

    def test_search_sunset_query(self, clip_processor, image_embeddings):
        """Test that 'sunset' query finds sunset image in index."""
        if len(image_embeddings) < 5:
            pytest.skip("Not all test images available")

        index = VectorIndex(dimension=clip_processor.embedding_dim)

        # Add all images
        names = list(image_embeddings.keys())
        ids = np.arange(len(names), dtype=np.int64)
        embeddings = np.array(list(image_embeddings.values()), dtype=np.float32)
        index.add(ids, embeddings)

        # Search with text query
        query = clip_processor.get_text_embedding("a beautiful sunset over the ocean")
        result_ids, scores = index.search(query, k=5)

        # sunset should be top result (ID 0 = "sunset")
        sunset_idx = names.index("sunset")
        assert result_ids[0] == sunset_idx, (
            f"Expected sunset (ID {sunset_idx}) as top result, got ID {result_ids[0]}"
        )

    def test_search_city_query(self, clip_processor, image_embeddings):
        """Test that 'city' query finds city image in index."""
        if len(image_embeddings) < 5:
            pytest.skip("Not all test images available")

        index = VectorIndex(dimension=clip_processor.embedding_dim)

        names = list(image_embeddings.keys())
        ids = np.arange(len(names), dtype=np.int64)
        embeddings = np.array(list(image_embeddings.values()), dtype=np.float32)
        index.add(ids, embeddings)

        query = clip_processor.get_text_embedding("city skyline with tall buildings")
        result_ids, scores = index.search(query, k=5)

        city_idx = names.index("city")
        assert result_ids[0] == city_idx, (
            f"Expected city (ID {city_idx}) as top result, got ID {result_ids[0]}"
        )

    def test_search_animal_query(self, clip_processor, image_embeddings):
        """Test that 'animal' query finds animal image in index."""
        if len(image_embeddings) < 5:
            pytest.skip("Not all test images available")

        index = VectorIndex(dimension=clip_processor.embedding_dim)

        names = list(image_embeddings.keys())
        ids = np.arange(len(names), dtype=np.int64)
        embeddings = np.array(list(image_embeddings.values()), dtype=np.float32)
        index.add(ids, embeddings)

        query = clip_processor.get_text_embedding("a cute animal or pet")
        result_ids, scores = index.search(query, k=5)

        animal_idx = names.index("animal")
        assert result_ids[0] == animal_idx, (
            f"Expected animal (ID {animal_idx}) as top result, got ID {result_ids[0]}"
        )

    def test_all_queries_find_correct_images(self, clip_processor, image_embeddings):
        """Test that each query type finds its corresponding image as #1."""
        if len(image_embeddings) < 5:
            pytest.skip("Not all test images available")

        index = VectorIndex(dimension=clip_processor.embedding_dim)

        names = list(image_embeddings.keys())
        ids = np.arange(len(names), dtype=np.int64)
        embeddings = np.array(list(image_embeddings.values()), dtype=np.float32)
        index.add(ids, embeddings)

        queries = {
            "sunset": "a beautiful sunset over the ocean",
            "city": "city skyline with tall buildings",
            "nature": "nature landscape with mountains or forest",
            "food": "delicious food on a plate",
            "animal": "a cute animal or pet",
        }

        for target_name, query_text in queries.items():
            query = clip_processor.get_text_embedding(query_text)
            result_ids, scores = index.search(query, k=5)

            target_idx = names.index(target_name)
            assert result_ids[0] == target_idx, (
                f"Query '{query_text}' should find {target_name} (ID {target_idx}), "
                f"but found ID {result_ids[0]} ({names[result_ids[0]]})"
            )

    def test_save_load_with_real_embeddings(self, clip_processor, image_embeddings):
        """Test save/load preserves search accuracy with real embeddings."""
        if len(image_embeddings) < 5:
            pytest.skip("Not all test images available")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "real_images.index"

            # Create and populate index
            index = VectorIndex(dimension=clip_processor.embedding_dim)
            names = list(image_embeddings.keys())
            ids = np.arange(len(names), dtype=np.int64)
            embeddings = np.array(list(image_embeddings.values()), dtype=np.float32)
            index.add(ids, embeddings)

            # Search before save
            query = clip_processor.get_text_embedding("sunset on beach")
            original_ids, original_scores = index.search(query, k=5)

            # Save and reload
            index.save(index_path)
            loaded = VectorIndex.load(index_path)

            # Search after load
            loaded_ids, loaded_scores = loaded.search(query, k=5)

            # Results should match
            np.testing.assert_array_equal(original_ids, loaded_ids)
            np.testing.assert_array_almost_equal(original_scores, loaded_scores, decimal=5)

    def test_remove_and_search_with_real_embeddings(self, clip_processor, image_embeddings):
        """Test that removed images don't appear in search results."""
        if len(image_embeddings) < 5:
            pytest.skip("Not all test images available")

        index = VectorIndex(dimension=clip_processor.embedding_dim)

        names = list(image_embeddings.keys())
        ids = np.arange(len(names), dtype=np.int64)
        embeddings = np.array(list(image_embeddings.values()), dtype=np.float32)
        index.add(ids, embeddings)

        # Remove sunset image
        sunset_idx = names.index("sunset")
        index.remove([sunset_idx])

        # Search for sunset - should NOT return sunset anymore
        query = clip_processor.get_text_embedding("a beautiful sunset")
        result_ids, scores = index.search(query, k=5)

        assert sunset_idx not in result_ids, (
            f"Removed sunset (ID {sunset_idx}) should not appear in results"
        )
