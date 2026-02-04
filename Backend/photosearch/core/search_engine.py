"""Search engine integrating CLIP, FAISS, and filters for photo search."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from photosearch.core.caption_generator import CaptionGenerator
from photosearch.core.clip_processor import CLIPProcessor
from photosearch.core.location_service import LocationService, PlaceInfo
from photosearch.core.query_parser import QueryParser
from photosearch.core.vector_index import VectorIndex
from photosearch.database.db import Database
from photosearch.models import PhotoCreate
from photosearch.utils.exif import extract_metadata
from photosearch.utils.image import load_image, scan_folder_for_images

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result."""

    id: str
    path: str
    score: float
    description: Optional[str] = None
    timestamp: Optional[datetime] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "path": self.path,
            "score": self.score,
            "description": self.description,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "city": self.city,
            "state": self.state,
            "country": self.country,
        }


@dataclass
class SearchResponse:
    """Response from a search query."""

    results: list[SearchResult]
    total_results: int
    location_resolved: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "results": [r.to_dict() for r in self.results],
            "total_results": self.total_results,
            "location_resolved": self.location_resolved,
        }


@dataclass
class IndexResult:
    """Result of indexing a single photo."""

    id: str
    path: str
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    location: Optional[PlaceInfo] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "path": self.path,
            "description": self.description,
            "tags": self.tags,
            "location": self.location.to_dict() if self.location else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class IndexProgress:
    """Progress of batch indexing."""

    task_id: str
    status: str  # "running", "completed", "failed"
    progress: float  # 0.0 to 1.0
    processed: int
    total: int
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "processed": self.processed,
            "total": self.total,
            "errors": self.errors,
        }


