"""Query parser for extracting location and semantic components from search queries."""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedQuery:
    """Result of parsing a search query."""

    semantic_query: str
    location: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "semantic_query": self.semantic_query,
            "location": self.location,
        }


class QueryParser:
    """Parser for extracting location information from natural language queries.

    Recognizes patterns like:
    - "sunset from Hawaii"
    - "beach in California"
    - "photos taken in Paris"
    - "mountains near Denver"
    """

    # Patterns for location extraction (case-insensitive)
    # Each pattern should have one capture group for the location name
    # NOTE: Order matters! More specific patterns (e.g., "taken in") must come before
    # less specific ones (e.g., "in") to ensure correct matching.
    LOCATION_PATTERNS = [
        # "from <Location>" - e.g., "photos from Hawaii"
        r"\bfrom\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)?)",
        # "taken in <Location>" - e.g., "photos taken in Paris" (must be before "in")
        r"\btaken\s+in\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)?)",
        # "in <Location>" - e.g., "beach in California"
        r"\bin\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)?)",
        # "near <Location>" - e.g., "mountains near Denver"
        r"\bnear\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)?)",
        # "at <Location>" - e.g., "photos at Golden Gate"
        r"\bat\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)?)",
    ]

    def __init__(self):
        """Initialize query parser with compiled regex patterns."""
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.LOCATION_PATTERNS
        ]

    def parse(self, query: str) -> ParsedQuery:
        """Parse a search query to extract location and semantic components.

        Args:
            query: The search query string.

        Returns:
            ParsedQuery with semantic_query and optional location.
        """
        if not query or not query.strip():
            return ParsedQuery(semantic_query="")

        query = query.strip()
        location = None
        semantic_query = query

        # Try each pattern to find a location
        for pattern in self._compiled_patterns:
            match = pattern.search(query)
            if match:
                location = match.group(1).strip()
                # Remove the location phrase from the semantic query
                semantic_query = pattern.sub("", query).strip()
                # Clean up extra whitespace
                semantic_query = re.sub(r"\s+", " ", semantic_query).strip()
                logger.debug(f"Extracted location '{location}' from query '{query}'")
                break

        return ParsedQuery(
            semantic_query=semantic_query if semantic_query else query,
            location=location,
        )

    def extract_location(self, query: str) -> Optional[str]:
        """Extract just the location from a query.

        Args:
            query: The search query string.

        Returns:
            Location string or None if no location found.
        """
        return self.parse(query).location

    def get_semantic_query(self, query: str) -> str:
        """Get just the semantic (non-location) part of a query.

        Args:
            query: The search query string.

        Returns:
            Semantic query string.
        """
        return self.parse(query).semantic_query
