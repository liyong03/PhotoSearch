# Migration Plan: Python Backend → Rust Single-Process

## Goal

Replace the two-process architecture (SwiftUI + Python/FastAPI) with a single-process app (SwiftUI + linked Rust library) for near-instant startup and eliminated IPC overhead.

## Current Architecture

```
PhotoSearch.app (SwiftUI) → HTTP localhost:52849 → Python/FastAPI backend
```

**Problems**: ~4s backend startup, 500ms health poll intervals, 5-30s lazy ML model loading on first search, large app bundle with Python runtime.

## Target Architecture

```
PhotoSearch.app (single process)
  └── SwiftUI frontend
  └── Rust library (linked via UniFFI → Swift Package)
        ├── Candle (CLIP + BLIP inference, Metal GPU)
        ├── Vector search (brute-force cosine similarity)
        ├── SQLite (rusqlite)
        └── Geocoding, query parsing, synonyms
```

**Expected gains**: <0.3s startup, ~30-50MB memory (vs ~221MB), no IPC overhead, smaller app bundle.

## Technology Choices

| Component | Current (Python) | Target (Rust) |
|---|---|---|
| ML inference | PyTorch + HuggingFace transformers | Candle (`candle-core` + `candle-transformers`) with Metal |
| CLIP model | `openai/clip-vit-base-patch32` via transformers | Same model via Candle (loads safetensors directly) |
| BLIP model | `Salesforce/blip-image-captioning-base` via transformers | Same model via Candle |
| Vector search | FAISS (`faiss-cpu`) | Brute-force cosine sim with `ndarray` |
| Database | `sqlite3` | `rusqlite` |
| EXIF extraction | Pillow + pillow-heif | `kamadak-exif` or `rexif` + `image` crate |
| Geocoding | `geopy` (Nominatim) | `reqwest` + Nominatim API |
| Synonyms | NLTK WordNet + static dict | Static dictionary only (embedded) |
| Swift interop | HTTP/REST (FastAPI + URLSession) | UniFFI + `cargo-swift` → Swift Package |

---

## Phases

### Phase 0: Setup & Tooling

- [ ] Add `RustCore/` directory at project root with `cargo init --lib`
- [ ] Add dependencies: `candle-core`, `candle-transformers`, `candle-nn` (with `metal` feature), `uniffi`
- [ ] Install `cargo-swift` to generate a Swift Package from the Rust lib
- [ ] Verify the Rust lib compiles and links into a test Swift CLI app

**Validation**: A Swift program can call a trivial Rust function (e.g., `add(1, 2) → 3`) via UniFFI.

### Phase 1: CLIP Inference in Rust

- [ ] Implement `encode_image(path: String) → Vec<f32>` using Candle CLIP (ViT-B/32)
- [ ] Implement `encode_text(query: String) → Vec<f32>` using Candle CLIP
- [ ] Load model weights from HuggingFace safetensors (cache in `~/Library/Application Support/PhotoSearch/models/`)
- [ ] Enable Metal GPU backend for Apple Silicon acceleration
- [ ] Expose both functions to Swift via UniFFI

**Validation**: Compare embeddings from Rust vs Python — cosine similarity between them should be >0.99 for same inputs. Run on 100 test images.

### Phase 2: Vector Search in Rust

- [ ] Implement brute-force cosine similarity search over an in-memory `ndarray` matrix
- [ ] Implement `search(query_embedding: Vec<f32>, top_k: u32) → Vec<(photo_id, score)>`
- [ ] Implement `add_embedding(photo_id: String, embedding: Vec<f32>)`
- [ ] Implement `remove_embedding(photo_id: String)`
- [ ] Implement save/load of the embedding matrix to disk (binary format)
- [ ] Expose to Swift via UniFFI

**Validation**: Search 10K embeddings returns same top-20 results as FAISS (order may differ for tied scores). Search completes in <10ms.

### Phase 3: Database in Rust

