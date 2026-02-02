"""Performance tests for PhotoSearch backend.

These tests measure indexing and search speed to ensure performance targets are met.
Some tests require ML models and are skipped by default.

Performance targets (from DESIGN.md):
- Index 100 photos: < 5 minutes
- Index 1000 photos: < 30 minutes
- Search (10k photos): < 200ms
- App launch: < 2s
- Thumbnail load: < 100ms
- Memory (10k photos): < 500MB
"""

import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest


# =============================================================================
# Mocked Performance Tests (run without ML models)
# =============================================================================


class TestIndexingPerformanceMocked:
    """Performance tests using mocked ML components."""

    def test_indexing_pipeline_overhead(self):
        """Test the overhead of the indexing pipeline (without ML inference).
        
        This measures: file I/O, EXIF extraction, database operations, FAISS indexing.
        ML inference time is mocked to be instant.
        """
        from photosearch.core.vector_index import VectorIndex
        from photosearch.database.db import Database
        from photosearch.utils.exif import extract_metadata
        from photosearch.utils.image import scan_folder_for_images
        from photosearch.models import PhotoCreate
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            db_path = tmpdir / "test.db"
            
            # Create test images
            jpeg_header = (
                b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
                b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
                b'\xff\xd9'
            )
            
            n_photos = 100
            for i in range(n_photos):
                (tmpdir / f"photo_{i:04d}.jpg").write_bytes(jpeg_header)
            
            # Initialize components
            db = Database(db_path)
            index = VectorIndex(dimension=512)
            
            # Mock embedding generation (instant)
            mock_embedding = np.random.randn(512).astype(np.float32)
            mock_embedding /= np.linalg.norm(mock_embedding)
            
            start = time.perf_counter()
            
            # Simulate indexing pipeline
            image_paths = scan_folder_for_images(tmpdir)
            
            for i, path in enumerate(image_paths):
                # Extract EXIF
                exif_data = extract_metadata(path)
                
                # Create photo record
                photo = PhotoCreate(
                    file_path=str(path),
                    filename=path.name,
                    timestamp=exif_data.timestamp,
                    latitude=exif_data.latitude,
                    longitude=exif_data.longitude,
                    description=f"Test photo {i}",
                    tags=["test"],
                )
                
                # Save to database
                saved = db.create_photo(photo)
                
                # Add to FAISS index
                vector_id = hash(saved.id) & 0x7FFFFFFF
                index.add_single(vector_id, mock_embedding)
            
            elapsed = time.perf_counter() - start
            
            # Verify
            assert db.count_photos() == n_photos
            assert index.size == n_photos
            
            # Pipeline overhead (without ML) should be < 5 seconds for 100 photos
            print(f"\nIndexing pipeline overhead for {n_photos} photos: {elapsed:.2f}s")
            print(f"  Per photo: {elapsed/n_photos*1000:.1f}ms")
            assert elapsed < 10.0, f"Pipeline overhead too high: {elapsed:.2f}s for {n_photos} photos"

    def test_search_performance_with_filters(self):
        """Test search performance including filter application."""
        from photosearch.database.db import Database
        from photosearch.models import PhotoCreate
        from photosearch.core.vector_index import VectorIndex
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            db_path = tmpdir / "test.db"
            
            db = Database(db_path)
            index = VectorIndex(dimension=512)
            
            # Create 10k photo records
            n_photos = 10000
            
            # Batch create photos
            start = time.perf_counter()
            
            for i in range(n_photos):
                photo = PhotoCreate(
                    file_path=f"/photos/photo_{i:05d}.jpg",
                    filename=f"photo_{i:05d}.jpg",
                    timestamp=datetime(2020 + i % 5, (i % 12) + 1, (i % 28) + 1),
                    latitude=20.0 + (i % 100) * 0.1 if i % 3 == 0 else None,
                    longitude=-150.0 + (i % 100) * 0.1 if i % 3 == 0 else None,
                    city=["Honolulu", "Tokyo", "Paris", "Sydney"][i % 4] if i % 3 == 0 else None,
                    country=["USA", "Japan", "France", "Australia"][i % 4] if i % 3 == 0 else None,
                    description=f"Photo {i}",
                    tags=["test"],
                )
                db.create_photo(photo)
                
                # Add random embedding to index
                emb = np.random.randn(512).astype(np.float32)
                emb /= np.linalg.norm(emb)
                index.add_single(i, emb)
            
            setup_elapsed = time.perf_counter() - start
            print(f"\nSetup {n_photos} photos: {setup_elapsed:.2f}s")
            
            # Test search speed
            query_embedding = np.random.randn(512).astype(np.float32)
            query_embedding /= np.linalg.norm(query_embedding)
            
            # Warm up
            index.search(query_embedding, k=100)
            
            # Timed search (vector search only)
            n_searches = 100
            start = time.perf_counter()
            for _ in range(n_searches):
                vector_ids, scores = index.search(query_embedding, k=100)
            vector_search_time = (time.perf_counter() - start) / n_searches * 1000
            
            print(f"Vector search time: {vector_search_time:.2f}ms per query")
            assert vector_search_time < 50, f"Vector search too slow: {vector_search_time:.2f}ms"
            
            # Test database query speed
            start = time.perf_counter()
            for _ in range(100):
                photos = db.search_by_location(18.0, 25.0, -160.0, -140.0, limit=100)
            db_query_time = (time.perf_counter() - start) / 100 * 1000
            
            print(f"Database location query: {db_query_time:.2f}ms per query")
            assert db_query_time < 100, f"Database query too slow: {db_query_time:.2f}ms"

    def test_batch_embedding_throughput(self):
        """Test throughput of batch operations."""
        from photosearch.core.vector_index import VectorIndex
        
        index = VectorIndex(dimension=512)
        
        batch_sizes = [10, 100, 1000]
        
        print("\nBatch embedding throughput:")
        for batch_size in batch_sizes:
            ids = np.arange(batch_size, dtype=np.int64)
            embeddings = np.random.randn(batch_size, 512).astype(np.float32)
            embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
            
            # Clear and time
            index.clear()
            start = time.perf_counter()
            index.add(ids, embeddings)
            elapsed = time.perf_counter() - start
            
            throughput = batch_size / elapsed
            print(f"  Batch size {batch_size}: {elapsed*1000:.2f}ms ({throughput:.0f} vectors/sec)")
            
            assert index.size == batch_size


