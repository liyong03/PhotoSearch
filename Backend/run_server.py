#!/usr/bin/env python3
"""
Standalone server runner for PhotoSearch backend.
Used when bundling with PyInstaller.
"""

import os
import sys
from pathlib import Path


def get_data_directory() -> Path:
    """Get the data directory for storing database and index files.
    
    Always uses ~/Library/Application Support/PhotoSearch/ to ensure
    consistency between development and bundled app modes.
    """
    # Always use Application Support directory for consistency
    # This ensures dev mode and bundled mode share the same database
    app_support = Path.home() / "Library" / "Application Support" / "PhotoSearch"
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support


def main():
    """Start the PhotoSearch backend server."""
    import uvicorn

    # Set up environment
    data_dir = get_data_directory()
    os.environ.setdefault("PHOTOSEARCH_DATA_DIR", str(data_dir))
    os.environ.setdefault("PHOTOSEARCH_DB_PATH", str(data_dir / "photos.db"))
    os.environ.setdefault("PHOTOSEARCH_INDEX_PATH", str(data_dir / "photo_index"))

    # Get port from environment or use default (unique port to avoid conflicts)
    port = int(os.environ.get("PHOTOSEARCH_PORT", "52849"))
    host = os.environ.get("PHOTOSEARCH_HOST", "127.0.0.1")

    print(f"Starting PhotoSearch backend on {host}:{port}")
    print(f"Data directory: {data_dir}")

    # Run the server
    uvicorn.run(
        "photosearch.main:app",
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