- [ ] Add `rusqlite` dependency
- [ ] Port the SQLite schema (photos, embeddings, caption_embeddings, photos_fts)
- [ ] Implement CRUD operations: insert/get/delete photos, batch operations
- [ ] Implement filtered queries: by time range, bounding box, folder path
- [ ] Implement FTS5 full-text search
- [ ] Expose to Swift via UniFFI

**Validation**: Migrate an existing `photos.db` from the Python backend. All queries return identical results.

### Phase 4: Supporting Services in Rust

- [ ] **Query parser** — port regex-based location extraction
- [ ] **Synonym service** — embed the static synonym dictionary (250+ groups); drop WordNet/NLTK
- [ ] **EXIF extraction** — use `kamadak-exif` or `rexif` crate; `image` crate for HEIC
- [ ] **Geocoding** — HTTP calls to Nominatim API via `reqwest` with LRU cache
- [ ] Expose all to Swift via UniFFI

**Validation**: Unit tests matching Python behavior for each service.

### Phase 5: Search Engine Orchestration

- [ ] Port `SearchEngine` — coordinate CLIP, vector search, DB, synonyms, geocoding
- [ ] Implement full search pipeline: query parse → CLIP encode → vector search → synonym filter → time/location filter → rank
- [ ] Implement full index pipeline: load image → EXIF → CLIP embed → caption → geocode → store
- [ ] Expose high-level API to Swift: `search(query, filters) → results`, `index_folder(path) → progress`
- [ ] Background indexing with progress callbacks via UniFFI

**Validation**: End-to-end search on a real photo library matches Python backend results.

### Phase 6: BLIP Captioning in Rust

- [ ] Implement BLIP image captioning using `candle-transformers` BLIP model
- [ ] Implement beam search (num_beams=4) for caption generation
- [ ] Implement tag extraction from captions
- [ ] Integrate into the index pipeline

**Validation**: Generate captions for 100 test images. Compare with Python BLIP output — captions should be semantically equivalent (not necessarily identical due to floating-point differences).

### Phase 7: Swift Frontend Integration

- [ ] Replace `BackendManager` — remove process spawning, health polling, termination logic
- [ ] Replace `APIClient` — call Rust functions directly instead of HTTP requests
- [ ] Update `AppState` — remove `isBackendReady` polling; backend is ready immediately
- [ ] Update `SearchViewModel` — call `RustCore.search()` directly
- [ ] Update `IndexingViewModel` — call `RustCore.indexFolder()` with progress callback
- [ ] Update `LibraryViewModel` — call `RustCore.getPhotos()` directly
- [ ] Remove all HTTP/REST related code

**Validation**: Full app works end-to-end. No Python process spawned.

### Phase 8: Cleanup

- [ ] Delete `Backend/` directory (Python code)
- [ ] Remove PyInstaller spec, requirements.txt, run_server.py
- [ ] Update build scripts
- [ ] Write one-time migration tool for existing user data (photos.db, FAISS index → new Rust format)

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| BLIP caption quality differs | Run Phase 6 validation early as a spike; if quality is unacceptable, keep a Python CLI tool for indexing only |
| UniFFI doesn't handle callbacks well | Test progress callbacks in Phase 0 setup; fall back to polling pattern if needed |
| Metal acceleration issues | Candle Metal is well-tested on Apple Silicon; CPU fallback always available |
| Existing user data migration | One-time migration tool in Phase 8 reads old FAISS index + DB and rebuilds in new format |

## Cross-Validation Test Suite

A dedicated test module that runs both Python and Rust implementations side-by-side and asserts equivalence. This ensures the Rust module produces identical results to the Python backend before we swap it in.

### Test Infrastructure