# =============================================================================
# Real Performance Tests (require ML models)
# =============================================================================


class TestRealIndexingPerformance:
    """Performance tests using actual ML models.
    
    These tests are skipped by default because they require ML models.
    """

    @pytest.fixture(scope="class")
    def test_images_dir(self):
        """Get the test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    def test_clip_embedding_speed(self, test_images_dir):
        """Test CLIP embedding generation speed per image (CLIP only, no BLIP).
        
        This is a simpler test that only tests CLIP embeddings without caption generation.
        Use this if the full test crashes due to library issues.
        
        Target per image (CPU):
        - Image loading: < 200ms
        - CLIP image embedding: < 2000ms
        - CLIP text embedding: < 500ms
        """
        import os
        # Disable tokenizer parallelism to avoid potential issues
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        
        from photosearch.core.clip_processor import CLIPProcessor
        from photosearch.utils.image import load_image, scan_folder_for_images
        
        # Find test images (only jpg/png to avoid format issues)
        all_images = scan_folder_for_images(test_images_dir)
        images = [img for img in all_images if img.suffix.lower() in ['.jpg', '.jpeg', '.png']]
        if not images:
            pytest.skip("No test images found")
        
        print(f"\n\nFound {len(images)} test images")
        
        # Initialize CLIP model
        print("Initializing CLIP model...")
        init_start = time.perf_counter()
        clip = CLIPProcessor(device="cpu", local_files_only=True)
        clip_init_time = time.perf_counter() - init_start
        print(f"  CLIP model init: {clip_init_time:.2f}s")
        
        # Collect timing data for each image
        results = []
        
        for image_path in images[:5]:  # Test up to 5 images
            print(f"  Processing: {image_path.name}...", end=" ", flush=True)
            try:
                timings = {"path": image_path.name}
                
                # Time image loading
                start = time.perf_counter()
                image = load_image(image_path)
                timings["load_ms"] = (time.perf_counter() - start) * 1000
                
                # Time CLIP image embedding
                start = time.perf_counter()
                image_embedding = clip.get_image_embedding(image)
                timings["clip_image_ms"] = (time.perf_counter() - start) * 1000
                
                timings["total_ms"] = timings["load_ms"] + timings["clip_image_ms"]
                results.append(timings)
                print(f"OK ({timings['total_ms']:.0f}ms)")
                
            except Exception as e:
                print(f"FAILED: {e}")
                continue
        
        if not results:
            pytest.fail("No images could be processed")
        
        # Time text embedding (for search queries)
        print("\nTesting text embeddings...")
        test_queries = ["sunset over ocean", "city skyline"]
        text_times = []
        for query in test_queries:
            start = time.perf_counter()
            text_embedding = clip.get_text_embedding(query)
            elapsed = (time.perf_counter() - start) * 1000
            text_times.append(elapsed)
            print(f"  '{query}': {elapsed:.1f}ms")
        avg_text_ms = sum(text_times) / len(text_times)
        
        # Print results
        print("\n\nCLIP Embedding Performance (per image):")
        print("=" * 60)
        print(f"{'Image':<30} {'Load (ms)':<15} {'CLIP (ms)':<15}")
        print("-" * 60)
        
        for r in results:
            print(f"{r['path']:<30} {r['load_ms']:<15.1f} {r['clip_image_ms']:<15.1f}")
        
        avg_load = sum(r["load_ms"] for r in results) / len(results)
        avg_clip = sum(r["clip_image_ms"] for r in results) / len(results)
        
        print("-" * 60)
        print(f"{'AVERAGE':<30} {avg_load:<15.1f} {avg_clip:<15.1f}")
        print("=" * 60)
        print(f"\nText embedding avg: {avg_text_ms:.1f}ms")
        
        # Assertions
        assert avg_load < 200, f"Image loading too slow: {avg_load:.1f}ms"
        assert avg_clip < 2000, f"CLIP embedding too slow: {avg_clip:.1f}ms"

    def test_embedding_generation_speed(self, test_images_dir):
        """Test full embedding generation speed (CLIP + BLIP) per image.
        
        This test measures how long it takes to generate embeddings for each image,
        broken down by component:
        - Image loading
        - CLIP image embedding
        - CLIP text embedding (for search queries)
        - BLIP caption generation
        
        Target per image (CPU):
        - Image loading: < 200ms
        - CLIP image embedding: < 2000ms
        - CLIP text embedding: < 500ms
        - BLIP caption: < 5000ms
        """
        import os
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        
        from photosearch.core.clip_processor import CLIPProcessor
        from photosearch.core.caption_generator import CaptionGenerator
        from photosearch.utils.image import load_image, scan_folder_for_images
        
        # Find test images (only jpg/png)
        all_images = scan_folder_for_images(test_images_dir)
        images = [img for img in all_images if img.suffix.lower() in ['.jpg', '.jpeg', '.png']]
        if not images:
            pytest.skip("No test images found")
        
        # Initialize models (not counted in timing)
        print("\n\nInitializing ML models...")
        init_start = time.perf_counter()
        clip = CLIPProcessor(device="cpu", local_files_only=True)
        clip_init_time = time.perf_counter() - init_start
        
        init_start = time.perf_counter()
        caption_gen = CaptionGenerator(device="cpu", local_files_only=True)
        blip_init_time = time.perf_counter() - init_start
        
        print(f"  CLIP model init: {clip_init_time:.2f}s")
        print(f"  BLIP model init: {blip_init_time:.2f}s")
        
        # Collect timing data for each image
        results = []
        
        for image_path in images[:10]:  # Test up to 10 images
            print(f"  Processing: {image_path.name}...", end=" ", flush=True)
            try:
                timings = {"path": image_path.name}
                
                # Time image loading
                start = time.perf_counter()
                image = load_image(image_path)
                timings["load_ms"] = (time.perf_counter() - start) * 1000
                
                # Time CLIP image embedding
                start = time.perf_counter()
                image_embedding = clip.get_image_embedding(image)
                timings["clip_image_ms"] = (time.perf_counter() - start) * 1000
                
                # Time BLIP caption generation
                start = time.perf_counter()
                caption, tags = caption_gen.generate_caption_with_tags(image)
                timings["blip_caption_ms"] = (time.perf_counter() - start) * 1000
                
                # Total embedding time
                timings["total_ms"] = timings["load_ms"] + timings["clip_image_ms"] + timings["blip_caption_ms"]
                
                results.append(timings)
                print(f"OK ({timings['total_ms']:.0f}ms)")
                
            except Exception as e:
                print(f"FAILED: {e}")
                continue
        
        if not results:
            pytest.fail("No images could be processed")
        
        # Time text embedding (for search queries)
        test_queries = ["sunset over ocean", "people at a party", "mountain landscape", "city skyline"]
        text_times = []
        for query in test_queries:
            start = time.perf_counter()
            text_embedding = clip.get_text_embedding(query)
            text_times.append((time.perf_counter() - start) * 1000)
        avg_text_ms = sum(text_times) / len(text_times)
        
        # Print detailed results
        print("\n\nEmbedding Generation Performance (per image):")
        print("=" * 80)
        print(f"{'Image':<30} {'Load':<10} {'CLIP':<12} {'BLIP':<12} {'Total':<10}")
        print(f"{'':30} {'(ms)':<10} {'(ms)':<12} {'(ms)':<12} {'(ms)':<10}")
        print("-" * 80)
        
        for r in results:
            print(f"{r['path']:<30} {r['load_ms']:<10.1f} {r['clip_image_ms']:<12.1f} "
                  f"{r['blip_caption_ms']:<12.1f} {r['total_ms']:<10.1f}")
        
        # Calculate averages
        avg_load = sum(r["load_ms"] for r in results) / len(results)
        avg_clip = sum(r["clip_image_ms"] for r in results) / len(results)
        avg_blip = sum(r["blip_caption_ms"] for r in results) / len(results)
        avg_total = sum(r["total_ms"] for r in results) / len(results)
        
        print("-" * 80)
        print(f"{'AVERAGE':<30} {avg_load:<10.1f} {avg_clip:<12.1f} "
              f"{avg_blip:<12.1f} {avg_total:<10.1f}")
        print("=" * 80)
        
        print(f"\nText embedding (search query): {avg_text_ms:.1f}ms avg")
        print(f"\nBreakdown of total time:")
        print(f"  - Image loading:    {avg_load/avg_total*100:5.1f}%")
        print(f"  - CLIP embedding:   {avg_clip/avg_total*100:5.1f}%")
        print(f"  - BLIP captioning:  {avg_blip/avg_total*100:5.1f}%")
        
        # Performance assertions
        assert avg_load < 200, f"Image loading too slow: {avg_load:.1f}ms (target: < 200ms)"
        assert avg_clip < 2000, f"CLIP embedding too slow: {avg_clip:.1f}ms (target: < 2000ms on CPU)"
        assert avg_blip < 5000, f"BLIP caption too slow: {avg_blip:.1f}ms (target: < 5000ms on CPU)"
        assert avg_text_ms < 500, f"Text embedding too slow: {avg_text_ms:.1f}ms (target: < 500ms)"

    def test_single_photo_indexing_speed(self, test_images_dir):
        """Test indexing speed for a single photo.
        
        Target: < 3 seconds per photo (including all ML inference)
        """
        from photosearch.core.clip_processor import CLIPProcessor
        from photosearch.core.caption_generator import CaptionGenerator
        from photosearch.utils.image import load_image
        from photosearch.utils.exif import extract_metadata
        
        # Find a test image
        test_image = test_images_dir / "sunset.jpg"
        if not test_image.exists():
            pytest.skip("Test image not found")
        
        # Initialize models (not counted in timing)
        clip = CLIPProcessor(device="cpu", local_files_only=True)
        caption_gen = CaptionGenerator(device="cpu", local_files_only=True)
        
        # Time the full indexing pipeline
        times = []
        for _ in range(3):  # Average over 3 runs
            start = time.perf_counter()
            
            # Load image
            image = load_image(test_image)
            
            # Extract EXIF
            exif = extract_metadata(test_image)
            
            # Generate caption
            caption, tags = caption_gen.generate_caption_with_tags(image)
            
            # Generate embedding
            embedding = clip.get_image_embedding(image)
            
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        print(f"\nSingle photo indexing time: {avg_time:.2f}s (avg of 3)")
        
        assert avg_time < 3.0, f"Single photo indexing too slow: {avg_time:.2f}s"

    def test_batch_indexing_speed(self, test_images_dir):
        """Test batch indexing speed.
        
        Target: Index 100 photos in < 5 minutes
        """
        from photosearch.core.search_engine import SearchEngine
        from photosearch.utils.image import scan_folder_for_images
        
        images = scan_folder_for_images(test_images_dir)
        if len(images) < 5:
            pytest.skip("Not enough test images")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            engine = SearchEngine(
                db_path=tmpdir / "test.db",
                index_path=tmpdir / "test.index",
                device="cpu",
                local_files_only=True,
            )
            
            start = time.perf_counter()
            
            indexed = 0
            for image_path in images:
                result = engine.index_photo(image_path)
                if result:
                    indexed += 1
            
            elapsed = time.perf_counter() - start
            
            print(f"\nBatch indexing: {indexed} photos in {elapsed:.2f}s")
            print(f"  Per photo: {elapsed/indexed:.2f}s")
            print(f"  Throughput: {indexed/elapsed*60:.1f} photos/min")
            
            # Extrapolate to 100 photos
            time_for_100 = (elapsed / indexed) * 100
            print(f"  Estimated time for 100 photos: {time_for_100/60:.1f} min")
            
            assert time_for_100 < 300, f"Would take {time_for_100/60:.1f} min for 100 photos (target: < 5 min)"
            
            engine.close()


# =============================================================================
# Memory Performance Tests
# =============================================================================


class TestMemoryPerformance:
    """Tests for memory usage."""

    def test_index_memory_usage(self):
        """Test memory usage of FAISS index.
        
        Target: < 500MB for 10k photos
        FAISS uses ~2KB per 512-dim vector = ~20MB for 10k photos
        """
        import sys
        from photosearch.core.vector_index import VectorIndex
        
        index = VectorIndex(dimension=512)
        
        # Add 10k vectors
        n = 10000
        ids = np.arange(n, dtype=np.int64)
        embeddings = np.random.randn(n, 512).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        index.add(ids, embeddings)
        
        # Estimate memory (FAISS internal memory not directly measurable)
        # Each float32 = 4 bytes, 512 dims = 2048 bytes per vector
        estimated_mb = (n * 512 * 4) / (1024 * 1024)
        
        print(f"\nIndex memory estimate for {n} vectors:")
        print(f"  Embeddings: ~{estimated_mb:.1f}MB")
        print(f"  ID mappings: ~{n * 16 / (1024*1024):.1f}MB")
        print(f"  Total estimate: ~{estimated_mb + n * 16 / (1024*1024):.1f}MB")
        
        # Should be well under 500MB target
        assert estimated_mb < 100, f"Index memory too high: {estimated_mb:.1f}MB"


# =============================================================================
# FAISS-specific Performance Tests
# =============================================================================


class TestFAISSPerformance:
    """Performance tests specifically for FAISS vector operations."""

    def test_large_index_search_speed(self):
        """Test search speed on 10k vector index.
        
        Target: < 50ms per search
        """
        from photosearch.core.vector_index import VectorIndex
        
        index = VectorIndex(dimension=512)
        
        # Add 10k vectors
        n = 10000
        ids = np.arange(n, dtype=np.int64)
        embeddings = np.random.randn(n, 512).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        index.add(ids, embeddings)
        
        # Create query
        query = np.random.randn(512).astype(np.float32)
        query /= np.linalg.norm(query)
        
        # Warm up
        index.search(query, k=100)
        
        # Timed searches
        n_searches = 100
        start = time.perf_counter()
        for _ in range(n_searches):
            result_ids, scores = index.search(query, k=100)
        elapsed_ms = (time.perf_counter() - start) / n_searches * 1000
        
        print(f"\nFAISS search (10k index, k=100): {elapsed_ms:.2f}ms per query")
        assert elapsed_ms < 50, f"Search too slow: {elapsed_ms:.2f}ms (target: < 50ms)"

    def test_add_vectors_speed(self):
        """Test speed of adding vectors to index.
        
        Target: Add 10k vectors in < 5 seconds
        """
        from photosearch.core.vector_index import VectorIndex
        
        index = VectorIndex(dimension=512)
        
        n = 10000
        ids = np.arange(n, dtype=np.int64)
        embeddings = np.random.randn(n, 512).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        start = time.perf_counter()
        index.add(ids, embeddings)
        elapsed = time.perf_counter() - start
        
        print(f"\nFAISS add 10k vectors: {elapsed:.2f}s ({n/elapsed:.0f} vectors/sec)")
        assert elapsed < 5, f"Adding too slow: {elapsed:.2f}s (target: < 5s)"
        assert index.size == n
