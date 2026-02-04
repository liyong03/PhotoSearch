"""Database operations for PhotoSearch backend."""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from photosearch.models import Photo, PhotoCreate, PhotoUpdate


class Database:
    """SQLite database manager for photo metadata."""

    def __init__(self, db_path: Path | str):
        """Initialize database connection.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema_sql = f.read()

        conn = self._get_connection()
        try:
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    def _row_to_photo(self, row: sqlite3.Row) -> Photo:
        """Convert a database row to a Photo model."""
        tags = json.loads(row["tags"]) if row["tags"] else []

        # Parse timestamp if it's a string
        timestamp = row["timestamp"]
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except (ValueError, TypeError):
                timestamp = None

        indexed_at = row["indexed_at"]
        if isinstance(indexed_at, str):
            try:
                indexed_at = datetime.fromisoformat(indexed_at)
            except (ValueError, TypeError):
                indexed_at = datetime.now()

        return Photo(
            id=row["id"],
            file_path=row["file_path"],
            filename=row["filename"],
            timestamp=timestamp,
            latitude=row["latitude"],
            longitude=row["longitude"],
            city=row["city"],
            state=row["state"],
            country=row["country"],
            place_name=row["place_name"],
            description=row["description"],
            tags=tags,
            indexed_at=indexed_at,
        )

    def create_photo(self, photo: PhotoCreate) -> Photo:
        """Create a new photo record.

        Args:
            photo: Photo data to insert.

        Returns:
            The created Photo with generated id and indexed_at.
        """
        photo_id = str(uuid.uuid4())
        indexed_at = datetime.now()
        tags_json = json.dumps(photo.tags)

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO photos (
                    id, file_path, filename, timestamp,
                    latitude, longitude, city, state, country, place_name,
                    description, tags, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    photo_id,
                    photo.file_path,
                    photo.filename,
                    photo.timestamp.isoformat() if photo.timestamp else None,
                    photo.latitude,
                    photo.longitude,
                    photo.city,
                    photo.state,
                    photo.country,
                    photo.place_name,
                    photo.description,
                    tags_json,
                    indexed_at.isoformat(),
                ),
            )
            conn.commit()

            return Photo(
                id=photo_id,
                file_path=photo.file_path,
                filename=photo.filename,
                timestamp=photo.timestamp,
                latitude=photo.latitude,
                longitude=photo.longitude,
                city=photo.city,
                state=photo.state,
                country=photo.country,
                place_name=photo.place_name,
                description=photo.description,
                tags=photo.tags,
                indexed_at=indexed_at,
            )
        finally:
            conn.close()

    def get_photo(self, photo_id: str) -> Optional[Photo]:
        """Get a photo by ID.

        Args:
            photo_id: The photo's unique identifier.

        Returns:
            Photo if found, None otherwise.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM photos WHERE id = ?",
                (photo_id,),
            )
            row = cursor.fetchone()
            return self._row_to_photo(row) if row else None
        finally:
            conn.close()

    def get_photo_by_path(self, file_path: str) -> Optional[Photo]:
        """Get a photo by file path.

        Args:
            file_path: The photo's file path.

        Returns:
            Photo if found, None otherwise.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM photos WHERE file_path = ?",
                (file_path,),
            )
            row = cursor.fetchone()
            return self._row_to_photo(row) if row else None
        finally:
            conn.close()

    def update_photo(self, photo_id: str, update: PhotoUpdate) -> Optional[Photo]:
        """Update a photo record.

        Args:
            photo_id: The photo's unique identifier.
            update: Fields to update.

        Returns:
            Updated Photo if found, None otherwise.
        """
        # Build dynamic update query
        updates = []
        values = []

        update_dict = update.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if field == "tags" and value is not None:
                value = json.dumps(value)
            elif field == "timestamp" and value is not None:
                value = value.isoformat()
            updates.append(f"{field} = ?")
            values.append(value)

        if not updates:
            return self.get_photo(photo_id)

        values.append(photo_id)
        query = f"UPDATE photos SET {', '.join(updates)} WHERE id = ?"

        conn = self._get_connection()
        try:
            cursor = conn.execute(query, values)
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_photo(photo_id)
        finally:
            conn.close()

    def delete_photo(self, photo_id: str) -> bool:
        """Delete a photo record.

        Args:
            photo_id: The photo's unique identifier.

        Returns:
            True if deleted, False if not found.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM photos WHERE id = ?",
                (photo_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_photos(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "indexed_at",
        descending: bool = True,
    ) -> list[Photo]:
        """List photos with pagination.

        Args:
            limit: Maximum number of photos to return.
            offset: Number of photos to skip.
            order_by: Field to order by.
            descending: Whether to order descending.

        Returns:
            List of Photo objects.
        """
        order = "DESC" if descending else "ASC"

        # Validate order_by to prevent SQL injection
        valid_columns = {"id", "file_path", "filename", "timestamp", "indexed_at", "city", "country"}
        if order_by not in valid_columns:
            order_by = "indexed_at"

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"SELECT * FROM photos ORDER BY {order_by} {order} LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            return [self._row_to_photo(row) for row in rows]
        finally:
            conn.close()

    def count_photos(self) -> int:
        """Get total number of photos.

        Returns:
            Total photo count.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM photos")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def search_fts(self, query: str, limit: int = 100) -> list[Photo]:
        """Full-text search on photo descriptions and location fields.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching Photo objects.
        """
        conn = self._get_connection()
        try:
            # FTS5 search with ranking
            cursor = conn.execute(
                """
                SELECT photos.* FROM photos
                JOIN photos_fts ON photos.id = photos_fts.id
                WHERE photos_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_photo(row) for row in rows]
        finally:
            conn.close()

    def search_by_location(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        limit: int = 100,
    ) -> list[Photo]:
        """Search photos within a geographic bounding box.

        Args:
            min_lat: Minimum latitude.
            max_lat: Maximum latitude.
            min_lon: Minimum longitude.
            max_lon: Maximum longitude.
            limit: Maximum number of results.

        Returns:
            List of matching Photo objects.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM photos
                WHERE latitude BETWEEN ? AND ?
                AND longitude BETWEEN ? AND ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (min_lat, max_lat, min_lon, max_lon, limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_photo(row) for row in rows]
        finally:
            conn.close()

    def search_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> list[Photo]:
        """Search photos within a time range.

        Args:
            start_time: Start of time range.
            end_time: End of time range.
            limit: Maximum number of results.

        Returns:
            List of matching Photo objects.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM photos
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (start_time.isoformat(), end_time.isoformat(), limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_photo(row) for row in rows]
        finally:
            conn.close()

    def get_photos_by_ids(self, photo_ids: list[str]) -> list[Photo]:
        """Get multiple photos by their IDs.

        Args:
            photo_ids: List of photo IDs to retrieve.

        Returns:
            List of Photo objects (may be fewer than requested if some not found).
        """
        if not photo_ids:
            return []

        conn = self._get_connection()
        try:
            placeholders = ",".join("?" * len(photo_ids))
            cursor = conn.execute(
                f"SELECT * FROM photos WHERE id IN ({placeholders})",
                photo_ids,
            )
            rows = cursor.fetchall()

            # Return in same order as requested
            photo_map = {self._row_to_photo(row).id: self._row_to_photo(row) for row in rows}
            return [photo_map[pid] for pid in photo_ids if pid in photo_map]
        finally:
            conn.close()

    def get_all_file_paths(self) -> set[str]:
        """Get all indexed file paths.

        Returns:
            Set of all file paths in the database.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT file_path FROM photos")
            return {row["file_path"] for row in cursor.fetchall()}
        finally:
            conn.close()

    def save_embedding_mapping(self, photo_id: str, faiss_index: int) -> None:
        """Save the mapping between photo ID and FAISS index.

        Args:
            photo_id: The photo's unique identifier.
            faiss_index: The index position in FAISS.
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO embeddings (photo_id, faiss_index)
                VALUES (?, ?)
                """,
                (photo_id, faiss_index),
            )
            conn.commit()
        finally:
            conn.close()

    def get_embedding_mapping(self, faiss_indices: list[int]) -> dict[int, str]:
        """Get photo IDs for FAISS indices.

        Args:
            faiss_indices: List of FAISS index positions.

        Returns:
            Dict mapping FAISS index to photo ID.
        """
        if not faiss_indices:
            return {}

        conn = self._get_connection()
        try:
            placeholders = ",".join("?" * len(faiss_indices))
            cursor = conn.execute(
                f"SELECT photo_id, faiss_index FROM embeddings WHERE faiss_index IN ({placeholders})",
                faiss_indices,
            )
            return {row["faiss_index"]: row["photo_id"] for row in cursor.fetchall()}
        finally:
            conn.close()

    def save_caption_embedding(self, photo_id: str, embedding: "np.ndarray") -> None:
        """Save caption embedding for a photo.

        Args:
            photo_id: The photo's unique identifier.
            embedding: Numpy array of the caption embedding.
        """
        import numpy as np

        conn = self._get_connection()
        try:
            # Convert numpy array to bytes
            embedding_bytes = embedding.astype(np.float32).tobytes()
            conn.execute(
                """
                INSERT OR REPLACE INTO caption_embeddings (photo_id, embedding)
                VALUES (?, ?)
                """,
                (photo_id, embedding_bytes),
            )
            conn.commit()
        finally:
            conn.close()

    def get_caption_embedding(self, photo_id: str) -> Optional["np.ndarray"]:
        """Get caption embedding for a photo.

        Args:
            photo_id: The photo's unique identifier.

        Returns:
            Numpy array of the caption embedding, or None if not found.
        """
        import numpy as np

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT embedding FROM caption_embeddings WHERE photo_id = ?",
                (photo_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            # Convert bytes back to numpy array
            return np.frombuffer(row["embedding"], dtype=np.float32)
        finally:
            conn.close()

    def get_caption_embeddings_batch(self, photo_ids: list[str]) -> dict[str, "np.ndarray"]:
        """Get caption embeddings for multiple photos.

        Args:
            photo_ids: List of photo IDs.

        Returns:
            Dict mapping photo_id to embedding numpy array.
        """
        import numpy as np

        if not photo_ids:
            return {}

        conn = self._get_connection()
        try:
            placeholders = ",".join("?" * len(photo_ids))
            cursor = conn.execute(
                f"SELECT photo_id, embedding FROM caption_embeddings WHERE photo_id IN ({placeholders})",
                photo_ids,
            )
            return {
                row["photo_id"]: np.frombuffer(row["embedding"], dtype=np.float32)
                for row in cursor.fetchall()
            }
        finally:
            conn.close()

    def close(self) -> None:
        """Close the database connection.

        Note: This class uses per-operation connections, so this method
        is a no-op but provided for API consistency.
        """
        pass
