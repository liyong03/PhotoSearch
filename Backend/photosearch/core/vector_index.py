"""FAISS-based vector index for similarity search."""

import logging
import os
from pathlib import Path
from typing import Optional

# Fix OpenMP conflict between torch and faiss on macOS
# Must be set before importing faiss
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import faiss
import numpy as np

logger = logging.getLogger(__name__)


class VectorIndex:
    """FAISS vector index for efficient similarity search.

    Uses IndexFlatIP (inner product) for exact search with manual ID mapping.
    For normalized vectors, inner product equals cosine similarity.
    """

    def __init__(self, dimension: int = 512):
        """Initialize vector index.

        Args:
            dimension: Dimension of embeddings (512 for CLIP base model).
        """
        self.dimension = dimension

        # Create inner product index (for normalized vectors = cosine similarity)
        self.index = faiss.IndexFlatIP(dimension)

        # Manual ID mapping: user ID -> position in index
        self._id_to_pos: dict[int, int] = {}
        self._pos_to_id: dict[int, int] = {}

        logger.info(f"Created vector index with dimension {dimension}")

    @property
    def size(self) -> int:
        """Get number of vectors in the index."""
        return self.index.ntotal

    @property
    def active_count(self) -> int:
        """Get number of active (non-deleted) vectors."""
        return len(self._id_to_pos)

    def add(self, ids: np.ndarray, embeddings: np.ndarray) -> None:
        """Add embeddings to the index.

        Args:
            ids: Array of unique integer IDs, shape (n,).
            embeddings: Normalized embeddings, shape (n, dimension).

        Raises:
            ValueError: If shapes don't match or embeddings not normalized.
        """
        if len(ids) != len(embeddings):
            raise ValueError(
                f"IDs length ({len(ids)}) must match embeddings length ({len(embeddings)})"
            )

        if len(embeddings) == 0:
            return

        if embeddings.shape[1] != self.dimension:
            raise ValueError(
                f"Embedding dimension ({embeddings.shape[1]}) must be {self.dimension}"
            )

        # Ensure correct types - must be float32 and C-contiguous for FAISS
        embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)

        # Filter out existing IDs
        new_indices = []
        for i, user_id in enumerate(ids):
            user_id = int(user_id)
            if user_id not in self._id_to_pos:
                new_indices.append(i)

        if not new_indices:
            return

        # Get embeddings to add
        embeddings_to_add = embeddings[new_indices]

        # Add all at once for efficiency
        start_pos = self.index.ntotal
        self.index.add(embeddings_to_add)

        # Update ID mappings
        for i, idx in enumerate(new_indices):
            user_id = int(ids[idx])
            pos = start_pos + i
            self._id_to_pos[user_id] = pos
            self._pos_to_id[pos] = user_id

        logger.debug(f"Added {len(new_indices)} embeddings to index (total: {self.size})")

    def add_single(self, id: int, embedding: np.ndarray) -> None:
        """Add a single embedding to the index.

        Args:
            id: Unique integer ID.
            embedding: Normalized embedding, shape (dimension,).
        """
        ids = np.array([id], dtype=np.int64)
        embeddings = embedding.reshape(1, -1).astype(np.float32)
        self.add(ids, embeddings)

    def remove(self, ids: np.ndarray | list[int]) -> int:
        """Mark embeddings as removed (they won't appear in search results).

        Note: This is a soft delete. The vectors remain in the index but are
        excluded from search results. For true deletion, rebuild the index.

        Args:
            ids: Array or list of IDs to remove.

        Returns:
            Number of embeddings actually removed.
        """
        removed = 0
        for user_id in ids:
            user_id = int(user_id)
            if user_id in self._id_to_pos:
                pos = self._id_to_pos[user_id]
                del self._id_to_pos[user_id]
                del self._pos_to_id[pos]
                removed += 1

        logger.debug(f"Soft-removed {removed} embeddings from index")
        return removed

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 10,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Search for similar embeddings.

        Args:
            query_embedding: Normalized query embedding, shape (dimension,).
            k: Number of results to return.

        Returns:
            Tuple of (ids, scores) where:
                - ids: Array of user IDs, shape (<=k,)
                - scores: Similarity scores, shape (<=k,)
                  Higher is more similar (cosine similarity).
        """
        if self.size == 0 or len(self._id_to_pos) == 0:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

        # Ensure correct shape and type - must be float32 and C-contiguous
        query = np.ascontiguousarray(
            np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
        )

        # Search for more than k to account for soft-deleted entries
        search_k = min(k * 2 + 10, self.index.ntotal)

        # Search
        scores, positions = self.index.search(query, search_k)

        # Flatten results
        scores = scores[0]
        positions = positions[0]

        # Filter to valid IDs (not soft-deleted) and convert to user IDs
        valid_ids = []
        valid_scores = []
        for pos, score in zip(positions, scores):
            pos = int(pos)
            if pos >= 0 and pos in self._pos_to_id:
                valid_ids.append(self._pos_to_id[pos])
                valid_scores.append(float(score))
                if len(valid_ids) >= k:
                    break

        return np.array(valid_ids, dtype=np.int64), np.array(valid_scores, dtype=np.float32)

    def search_batch(
        self,
        query_embeddings: np.ndarray,
        k: int = 10,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Search for similar embeddings for multiple queries.

        Args:
            query_embeddings: Normalized query embeddings, shape (n_queries, dimension).
            k: Number of results to return per query.

        Returns:
            Tuple of (ids, scores) where:
                - ids: Array of user IDs, shape (n_queries, k)
                - scores: Similarity scores, shape (n_queries, k)
        """
        n_queries = len(query_embeddings)

        if self.size == 0 or len(self._id_to_pos) == 0:
            return (
                np.full((n_queries, k), -1, dtype=np.int64),
                np.zeros((n_queries, k), dtype=np.float32),
            )

        # Use single search for each query to avoid FAISS batch issues on macOS
        result_ids = np.full((n_queries, k), -1, dtype=np.int64)
        result_scores = np.zeros((n_queries, k), dtype=np.float32)

        for q_idx in range(n_queries):
            ids, scores = self.search(query_embeddings[q_idx], k=k)
            result_ids[q_idx, :len(ids)] = ids
            result_scores[q_idx, :len(scores)] = scores

        return result_ids, result_scores

    def save(self, path: Path | str) -> None:
        """Save index to file.

        Args:
            path: Path to save the index.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        faiss.write_index(self.index, str(path))

        # Save ID mapping
        mapping_path = path.with_suffix('.mapping.npz')
        np.savez(
            mapping_path,
            id_to_pos_keys=np.array(list(self._id_to_pos.keys()), dtype=np.int64),
            id_to_pos_values=np.array(list(self._id_to_pos.values()), dtype=np.int64),
        )

        logger.info(f"Saved index with {self.size} vectors to {path}")

    @classmethod
    def load(cls, path: Path | str, dimension: int = 512) -> "VectorIndex":
        """Load index from file.

        Args:
            path: Path to the saved index.
            dimension: Expected dimension (for validation).

        Returns:
            Loaded VectorIndex instance.

        Raises:
            FileNotFoundError: If index file doesn't exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Index file not found: {path}")

        instance = cls.__new__(cls)
        instance.dimension = dimension
        instance.index = faiss.read_index(str(path))

        # Load ID mapping
        mapping_path = path.with_suffix('.mapping.npz')
        if mapping_path.exists():
            data = np.load(mapping_path)
            keys = data['id_to_pos_keys']
            values = data['id_to_pos_values']
            instance._id_to_pos = dict(zip(keys.tolist(), values.tolist()))
            instance._pos_to_id = {v: k for k, v in instance._id_to_pos.items()}
        else:
            # Assume sequential IDs if no mapping file
            instance._id_to_pos = {i: i for i in range(instance.index.ntotal)}
            instance._pos_to_id = dict(instance._id_to_pos)

        logger.info(f"Loaded index with {instance.size} vectors from {path}")
        return instance

    def has_id(self, id: int) -> bool:
        """Check if an ID exists in the index.

        Args:
            id: ID to check.

        Returns:
            True if ID exists in index.
        """
        return int(id) in self._id_to_pos

    def get_embedding(self, id: int) -> Optional[np.ndarray]:
        """Get embedding by ID.

        Args:
            id: ID of the embedding.

        Returns:
            Embedding array or None if not found.
        """
        user_id = int(id)
        if user_id not in self._id_to_pos:
            return None

        pos = self._id_to_pos[user_id]
        embedding = self.index.reconstruct(pos)
        return embedding

    def clear(self) -> None:
        """Remove all embeddings from the index."""
        self.index.reset()
        self._id_to_pos.clear()
        self._pos_to_id.clear()
        logger.info("Cleared all embeddings from index")

    def rebuild(self) -> "VectorIndex":
        """Rebuild index to reclaim space from soft-deleted entries.

        Returns:
            New VectorIndex with only active entries.
        """
        new_index = VectorIndex(self.dimension)

        if len(self._id_to_pos) == 0:
            return new_index

        # Get all active embeddings
        ids = []
        embeddings = []
        for user_id, pos in sorted(self._id_to_pos.items()):
            ids.append(user_id)
            embeddings.append(self.index.reconstruct(pos))

        # Add to new index
        new_index.add(
            np.array(ids, dtype=np.int64),
            np.array(embeddings, dtype=np.float32),
        )

        return new_index