class SearchEngine:
    """Main search engine combining all components.

    Provides:
    - Photo indexing (single and batch)
    - Semantic search with CLIP embeddings
    - Location filtering with geocoding
    - Time range filtering
    - Query parsing for natural language queries
    """

    def __init__(
        self,
        db_path: Path | str,
        index_path: Path | str,
        device: Optional[str] = None,
        local_files_only: bool = False,
    ):
        """Initialize search engine.

        Args:
            db_path: Path to SQLite database.
            index_path: Path to FAISS index file.
            device: Device for ML models ("cpu", "cuda", "mps").
            local_files_only: If True, only use cached ML models (no network).
        """
        self.db_path = Path(db_path)
        self.index_path = Path(index_path)

        # Ensure directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize components
        logger.info("Initializing search engine components...")

        self.db = Database(self.db_path)
        self.clip = CLIPProcessor(device=device, local_files_only=local_files_only)
        self.caption_generator = CaptionGenerator(device=device, local_files_only=local_files_only)
        self.location_service = LocationService()
        self.query_parser = QueryParser()

        # Load or create vector index
        if self.index_path.exists():
            self.vector_index = VectorIndex.load(
                self.index_path, dimension=self.clip.embedding_dim
            )
            logger.info(f"Loaded existing index with {self.vector_index.size} vectors")
        else:
            self.vector_index = VectorIndex(dimension=self.clip.embedding_dim)
            logger.info("Created new vector index")

        # Track indexing tasks
        self._indexing_tasks: dict[str, IndexProgress] = {}

        logger.info("Search engine initialized")

    def _photo_id_to_vector_id(self, photo_id: str) -> int:
        """Convert photo UUID to vector index ID."""
        return hash(photo_id) & 0x7FFFFFFF

    def index_photo(self, photo_path: Path | str) -> Optional[IndexResult]:
        """Index a single photo.

        Extracts metadata, generates caption and embedding, stores in database and index.

        Args:
            photo_path: Path to the photo file.

        Returns:
            IndexResult with photo information, or None if indexing failed.
        """
        photo_path = Path(photo_path)

        if not photo_path.exists():
            logger.warning(f"Photo not found: {photo_path}")
            return None

        # Check if already indexed
        existing = self.db.get_photo_by_path(str(photo_path.absolute()))
        if existing:
            logger.debug(f"Photo already indexed: {photo_path}")
            return IndexResult(
                id=existing.id,
                path=existing.file_path,
                description=existing.description,
                tags=existing.tags,
                location=PlaceInfo(
                    city=existing.city,
                    state=existing.state,
                    country=existing.country,
                    place_name=existing.place_name,
                ) if existing.city or existing.country else None,
                timestamp=existing.timestamp,
            )

        try:
            # Load image
            image = load_image(photo_path)
            if image is None:
                logger.warning(f"Could not load image: {photo_path}")
                return None

            # Extract EXIF metadata
            exif_data = extract_metadata(photo_path)

            # Generate caption and tags
            caption, tags = self.caption_generator.generate_caption_with_tags(image)

            # Generate CLIP embedding for image
            embedding = self.clip.get_image_embedding(image)

            # Generate CLIP embedding for caption (for semantic matching during search)
            caption_embedding = self.clip.get_text_embedding(caption) if caption else None

            # Reverse geocode if GPS available
            location = None
            if exif_data.latitude is not None and exif_data.longitude is not None:
                location = self.location_service.reverse_geocode(
                    exif_data.latitude, exif_data.longitude
                )

            # Create photo record
            photo_create = PhotoCreate(
                file_path=str(photo_path.absolute()),
                filename=photo_path.name,
                timestamp=exif_data.timestamp,
                latitude=exif_data.latitude,
                longitude=exif_data.longitude,
                city=location.city if location else None,
                state=location.state if location else None,
                country=location.country if location else None,
                place_name=location.place_name if location else None,
                description=caption,
                tags=tags,
            )

            # Store in database
            photo = self.db.create_photo(photo_create)

            # Add to vector index
            vector_id = self._photo_id_to_vector_id(photo.id)
            self.vector_index.add_single(id=vector_id, embedding=embedding)

            # Store ID mapping
            self.db.save_embedding_mapping(photo.id, vector_id)

            # Store caption embedding for semantic search
            if caption_embedding is not None:
                self.db.save_caption_embedding(photo.id, caption_embedding)

            logger.info(f"Indexed photo: {photo_path}")

            return IndexResult(
                id=photo.id,
                path=str(photo_path),
                description=caption,
                tags=tags,
                location=location,
                timestamp=exif_data.timestamp,
            )

        except Exception as e:
            logger.error(f"Failed to index {photo_path}: {e}")
            return None

    def index_folder(
        self,
        folder_path: Path | str,
        recursive: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> IndexProgress:
        """Index all photos in a folder.

        Args:
            folder_path: Path to the folder.
            recursive: Whether to scan subdirectories.
            progress_callback: Optional callback for progress updates.

        Returns:
            IndexProgress with final status.
        """
        folder_path = Path(folder_path)
        task_id = str(uuid.uuid4())

        # Scan for images
        image_paths = scan_folder_for_images(folder_path, recursive=recursive)
        total = len(image_paths)

        progress = IndexProgress(
            task_id=task_id,
            status="running",
            progress=0.0,
            processed=0,
            total=total,
        )
        self._indexing_tasks[task_id] = progress

        logger.info(f"Starting batch indexing: {total} images in {folder_path}")

        for i, image_path in enumerate(image_paths):
            try:
                result = self.index_photo(image_path)
                if result is None:
                    progress.errors.append(f"Failed to index: {image_path}")
            except Exception as e:
                progress.errors.append(f"{image_path}: {e}")
                logger.error(f"Error indexing {image_path}: {e}")

            progress.processed = i + 1
            progress.progress = (i + 1) / total if total > 0 else 1.0

            if progress_callback:
                progress_callback(progress)

            # Save index periodically
            if (i + 1) % 100 == 0:
                self._save_index()

        # Final save
        self._save_index()

        progress.status = "completed"
        logger.info(f"Batch indexing complete: {progress.processed}/{total} photos")

        return progress

    def get_indexing_progress(self, task_id: str) -> Optional[IndexProgress]:
        """Get progress of an indexing task.

        Args:
            task_id: Task ID from index_folder.

        Returns:
            IndexProgress or None if task not found.
        """
        return self._indexing_tasks.get(task_id)

    def _check_lexical_match(self, query: str, description: str, tags: list[str]) -> bool:
        """Check if query terms appear in description or tags.

        Uses WordNet + manual synonyms for comprehensive expansion.
        Query terms are expanded, then we check if any expanded term appears in the document.

        Args:
            query: Search query.
            description: Photo description/caption.
            tags: Photo tags.

        Returns:
            True if any query term (or its synonym) matches document content.
        """
        from photosearch.core.synonym_service import check_match

        return check_match(query, description, tags)

    def search(
        self,
        query: str,
        top_k: int = 20,
        time_range: Optional[tuple[datetime, datetime]] = None,
        location: Optional[str] = None,
        min_score: float = 0.15,
        caption_weight: float = 0.5,
    ) -> SearchResponse:
        """Search for photos using lexical matching + image similarity ranking.

        Uses a two-stage approach:
        1. Lexical filtering: Only include photos where caption/tags contain query terms
        2. Ranking: Use CLIP image-query similarity for final ranking

        This ensures precision (only relevant photos) while using CLIP for ranking.

        Args:
            query: Search query (can include location phrases).
            top_k: Maximum number of results to return.
            time_range: Optional (start, end) datetime tuple.
            location: Optional explicit location filter.
            min_score: Minimum image similarity score threshold (0.0-1.0).
            caption_weight: Not used in current implementation (kept for API compatibility).

        Returns:
            SearchResponse with results.
        """
        # Parse query for embedded location
        parsed = self.query_parser.parse(query)
        semantic_query = parsed.semantic_query
        query_location = location or parsed.location

        logger.info(f"Search: semantic='{semantic_query}', location='{query_location}'")

        # Resolve location to bounding box
        location_resolved = None
        bbox = None
        if query_location:
            geocode_result = self.location_service.geocode(query_location)
            if geocode_result:
                bbox = geocode_result.bounding_box
                location_resolved = geocode_result.to_dict()
                logger.debug(f"Resolved location '{query_location}' to bbox: {bbox}")

        # Generate query embedding for image similarity
        query_embedding = self.clip.get_text_embedding(semantic_query)

        # Search vector index (get more candidates for filtering)
        search_k = top_k * 10  # Get many candidates since we'll filter heavily
        vector_ids, image_scores = self.vector_index.search(query_embedding, k=search_k)

        # Get photo IDs from vector IDs
        vector_id_list = [int(vid) for vid in vector_ids]
        id_mapping = self.db.get_embedding_mapping(vector_id_list)

        # Get photo records, apply lexical filter, and rank by image similarity
        candidates = []

        for vector_id, image_score in zip(vector_ids, image_scores):
            photo_id = id_mapping.get(int(vector_id))
            if photo_id is None:
                continue

            photo = self.db.get_photo(photo_id)
            if photo is None:
                continue

            # Apply time filter
            if time_range:
                if photo.timestamp is None:
                    continue
                start, end = time_range
                if not (start <= photo.timestamp <= end):
                    continue

            # Apply location filter
            if bbox:
                if photo.latitude is None or photo.longitude is None:
                    continue
                if not bbox.contains(photo.latitude, photo.longitude):
                    continue

            # KEY FILTER: Lexical match required
            # Caption/tags must contain query terms (or synonyms)
            has_lexical_match = self._check_lexical_match(
                semantic_query,
                photo.description,
                photo.tags
            )

            if not has_lexical_match:
                logger.debug(
                    f"Filtered {photo_id}: no lexical match for '{semantic_query}' "
                    f"in desc='{photo.description[:50] if photo.description else None}...'"
                )
                continue

            # Use image similarity for ranking
            final_score = float(image_score)

            candidates.append((photo, final_score))

            logger.debug(
                f"Candidate {photo_id}: score={final_score:.3f} "
                f"desc='{photo.description[:50] if photo.description else None}...'"
            )

        # Sort by score (image similarity)
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Take top_k results
        results = []
        for photo, score in candidates[:top_k]:
            results.append(SearchResult(
                id=photo.id,
                path=photo.file_path,
                score=score,
                description=photo.description,
                timestamp=photo.timestamp,
                city=photo.city,
                state=photo.state,
                country=photo.country,
            ))

        logger.info(f"Search returned {len(results)} results (from {len(candidates)} lexical matches)")

        return SearchResponse(
            results=results,
            total_results=len(results),
            location_resolved=location_resolved,
        )

    def remove_photo(self, photo_id: str) -> bool:
        """Remove a photo from the index.

        Args:
            photo_id: ID of the photo to remove.

        Returns:
            True if removed, False if not found.
        """
        photo = self.db.get_photo(photo_id)
        if photo is None:
            return False

        # Remove from vector index
        vector_id = self._photo_id_to_vector_id(photo_id)
        self.vector_index.remove([vector_id])

        # Remove from database
        self.db.delete_photo(photo_id)

        logger.info(f"Removed photo: {photo_id}")
        return True

    def remove_folder(self, folder_path: Path | str) -> int:
        """Remove all photos in a folder from the index.

        Args:
            folder_path: Path to the folder to remove.

        Returns:
            Number of photos removed.
        """
        folder_path = str(Path(folder_path).absolute())

        # Get all photos in the folder
        photos = self.db.get_photos_by_folder(folder_path)

        if not photos:
            logger.info(f"No photos found in folder: {folder_path}")
            return 0

        # Remove from vector index
        vector_ids = [self._photo_id_to_vector_id(photo.id) for photo in photos]
        self.vector_index.remove(vector_ids)

        # Remove from database
        count = self.db.delete_photos_by_folder(folder_path)

        # Save the updated index
        self._save_index()

        logger.info(f"Removed {count} photos from folder: {folder_path}")
        return count

    def get_status(self) -> dict:
        """Get search engine status.

        Returns:
            Dictionary with status information.
        """
        return {
            "status": "ready",
            "indexed_count": self.db.count_photos(),
            "vector_index_size": self.vector_index.size,
            "location_cache": self.location_service.cache_info(),
        }

    def _save_index(self) -> None:
        """Save vector index to disk."""
        self.vector_index.save(self.index_path)
        logger.debug(f"Saved vector index to {self.index_path}")

    def close(self) -> None:
        """Close the search engine and save state."""
        self._save_index()
        logger.info("Search engine closed")

    def reload_index(self) -> None:
        """Reload the vector index from disk.

        This should be called after external processes (like background indexing)
        have modified the index file, to ensure the in-memory state is up to date.
        """
        logger.info("Reloading vector index from disk...")
        self.vector_index.reload_from(self.index_path)
        logger.info(f"Reloaded vector index with {self.vector_index.size} vectors")
