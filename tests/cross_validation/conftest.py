"""
Shared test configuration and fixtures for cross-validation tests.

These tests compare the Rust implementation output against golden outputs
generated from the Python backend.
"""
import json
import os
from pathlib import Path

import pytest
import numpy as np


FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = FIXTURES_DIR / "golden_outputs"
TEST_IMAGES_DIR = FIXTURES_DIR / "test_images"


def golden_exists():
    """Check if golden outputs have been generated."""
    return (GOLDEN_DIR / "clip" / "test_queries.json").exists()


def load_golden_json(subdir: str, filename: str):
    """Load a JSON file from golden outputs."""
    path = GOLDEN_DIR / subdir / filename
    if not path.exists():
        pytest.skip(f"Golden output not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_golden_npy(subdir: str, filename: str) -> np.ndarray:
    """Load a numpy array from golden outputs."""
    path = GOLDEN_DIR / subdir / filename
    if not path.exists():
        pytest.skip(f"Golden output not found: {path}")
    return np.load(path)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def jaccard_similarity(set_a, set_b) -> float:
    """Compute Jaccard similarity between two sets."""
    a = set(set_a)
    b = set(set_b)
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0
