"""API routes for PhotoSearch backend."""

from fastapi import APIRouter
from pydantic import BaseModel

from photosearch import __version__
from photosearch.config import settings
from photosearch.database import Database

router = APIRouter()

# Initialize database
_db: Database | None = None


def get_db() -> Database:
    """Get or create database instance."""
    global _db
    if _db is None:
        _db = Database(settings.db_path)
    return _db


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
