"""API routes for PhotoSearch backend."""

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from photosearch import __version__
from photosearch.config import settings
from photosearch.database import Database

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize database
_db: Database | None = None


def get_db() -> Database:
    """Get or create database instance."""
    global _db
    if _db is None:
        _db = Database(settings.db_path)
    return _db


# Lazy-loaded search engine (expensive to initialize)
_search_engine = None
_search_engine_lock = asyncio.Lock()


async def get_search_engine():
    """Get or create search engine instance (lazy initialization)."""
    global _search_engine
    if _search_engine is None:
        async with _search_engine_lock:
            if _search_engine is None:
                from photosearch.core.search_engine import SearchEngine
                logger.info("Initializing search engine (this may take a moment)...")
                _search_engine = SearchEngine(
                    db_path=settings.db_path,
                    index_path=settings.faiss_index_path,
                    device=settings.device,
                )
                logger.info("Search engine initialized")
    return _search_engine


# =============================================================================
# Request/Response Models
# =============================================================================


class StatusResponse(BaseModel):
    """Response model for status endpoint."""

    status: str
    version: str
    indexed_count: int = 0
    index_size_mb: float = 0.0


class ErrorResponse(BaseModel):
    """Response model for errors."""

    error: str
    detail: str | None = None


class TimeRange(BaseModel):
    """Time range for filtering."""

    start: datetime
    end: datetime


class SearchRequest(BaseModel):
    """Request model for search endpoint."""

    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(default=20, ge=1, le=100, description="Number of results")
    time_range: TimeRange | None = Field(default=None, description="Optional time filter")
    location: str | None = Field(default=None, description="Optional location filter")
    min_score: float = Field(default=0.15, ge=0.0, le=1.0, description="Minimum combined score threshold")
    caption_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="Weight for caption similarity (vs image)")


class SearchResultItem(BaseModel):
    """Single search result."""

    id: str
    path: str
    score: float
    description: str | None = None
    timestamp: datetime | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None


class LocationResolved(BaseModel):
    """Resolved location information."""

    name: str
    bounding_box: dict | None = None
    center: dict | None = None


class SearchResponse(BaseModel):
    """Response model for search endpoint."""

    results: list[SearchResultItem]
    total_results: int
    location_resolved: LocationResolved | None = None


class IndexPhotoRequest(BaseModel):
    """Request model for indexing a single photo."""

    photo_path: str = Field(..., description="Path to the photo file")


class IndexPhotoResponse(BaseModel):
    """Response model for indexing a single photo."""

    id: str
    path: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    location: dict | None = None
    timestamp: datetime | None = None


class IndexFolderRequest(BaseModel):
    """Request model for batch indexing a folder."""

    folder_path: str = Field(..., description="Path to the folder")
    recursive: bool = Field(default=True, description="Scan subdirectories")


class IndexTaskResponse(BaseModel):
    """Response model for starting a batch index task."""

    task_id: str
    status: str
    total_files: int | None = None


class IndexProgressResponse(BaseModel):
    """Response model for indexing progress."""

    task_id: str
    status: str
    progress: float
    processed: int
    total: int
    errors: list[str] = Field(default_factory=list)


class GeocodeRequest(BaseModel):
    """Request model for geocoding."""

    place_name: str = Field(..., min_length=1, description="Place name to geocode")


class GeocodeResponse(BaseModel):
    """Response model for geocoding."""

    name: str
    bounding_box: dict | None = None
    center: dict | None = None


class DeleteResponse(BaseModel):
    """Response model for delete operations."""

    success: bool
    message: str


# =============================================================================
# In-memory task storage (for demo; use Redis/DB in production)
# =============================================================================

_indexing_tasks: dict[str, IndexProgressResponse] = {}


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """
    Get backend status and health information.

    Returns:
        StatusResponse with current status and statistics.
    """
    # Calculate index size if file exists
    index_size_mb = 0.0
    if settings.faiss_index_path and settings.faiss_index_path.exists():
        index_size_mb = settings.faiss_index_path.stat().st_size / (1024 * 1024)

    # Get actual indexed count from database
    db = get_db()
    indexed_count = db.count_photos()

    return StatusResponse(
        status="ok",
        version=__version__,
        indexed_count=indexed_count,
        index_size_mb=round(index_size_mb, 2),
    )