```
tests/
  cross_validation/
    fixtures/
      test_images/          # 100 diverse test images (landscapes, people, objects, etc.)
      test_queries.json     # Standard query set with expected behavior
      golden_outputs/       # Pre-computed Python outputs as ground truth
    generate_golden.py      # Runs Python backend, saves reference outputs
    test_clip.py            # CLIP embedding comparison
    test_blip.py            # BLIP caption comparison
    test_vector_search.py   # Vector search results comparison
    test_database.py        # Database query comparison
    test_search_e2e.py      # Full search pipeline comparison
    test_services.py        # Supporting services comparison
    conftest.py             # Shared fixtures and helpers
```

### Step 1: Generate Golden Outputs from Python

`generate_golden.py` runs the Python backend and saves reference outputs:

- **CLIP embeddings**: For each test image, save the 512-dim embedding vector as `.npy`
- **CLIP text embeddings**: For a set of 50 standard queries, save text embeddings
- **BLIP captions**: For each test image, save the generated caption and extracted tags
- **Search results**: For each test query (with various filter combinations), save ranked results
- **Database queries**: For a pre-populated test DB, save results of all query types

These golden outputs are committed to the repo so tests can run without the Python backend.

### Step 2: Cross-Validation Tests

#### Test: CLIP Image Embeddings (`test_clip.py`)
```
For each test image:
  python_embedding = load golden .npy
  rust_embedding = RustCore.encode_image(image_path)
  assert cosine_similarity(python_embedding, rust_embedding) > 0.99
  assert rust_embedding.shape == (512,)
  assert is_normalized(rust_embedding)  # L2 norm ≈ 1.0
```

#### Test: CLIP Text Embeddings (`test_clip.py`)
```
For each test query:
  python_embedding = load golden .npy
  rust_embedding = RustCore.encode_text(query)
  assert cosine_similarity(python_embedding, rust_embedding) > 0.99
```

#### Test: Cross-modal Consistency (`test_clip.py`)
```
For (image, query) pairs known to be relevant:
  rust_image_emb = RustCore.encode_image(image)
  rust_text_emb = RustCore.encode_text(query)
  python_score = load golden similarity score
  rust_score = cosine_similarity(rust_image_emb, rust_text_emb)
  assert abs(rust_score - python_score) < 0.01
```

#### Test: BLIP Captions (`test_blip.py`)
```
For each test image:
  python_caption = load golden caption
  rust_caption = RustCore.generate_caption(image_path)
  # Exact match is NOT required (floating-point differences in beam search)
  # Instead, check semantic equivalence:
  python_caption_emb = RustCore.encode_text(python_caption)
  rust_caption_emb = RustCore.encode_text(rust_caption)
  assert cosine_similarity(python_caption_emb, rust_caption_emb) > 0.90
  # Also check tags overlap:
  python_tags = load golden tags
  rust_tags = RustCore.extract_tags(rust_caption)
  assert jaccard_similarity(python_tags, rust_tags) > 0.7
```

#### Test: Vector Search (`test_vector_search.py`)
```
Setup:
  Load 10K golden embeddings into both Python FAISS and Rust brute-force index

For each test query embedding:
  python_results = FAISS.search(query, top_k=20)
  rust_results = RustCore.search(query, top_k=20)
  # Top results must match (order may differ for tied scores)
  assert set(python_results.top_5_ids) == set(rust_results.top_5_ids)
  # Scores must be close
  for py, rs in zip(python_results, rust_results):
    assert abs(py.score - rs.score) < 0.001
  # Performance
  assert rust_search_time < 10ms
```

#### Test: Database Queries (`test_database.py`)
```
Setup:
  Create identical test DB in both Python and Rust with 1K photo records

Tests:
  - get_photo(id) returns identical fields
  - get_photos(limit, offset) returns same pagination
  - filter_by_time_range(start, end) returns same photo IDs
  - filter_by_location(bbox) returns same photo IDs
  - filter_by_folder(path) returns same photo IDs
  - full_text_search(query) returns same ranked results
  - insert/delete operations maintain consistency
```

