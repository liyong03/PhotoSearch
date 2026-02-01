"""Shared test fixtures and configuration."""

import os
import tempfile
from pathlib import Path

import pytest

# Set test environment before importing app modules
os.environ["PHOTOSEARCH_DEBUG"] = "true"


@pytest.fixture(scope="session")
def test_data_dir():
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="session")
def test_photos_dir(test_data_dir):
    """Create a directory with test photos."""
    photos_dir = test_data_dir / "photos"
    photos_dir.mkdir(exist_ok=True)
    return photos_dir
