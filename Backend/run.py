#!/usr/bin/env python3
"""Run the PhotoSearch backend server."""

import uvicorn

from photosearch.config import settings


def main():
    """Start the FastAPI server."""
    uvicorn.run(
        "photosearch.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