#### Test: Query Parser (`test_services.py`)
```
Test cases (from Python's existing behavior):
  "sunset from Hawaii"       → query="sunset", location="Hawaii"
  "dogs in Central Park"     → query="dogs", location="Central Park"
  "birthday party"           → query="birthday party", location=None
  "taken in Paris at night"  → query="at night", location="Paris"
  ... 30+ test cases covering all regex patterns

For each:
  assert RustCore.parse_query(input) == expected
```

#### Test: Synonym Service (`test_services.py`)
```
For each synonym group in the Python static dictionary:
  python_synonyms = python_get_synonyms(word)
  rust_synonyms = RustCore.get_synonyms(word)
  # Static synonyms must match exactly
  assert python_static_synonyms == rust_synonyms
  # WordNet-only synonyms are acceptable to drop (documented in migration)

Edge cases:
  - Stop words return empty set
  - Unknown words return {word} only
  - Case insensitivity
```

#### Test: EXIF Extraction (`test_services.py`)
```
For each test image with known EXIF:
  python_exif = python_extract_exif(image_path)
  rust_exif = RustCore.extract_exif(image_path)
  assert rust_exif.timestamp == python_exif.timestamp
  assert abs(rust_exif.latitude - python_exif.latitude) < 0.0001
  assert abs(rust_exif.longitude - python_exif.longitude) < 0.0001
  assert rust_exif.camera_make == python_exif.camera_make

Formats: JPEG, HEIC, PNG, TIFF
```

#### Test: End-to-End Search (`test_search_e2e.py`)
```
Setup:
  Index 100 test images with both Python and Rust

For each test query + filter combination:
  python_results = python_search(query, filters)
  rust_results = RustCore.search(query, filters)
  # Top 10 results should overlap significantly
  python_top10 = set(r.photo_id for r in python_results[:10])
  rust_top10 = set(r.photo_id for r in rust_results[:10])
  overlap = len(python_top10 & rust_top10) / 10
  assert overlap >= 0.8  # At least 80% overlap in top 10
  # Scores should be in same ballpark
  assert abs(python_results[0].score - rust_results[0].score) < 0.05

Filter combinations to test:
  - Query only
  - Query + time range
  - Query + location
  - Query + folder path
  - Query + all filters
  - Location-only (no text query)
```

### Running the Tests

```bash
# Step 1: Generate golden outputs (one-time, requires Python backend)
cd tests/cross_validation
python generate_golden.py --images fixtures/test_images/ --output fixtures/golden_outputs/

# Step 2: Run Rust cross-validation tests
cd RustCore
cargo test --test cross_validation

# Step 3: Run from CI (golden outputs already committed)
cargo test --test cross_validation --features ci
```

### Acceptance Criteria

| Component | Metric | Threshold |
|---|---|---|
| CLIP image embeddings | Cosine similarity vs Python | > 0.99 |
| CLIP text embeddings | Cosine similarity vs Python | > 0.99 |
| Cross-modal scores | Absolute score difference | < 0.01 |
| BLIP captions | Caption embedding similarity | > 0.90 |
| BLIP tags | Jaccard similarity | > 0.70 |
| Vector search | Top-5 ID set overlap | 100% |
| Vector search | Score difference | < 0.001 |
| Database queries | Result set equality | 100% |
| Query parser | Output equality | 100% |
| Synonyms (static) | Set equality | 100% |
| EXIF extraction | Field equality | 100% |
| E2E search top-10 | ID overlap | >= 80% |

---

## Execution Notes

- Phases 0-2 are the **critical path** — they prove the architecture works
- Phase 6 (BLIP) is the **highest technical risk** — spike it early in parallel
- Phases 3-5 are straightforward porting work
- Phase 7 is integration

## Reference Projects

- **sriv** (`dllu/sriv`) — Rust image viewer with CLIP semantic search via Candle
- **imgfind** (`flaribbit/imgfind`) — Local image search with Rust + Candle + CLIP
