"""Pydantic models for PhotoSearch backend."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LocationInfo(BaseModel):
    """Location information for a photo."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    place_name: Optional[str] = None


class PhotoBase(BaseModel):
    """Base photo model with common fields."""

    file_path: str
    filename: str
    timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    place_name: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class PhotoCreate(PhotoBase):
    """Model for creating a new photo record."""

    pass


class PhotoUpdate(BaseModel):
    """Model for updating a photo record. All fields optional."""

    file_path: Optional[str] = None
    filename: Optional[str] = None
    timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    place_name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class Photo(PhotoBase):
    """Complete photo model with all fields."""

    model_config = {"from_attributes": True}

    id: str
    indexed_at: datetime


class PhotoInDB(Photo):
    """Photo model as stored in database (with tags as JSON string)."""

    tags: str  # JSON string in database

    def to_photo(self) -> Photo:
        """Convert to Photo model with parsed tags."""
        import json

        tags_list = json.loads(self.tags) if self.tags else []
        return Photo(
            id=self.id,
            file_path=self.file_path,
            filename=self.filename,
            timestamp=self.timestamp,
            latitude=self.latitude,
            longitude=self.longitude,
            city=self.city,
            state=self.state,
            country=self.country,
            place_name=self.place_name,
            description=self.description,
            tags=tags_list,
            indexed_at=self.indexed_at,
        )


class SearchResult(BaseModel):
    """Search result model."""

    id: str
    file_path: str
    filename: str
    score: float
    description: Optional[str] = None
    timestamp: Optional[datetime] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    place_name: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class BoundingBox(BaseModel):
    """Geographic bounding box."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        """Check if a point is within the bounding box."""
        return (
            self.min_lat <= lat <= self.max_lat
            and self.min_lon <= lon <= self.max_lon
        )


class IndexProgress(BaseModel):
    """Indexing progress information."""

    task_id: str
    status: str  # "pending", "running", "completed", "failed"
    progress: float  # 0.0 to 1.0
    processed: int
    total: int
    current_file: Optional[str] = None
    error: Optional[str] = None