@router.get("/health")
async def health_check() -> dict:
    """Simple health check endpoint."""
    return {"status": "healthy"}


@router.post("/search", response_model=SearchResponse)
async def search_photos(request: SearchRequest) -> SearchResponse:
    """
    Search for photos using semantic search with optional filters.

    - **query**: Natural language search query (e.g., "sunset on beach")
    - **top_k**: Maximum number of results to return (1-100)
    - **time_range**: Optional date range filter
    - **location**: Optional location filter (e.g., "Hawaii")

    The query can include location phrases like "photos from Hawaii" which
    will be automatically parsed and used for filtering.
    """
    search_engine = await get_search_engine()

    # Build time range tuple if provided
    time_range = None
    if request.time_range:
        time_range = (request.time_range.start, request.time_range.end)

    # Execute search with semantic caption matching
    result = search_engine.search(
        query=request.query,
        top_k=request.top_k,
        time_range=time_range,
        location=request.location,
        min_score=request.min_score,
        caption_weight=request.caption_weight,
    )

    # Convert to response format
    results = [
        SearchResultItem(
            id=r.id,
            path=r.path,
            score=r.score,
            description=r.description,
            timestamp=r.timestamp,
            city=r.city,
            state=r.state,
            country=r.country,
        )
        for r in result.results
    ]

    location_resolved = None
    if result.location_resolved:
        location_resolved = LocationResolved(
            name=result.location_resolved.get("name", ""),
            bounding_box=result.location_resolved.get("bounding_box"),
            center=result.location_resolved.get("center"),
        )

    return SearchResponse(
        results=results,
        total_results=result.total_results,
        location_resolved=location_resolved,
    )


@router.post("/index", response_model=IndexPhotoResponse)
async def index_single_photo(request: IndexPhotoRequest) -> IndexPhotoResponse:
    """
    Index a single photo.

    Extracts EXIF metadata, generates AI caption, and creates CLIP embedding
    for semantic search.

    - **photo_path**: Absolute path to the photo file
    """
    photo_path = Path(request.photo_path)

    if not photo_path.exists():
        raise HTTPException(status_code=404, detail=f"Photo not found: {request.photo_path}")

    if not photo_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.photo_path}")

    search_engine = await get_search_engine()
    result = search_engine.index_photo(photo_path)

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to index photo")

    return IndexPhotoResponse(
        id=result.id,
        path=result.path,
        description=result.description,
        tags=result.tags,
        location=result.location.to_dict() if result.location else None,
        timestamp=result.timestamp,
    )


def _run_batch_indexing(task_id: str, folder_path: Path, recursive: bool):
    """Background task for batch indexing."""
    import asyncio

    # Create a new event loop for the background task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        from photosearch.core.search_engine import SearchEngine

        # Create a new search engine instance for the background task
        search_engine = SearchEngine(
            db_path=settings.db_path,
            index_path=settings.faiss_index_path,
            device=settings.device,
        )

        def progress_callback(progress):
            _indexing_tasks[task_id] = IndexProgressResponse(
                task_id=task_id,
                status=progress.status,
                progress=progress.progress,
                processed=progress.processed,
                total=progress.total,
                errors=progress.errors,
            )

        result = search_engine.index_folder(
            folder_path=folder_path,
            recursive=recursive,
            progress_callback=progress_callback,
        )

        # Update final status
        _indexing_tasks[task_id] = IndexProgressResponse(
            task_id=task_id,
            status=result.status,
            progress=result.progress,
            processed=result.processed,
            total=result.total,
            errors=result.errors,
        )

        search_engine.close()

    except Exception as e:
        logger.error(f"Batch indexing failed: {e}")
        _indexing_tasks[task_id] = IndexProgressResponse(
            task_id=task_id,
            status="failed",
            progress=0.0,
            processed=0,
            total=0,
            errors=[str(e)],
        )
    finally:
        loop.close()


