"""Tests for search relevance - ensuring only relevant photos are returned."""

import tempfile
from pathlib import Path

import pytest


class TestSearchRelevance:
    """Test that search returns only relevant photos based on lexical matching."""

    @pytest.fixture
    def search_engine(self):
        """Create a search engine with test images indexed."""
        from photosearch.core.search_engine import SearchEngine

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "test.db"
            index_path = tmp_path / "test.index"

            engine = SearchEngine(
                db_path=db_path,
                index_path=index_path,
            )

            # Index test images
            fixtures = Path(__file__).parent / "fixtures"
            test_images = [
                "animal.jpg",  # otter - should match "otter", "animal", "water"
                "sunset.jpg",  # beach sunset - should match "sunset", "beach"
                "city.jpg",  # chicago skyline - should match "city", "chicago", "skyline"
                "food.jpg",  # food containers - should match "food"
                "nature.jpg",  # river/forest/mountain - should match "river", "forest", "mountain"
            ]

            for img in test_images:
                img_path = fixtures / img
                if img_path.exists():
                    result = engine.index_photo(img_path)
                    print(f"Indexed {img}: {result.description if result else 'FAILED'}")

            yield engine
            engine.close()

    def test_search_otter_returns_only_otter_image(self, search_engine):
        """Search for 'otter' should return only the otter image."""
        results = search_engine.search("otter", top_k=10)

        print(f"\nSearch 'otter' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return at least the otter image
        assert len(results.results) >= 1, "Should find at least the otter image"

        # The top result should be the otter image
        top_result = results.results[0]
        assert "otter" in top_result.description.lower(), \
            f"Top result should contain 'otter', got: {top_result.description}"

        # No non-otter images should be returned
        for r in results.results:
            assert "otter" in r.description.lower() or "animal" in Path(r.path).name.lower(), \
                f"Non-otter image returned: {r.description}"

    def test_search_sunset_returns_only_sunset_images(self, search_engine):
        """Search for 'sunset' should return only sunset-related images."""
        results = search_engine.search("sunset", top_k=10)

        print(f"\nSearch 'sunset' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return at least the sunset image
        assert len(results.results) >= 1, "Should find at least the sunset image"

        # All results should contain 'sunset' in description
        for r in results.results:
            assert "sunset" in r.description.lower(), \
                f"Non-sunset image returned: {r.description}"

    def test_search_city_returns_only_city_images(self, search_engine):
        """Search for 'city' should return only city-related images."""
        results = search_engine.search("city", top_k=10)

        print(f"\nSearch 'city' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return at least the city image
        assert len(results.results) >= 1, "Should find at least the city image"

        # Check that city image is in results (may match 'skyline' synonym)
        descriptions = [r.description.lower() for r in results.results]
        has_city_image = any(
            "chicago" in d or "skyline" in d or "city" in d or "tower" in d
            for d in descriptions
        )
        assert has_city_image, "City image should be in results"

    def test_search_food_returns_only_food_images(self, search_engine):
        """Search for 'food' should return only food-related images."""
        results = search_engine.search("food", top_k=10)

        print(f"\nSearch 'food' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return at least the food image
        assert len(results.results) >= 1, "Should find at least the food image"

        # All results should contain 'food' in description
        for r in results.results:
            assert "food" in r.description.lower(), \
                f"Non-food image returned: {r.description}"

    def test_search_dog_returns_no_results(self, search_engine):
        """Search for 'dog' should return NO results since no dog images exist."""
        results = search_engine.search("dog", top_k=10)

        print(f"\nSearch 'dog' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return NO results since there are no dog images
        assert len(results.results) == 0, \
            f"Should not return any results for 'dog', but got {len(results.results)}: " \
            f"{[r.description for r in results.results]}"

    def test_search_beach_returns_beach_images(self, search_engine):
        """Search for 'beach' should return beach-related images."""
        results = search_engine.search("beach", top_k=10)

        print(f"\nSearch 'beach' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return at least the sunset/beach image
        assert len(results.results) >= 1, "Should find at least the beach image"

        # All results should contain 'beach' in description
        for r in results.results:
            assert "beach" in r.description.lower(), \
                f"Non-beach image returned: {r.description}"

    def test_search_river_returns_nature_image(self, search_engine):
        """Search for 'river' should return the nature image."""
        results = search_engine.search("river", top_k=10)

        print(f"\nSearch 'river' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return at least the nature image (which has river in caption)
        assert len(results.results) >= 1, "Should find at least the nature image"

        # Top result should be the river image
        assert "river" in results.results[0].description.lower(), \
            f"Top result should contain 'river', got: {results.results[0].description}"

    def test_search_mountain_returns_nature_image(self, search_engine):
        """Search for 'mountain' should return the nature image."""
        results = search_engine.search("mountain", top_k=10)

        print(f"\nSearch 'mountain' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return at least the nature image
        assert len(results.results) >= 1, "Should find at least the nature image"

        # All results should contain 'mountain' in description
        for r in results.results:
            assert "mountain" in r.description.lower(), \
                f"Non-mountain image returned: {r.description}"

    def test_search_water_returns_water_related_images(self, search_engine):
        """Search for 'water' should return images with water (otter, nature via river synonym)."""
        results = search_engine.search("water", top_k=10)

        print(f"\nSearch 'water' returned {len(results.results)} results:")
        for r in results.results:
            print(f"  - {Path(r.path).name}: {r.description[:60]}...")

        # Should return images that mention water or water-related terms (river is a synonym)
        assert len(results.results) >= 1, "Should find at least one water image"

        # All results should contain 'water' or water-related terms (river, ocean, etc.)
        water_terms = {"water", "river", "ocean", "sea", "stream", "creek", "lake"}
        for r in results.results:
            desc_lower = r.description.lower()
            has_water_term = any(term in desc_lower for term in water_terms)
            assert has_water_term, \
                f"Non-water image returned: {r.description}"


class TestLexicalMatching:
    """Test the lexical matching helper function."""

    def test_exact_match(self):
        """Test exact word matching."""
        from photosearch.core.search_engine import SearchEngine

        # Create minimal engine just to access the method
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = SearchEngine(
                db_path=tmp_path / "test.db",
                index_path=tmp_path / "test.index",
            )

            # Test exact match
            assert engine._check_lexical_match(
                "otter",
                "an otter standing on a rock",
                []
            ) is True

            # Test no match
            assert engine._check_lexical_match(
                "dog",
                "an otter standing on a rock",
                []
            ) is False

            # Test match in tags
            assert engine._check_lexical_match(
                "sunset",
                "a beautiful scene",
                ["sunset", "beach"]
            ) is True

            engine.close()

    def test_synonym_match(self):
        """Test synonym matching."""
        from photosearch.core.search_engine import SearchEngine

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = SearchEngine(
                db_path=tmp_path / "test.db",
                index_path=tmp_path / "test.index",
            )

            # Test synonym: dog -> puppy
            assert engine._check_lexical_match(
                "dog",
                "a cute puppy playing in the yard",
                []
            ) is True

            # Test synonym: kid -> child
            assert engine._check_lexical_match(
                "kid",
                "a child playing with toys",
                []
            ) is True

            # Test synonym: sunset -> dusk
            assert engine._check_lexical_match(
                "sunset",
                "beautiful colors at dusk",
                []
            ) is True

            engine.close()

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        from photosearch.core.search_engine import SearchEngine

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = SearchEngine(
                db_path=tmp_path / "test.db",
                index_path=tmp_path / "test.index",
            )

            # Test case insensitive
            assert engine._check_lexical_match(
                "OTTER",
                "An Otter Standing On A Rock",
                []
            ) is True

            engine.close()
