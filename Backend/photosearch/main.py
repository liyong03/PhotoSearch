"""FastAPI application entry point for PhotoSearch backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from photosearch import __version__
from photosearch.api import router
from photosearch.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    print(f"PhotoSearch Backend v{__version__} starting...")
    print(f"Data directory: {settings.data_dir}")
    print(f"API available at: http://{settings.host}:{settings.port}{settings.api_prefix}")

    yield

    # Shutdown
    print("PhotoSearch Backend shutting down...")


app = FastAPI(
    title="PhotoSearch API",
    description="AI-powered photo search backend service",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router with prefix
app.include_router(router, prefix=settings.api_prefix)


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "name": "PhotoSearch API",
        "version": __version__,
        "docs": "/docs",
        "status": f"{settings.api_prefix}/status",
    }