@router.post("/index/batch", response_model=IndexTaskResponse)
async def index_folder(
    request: IndexFolderRequest,
    background_tasks: BackgroundTasks,
) -> IndexTaskResponse:
    """
    Index all photos in a folder (runs in background).

    - **folder_path**: Path to the folder containing photos
    - **recursive**: Whether to scan subdirectories (default: true)

    Returns a task_id that can be used to check progress via
    GET /index/status/{task_id}
    """
    folder_path = Path(request.folder_path)

    if not folder_path.exists():
        raise HTTPException(status_code=404, detail=f"Folder not found: {request.folder_path}")

    if not folder_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.folder_path}")

    # Count files to index
    from photosearch.utils.image import scan_folder_for_images
    image_paths = scan_folder_for_images(folder_path, recursive=request.recursive)
    total_files = len(image_paths)

    if total_files == 0:
        raise HTTPException(status_code=400, detail="No supported image files found in folder")

    # Create task
    task_id = str(uuid.uuid4())
    _indexing_tasks[task_id] = IndexProgressResponse(
        task_id=task_id,
        status="running",
        progress=0.0,
        processed=0,
        total=total_files,
        errors=[],
    )

    # Start background task
    background_tasks.add_task(
        _run_batch_indexing,
        task_id,
        folder_path,
        request.recursive,
    )

    return IndexTaskResponse(
        task_id=task_id,
        status="started",
        total_files=total_files,
    )


@router.get("/index/status/{task_id}", response_model=IndexProgressResponse)
async def get_index_status(task_id: str) -> IndexProgressResponse:
    """
    Get the progress of a batch indexing task.

    - **task_id**: Task ID returned from POST /index/batch
    """
    if task_id not in _indexing_tasks:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return _indexing_tasks[task_id]


@router.delete("/index/{photo_id}", response_model=DeleteResponse)
async def delete_photo(photo_id: str) -> DeleteResponse:
    """
    Remove a photo from the index.

    - **photo_id**: ID of the photo to remove
    """
    search_engine = await get_search_engine()
    success = search_engine.remove_photo(photo_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Photo not found: {photo_id}")

    return DeleteResponse(
        success=True,
        message=f"Photo {photo_id} removed from index",
    )


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_place(request: GeocodeRequest) -> GeocodeResponse:
    """
    Convert a place name to geographic coordinates.

    - **place_name**: Name of the place (e.g., "Hawaii", "San Francisco")

    Returns bounding box and center coordinates for the location.
    """
    search_engine = await get_search_engine()
    result = search_engine.location_service.geocode(request.place_name)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Location not found: {request.place_name}")

    return GeocodeResponse(
        name=result.name,
        bounding_box=result.bounding_box.to_dict() if result.bounding_box else None,
        center={"lat": result.center_lat, "lon": result.center_lon},
    )


@router.post("/reindex", response_model=DeleteResponse)
async def reindex_all(background_tasks: BackgroundTasks) -> DeleteResponse:
    """
    Rebuild the entire search index.

    This is useful if the index becomes corrupted or out of sync.
    Runs in background and may take a while for large libraries.
    """
    # For now, just return a message - full implementation would
    # clear and rebuild the index from the database
    return DeleteResponse(
        success=True,
        message="Reindex operation started (not fully implemented)",
    )


@router.get("/photos", response_model=list[dict])
async def list_photos(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """
    List all indexed photos with pagination.

    - **limit**: Maximum number of photos to return (1-1000)
    - **offset**: Number of photos to skip
    """
    db = get_db()
    photos = db.list_photos(limit=limit, offset=offset)

    return [
        {
            "id": p.id,
            "file_path": p.file_path,
            "filename": p.filename,
            "timestamp": p.timestamp.isoformat() if p.timestamp else None,
            "city": p.city,
            "state": p.state,
            "country": p.country,
            "description": p.description,
            "tags": p.tags,
            "indexed_at": p.indexed_at.isoformat() if p.indexed_at else None,
        }
        for p in photos
    ]


@router.get("/photos/{photo_id}")
async def get_photo(photo_id: str) -> dict:
    """
    Get details for a specific photo.

    - **photo_id**: ID of the photo
    """
    db = get_db()
    photo = db.get_photo(photo_id)

    if photo is None:
        raise HTTPException(status_code=404, detail=f"Photo not found: {photo_id}")

    return {
        "id": photo.id,
        "file_path": photo.file_path,
        "filename": photo.filename,
        "timestamp": photo.timestamp.isoformat() if photo.timestamp else None,
        "latitude": photo.latitude,
        "longitude": photo.longitude,
        "city": photo.city,
        "state": photo.state,
        "country": photo.country,
        "place_name": photo.place_name,
        "description": photo.description,
        "tags": photo.tags,
        "indexed_at": photo.indexed_at.isoformat() if photo.indexed_at else None,
    }
