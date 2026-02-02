# Photo Search App - Design Document

## Overview
A native macOS photo search application that automatically indexes photos with AI-generated descriptions and metadata, enabling powerful search capabilities including text search, time range filtering, and location-based queries.

## System Architecture (Hybrid: SwiftUI + Python Backend)

```
┌─────────────────────────────────────────────────────────────┐
│                   macOS Native UI (SwiftUI)                  │
│  - Search Bar + Filters                                      │
│  - Photo Grid with Quick Look                                │
│  - Sidebar Navigation                                        │
│  - Native macOS Design Language                              │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP (localhost:8765)
┌──────────────────────▼──────────────────────────────────────┐
│                   Python Backend (FastAPI)                   │
│  - REST API for search, indexing, geocoding                  │
│  - Runs as local service (LaunchAgent)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼───────┐ ┌────▼────┐ ┌───────▼───────┐
│  AI Models    │ │  FAISS  │ │    SQLite     │
│  - CLIP       │ │  Vector │ │   Metadata    │
│  - BLIP       │ │  Index  │ │   Database    │
│  (PyTorch)    │ │         │ │               │
└───────────────┘ └─────────┘ └───────────────┘
```

## Technology Stack

### Frontend (macOS App)
- **UI Framework**: SwiftUI with AppKit integration
- **HTTP Client**: URLSession for backend communication
- **Image Handling**: Core Image, CGImageSource for thumbnails
- **File Access**: FileManager, Security-Scoped Bookmarks
- **Background Tasks**: async/await, GCD

### Backend (Python Service)
- **Web Framework**: FastAPI + Uvicorn
- **ML Models**: PyTorch, Transformers (CLIP, BLIP)
- **Vector Search**: FAISS (Facebook AI Similarity Search)
- **Database**: SQLite for metadata
- **Geocoding**: geopy + Nominatim (OpenStreetMap)
- **Image Processing**: Pillow

### Why Hybrid Architecture?
- **Best ML Performance**: Use original PyTorch models without conversion issues
- **FAISS**: Industry-standard vector search, battle-tested at scale
- **Flexibility**: Easy to swap/upgrade models without app rebuild
- **Development Speed**: Python ML ecosystem is more mature
- **Trade-off**: Requires bundling Python runtime (~100MB)

## Data Models

### Photo Record
```python
{
    "id": "uuid",
    "file_path": "/path/to/photo.jpg",
    "filename": "photo.jpg",
    "timestamp": "2024-03-15T14:30:00",
    "location": {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "city": "San Francisco",
        "state": "California",
        "country": "USA",
        "place_name": "Golden Gate Bridge"
    },
    "description": "A sunset over the Golden Gate Bridge with orange sky",
    "embedding": [0.123, 0.456, ...],  # 512-dimensional CLIP vector
    "tags": ["sunset", "bridge", "ocean", "golden gate"],
    "indexed_at": "2024-03-20T10:00:00"
}
```

### Database Schema (SQLite)

```sql
CREATE TABLE photos (
    id TEXT PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    timestamp DATETIME,
    latitude REAL,
    longitude REAL,
    city TEXT,
    state TEXT,
    country TEXT,
    place_name TEXT,
    description TEXT,
    tags TEXT,  -- JSON array
    indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_timestamp ON photos(timestamp);
CREATE INDEX idx_latitude ON photos(latitude);
CREATE INDEX idx_longitude ON photos(longitude);
CREATE INDEX idx_city ON photos(city);
CREATE INDEX idx_country ON photos(country);

-- Full-text search on description and location fields
CREATE VIRTUAL TABLE photos_fts USING fts5(
    description, city, country, place_name,
    content='photos', content_rowid='rowid'
);
```

### FAISS Vector Index
- Maps photo_id → 512-dimensional CLIP embedding
- `IndexFlatIP` for exact search (libraries < 10k photos)
- `IndexIVFFlat` for approximate search (larger libraries)

## Backend API

```
Base URL: http://localhost:8765/api/v1
```

### POST /index
Index a single photo.
```json
Request: { "photo_path": "/path/to/photo.jpg" }
Response: {
    "id": "uuid",
    "description": "A sunset over mountains",
    "tags": ["sunset", "mountains", "nature"],
    "location": { "city": "Denver", "state": "Colorado", "country": "USA" }
}
```

### POST /index/batch
Index a folder of photos.
```json
Request: { "folder_path": "/path/to/photos", "recursive": true }
Response: { "task_id": "uuid", "status": "started", "total_files": 150 }
```

### GET /index/status/{task_id}
Check indexing progress.
```json
Response: { "progress": 0.75, "processed": 112, "total": 150, "status": "running" }
```

### POST /search
Search photos with optional filters.
```json
Request: {
    "query": "sunset on beach",
    "top_k": 20,
    "time_range": { "start": "2024-01-01", "end": "2024-12-31" },
    "location": "Hawaii"
}
Response: {
    "results": [
        {
            "id": "uuid",
            "path": "/path/to/photo.jpg",
            "score": 0.89,
            "description": "Beautiful sunset at Waikiki Beach",
            "timestamp": "2024-06-15T18:30:00",
            "city": "Honolulu",
            "country": "USA"
        }
    ],
    "location_resolved": {
        "query": "Hawaii",
        "bounding_box": { "min_lat": 18.91, "max_lat": 22.24, "min_lon": -160.25, "max_lon": -154.81 }
    },
    "total_results": 45
}
```

### POST /geocode
Convert place name to bounding box.
```json
Request: { "place_name": "Hawaii" }
Response: {
    "name": "Hawaii",
    "bounding_box": { "min_lat": 18.91, "max_lat": 22.24, "min_lon": -160.25, "max_lon": -154.81 },
    "center": { "lat": 20.57, "lon": -157.53 }
}
```

### GET /status
Backend health and stats.
```json
Response: { "status": "ok", "version": "0.1.0", "indexed_count": 1500, "index_size_mb": 12.5 }
```

### GET /health
Simple health check.
```json
Response: { "status": "healthy" }
```

### DELETE /index/{photo_id}
Remove a photo from the index.
```json
Response: { "success": true, "message": "Photo {photo_id} removed from index" }
```

### POST /reindex
Rebuild entire index.
```json
Response: { "success": true, "message": "Reindex operation started" }
```

### GET /photos
List indexed photos with pagination.
```json
Request: GET /photos?limit=100&offset=0
Response: [
    {
        "id": "uuid",
        "file_path": "/path/to/photo.jpg",
        "filename": "photo.jpg",
        "timestamp": "2024-06-15T18:30:00",
        "city": "Honolulu",
        "country": "USA",
        "description": "A sunset over the ocean",
        "tags": ["sunset", "ocean"]
    }
]
```

### GET /photos/{photo_id}
Get details for a specific photo.
```json
Response: {
    "id": "uuid",
    "file_path": "/path/to/photo.jpg",
    "filename": "photo.jpg",
    "timestamp": "2024-06-15T18:30:00",
    "latitude": 21.3069,
    "longitude": -157.8583,
    "city": "Honolulu",
    "state": "Hawaii",
    "country": "USA",
    "place_name": "Waikiki Beach",
    "description": "A sunset over the ocean",
    "tags": ["sunset", "ocean"],
    "indexed_at": "2024-06-20T10:00:00"
}
```

## Core Components

### Swift Frontend

#### APIClient
```swift
class APIClient {
    private let baseURL = URL(string: "http://localhost:8765/api/v1")!

    func search(query: String, topK: Int, timeRange: DateInterval?, location: String?) async throws -> SearchResponse

    func indexFolder(_ url: URL) async throws -> IndexTask

    func getIndexStatus(_ taskId: String) async throws -> IndexProgress

    func getBackendStatus() async throws -> BackendStatus
}
```

#### PhotoLoader
```swift
class PhotoLoader {
    func scanFolder(_ url: URL, extensions: [String] = ["jpg", "jpeg", "png", "heic"]) -> [URL]

    func requestFolderAccess() async -> URL?  // NSOpenPanel

    func saveFolderBookmark(_ url: URL) throws  // Security-Scoped Bookmark
}
```

#### ThumbnailCache
```swift
class ThumbnailCache {
    func thumbnail(for url: URL, size: CGSize) async -> NSImage?

    func preloadThumbnails(for urls: [URL])

    func clearCache()
}
```

### Python Backend

#### CLIPProcessor
```python
class CLIPProcessor:
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        self.model = CLIPModel.from_pretrained(model_name)
        self.processor = CLIPProcessor.from_pretrained(model_name)

    def get_image_embedding(self, image: Image) -> np.ndarray:
        """Generate 512-d embedding for an image."""

    def get_text_embedding(self, text: str) -> np.ndarray:
        """Generate 512-d embedding for a text query."""
```

#### CaptionGenerator
```python
class CaptionGenerator:
    def __init__(self, model_name: str = "Salesforce/blip-image-captioning-base"):
        self.model = BlipForConditionalGeneration.from_pretrained(model_name)
        self.processor = BlipProcessor.from_pretrained(model_name)

    def generate_caption(self, image: Image) -> str:
        """Generate natural language description for an image."""

    def extract_tags(self, caption: str) -> list[str]:
        """Extract key tags from caption using NLP."""
```

#### SearchEngine
```python
class SearchEngine:
    def __init__(self, db_path: str, index_path: str):
        self.db = Database(db_path)
        self.faiss_index = faiss.read_index(index_path)
        self.clip = CLIPProcessor()
        self.location_service = LocationService()

    def search(
        self,
        query: str,
        top_k: int = 20,
        time_range: tuple[datetime, datetime] | None = None,
        location: str | None = None
    ) -> list[SearchResult]:
        # 1. Parse query to extract location if present
        parsed = self.parse_query(query)

        # 2. Generate query embedding
        query_embedding = self.clip.get_text_embedding(parsed.semantic_query)

        # 3. FAISS vector search
        scores, indices = self.faiss_index.search(query_embedding, top_k * 3)

        # 4. Get photo metadata from SQLite
        candidates = self.db.get_photos_by_indices(indices)

        # 5. Apply filters
        if time_range:
            candidates = self.filter_by_time(candidates, time_range)
        if location or parsed.location:
            loc = location or parsed.location
            bbox = self.location_service.geocode(loc)
            candidates = self.filter_by_location(candidates, bbox)

        # 6. Return top_k results
        return candidates[:top_k]
```

#### LocationService
```python
class LocationService:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="photosearch")
        self._cache = {}  # LRU cache for geocoding results

    def geocode(self, place_name: str) -> BoundingBox | None:
        """Convert place name to GPS bounding box."""
        if place_name in self._cache:
            return self._cache[place_name]

        location = self.geolocator.geocode(place_name, exactly_one=True)
        if location and 'boundingbox' in location.raw:
            bb = location.raw['boundingbox']
            bbox = BoundingBox(
                min_lat=float(bb[0]), max_lat=float(bb[1]),
                min_lon=float(bb[2]), max_lon=float(bb[3])
            )
            self._cache[place_name] = bbox
            return bbox
        return None

    def reverse_geocode(self, lat: float, lon: float) -> PlaceInfo | None:
        """Convert GPS coordinates to place name."""
        location = self.geolocator.reverse(f"{lat}, {lon}")
        if location:
            addr = location.raw.get('address', {})
            return PlaceInfo(
                city=addr.get('city') or addr.get('town'),
                state=addr.get('state'),
                country=addr.get('country'),
                place_name=addr.get('tourism') or addr.get('amenity')
            )
        return None
```

#### QueryParser
```python
class QueryParser:
    LOCATION_PATTERNS = [
        r'\bfrom\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # "from Hawaii"
        r'\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',     # "in Paris"
        r'\btaken\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        r'\bnear\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
    ]

    def parse(self, query: str) -> ParsedQuery:
        location = None
        semantic_query = query

        for pattern in self.LOCATION_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                location = match.group(1)
                semantic_query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
                break

        return ParsedQuery(semantic_query=semantic_query, location=location)
```

## File Structure

```
PhotoSearch/
├── PhotoSearch.xcodeproj/
├── PhotoSearch/                        # macOS SwiftUI App
│   ├── App/
│   │   ├── PhotoSearchApp.swift        # App entry point
│   │   └── AppDelegate.swift           # Manage backend lifecycle
│   ├── Views/
│   │   ├── ContentView.swift           # Main window
│   │   ├── SearchBar.swift             # Search input
│   │   ├── PhotoGridView.swift         # Photo grid display
│   │   ├── PhotoDetailView.swift       # Single photo view
│   │   ├── FilterPanel.swift           # Time/location filters
│   │   ├── SidebarView.swift           # Folder navigation
│   │   └── IndexingProgressView.swift  # Indexing status
│   ├── ViewModels/
│   │   ├── SearchViewModel.swift
│   │   ├── LibraryViewModel.swift
│   │   └── IndexingViewModel.swift
│   ├── Models/
│   │   ├── Photo.swift
│   │   ├── SearchResult.swift
│   │   └── IndexTask.swift
│   ├── Services/
│   │   ├── APIClient.swift             # Backend communication
│   │   ├── PhotoLoader.swift           # File scanning
│   │   ├── ThumbnailCache.swift        # Image caching
│   │   └── BackendManager.swift        # Start/stop backend
│   └── Resources/
│       ├── Assets.xcassets
│       └── Localizable.strings
├── Backend/                             # Python Backend
│   ├── photosearch/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app entry
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py               # API endpoints
│   │   │   └── models.py               # Pydantic models
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── clip_processor.py       # CLIP model
│   │   │   ├── caption_generator.py    # BLIP model
│   │   │   ├── search_engine.py        # FAISS search
│   │   │   ├── query_parser.py         # Query parsing
│   │   │   └── location_service.py     # Geocoding
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── db.py                   # SQLite operations
│   │   │   └── schema.sql
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── exif.py                 # EXIF extraction
│   │       └── image.py                # Image processing
│   ├── data/
│   │   ├── photos.db                   # SQLite database
│   │   └── faiss.index                 # Vector index
│   ├── requirements.txt
│   └── run.py                          # Server startup script
├── LaunchAgent/
│   └── com.photosearch.backend.plist   # Auto-start backend
├── scripts/
│   ├── install_backend.sh              # Setup Python environment
│   └── bundle_backend.sh               # Package for distribution
├── PhotoSearchTests/
├── PhotoSearchUITests/
└── README.md
```

## Implementation Flow

### Indexing Flow
```
1. User selects folder in SwiftUI app
2. App saves Security-Scoped Bookmark for folder access
3. App calls POST /index/batch with folder path
4. Backend scans folder for image files
5. For each photo:
   a. Load image with Pillow
   b. Extract EXIF (timestamp, GPS)
   c. Reverse geocode GPS → city/state/country
   d. Generate caption with BLIP
   e. Generate CLIP embedding
   f. Save metadata to SQLite
   g. Add embedding to FAISS index
6. Backend reports progress via GET /index/status
7. App displays progress bar
8. On completion, FAISS index is saved to disk
```

### Search Flow
```
1. User enters query: "sunset photos from Hawaii"
2. App calls POST /search with query and filters
3. Backend:
   a. Parse query → semantic: "sunset photos", location: "Hawaii"
   b. Geocode "Hawaii" → bounding box
   c. Generate CLIP embedding for "sunset photos"
   d. FAISS search → top 60 candidates
   e. Filter by bounding box → 25 matches
   f. Filter by time range if specified
   g. Return top 20 results with metadata
4. App displays photo grid with results
5. User clicks photo → detail view with description
```

## Location Search

### Query Examples
| User Query | Semantic Query | Location Filter |
|------------|----------------|-----------------|
| "sunset photos from Hawaii" | "sunset photos" | Hawaii bbox |
| "beach in California" | "beach" | California bbox |
| "Eiffel Tower" | "Eiffel Tower" | None (CLIP handles it) |
| "family photos in Tokyo 2023" | "family photos" | Tokyo bbox + time filter |

### Geocoding Flow
```
"Hawaii" → Nominatim API → BoundingBox(18.91, 22.24, -160.25, -154.81)
                               ↓
SQL: WHERE latitude BETWEEN 18.91 AND 22.24
     AND longitude BETWEEN -160.25 AND -154.81
```

## Backend Lifecycle

### Starting the Backend
The Swift app manages the Python backend lifecycle:

```swift
class BackendManager {
    private var backendProcess: Process?

    func startBackend() throws {
        let process = Process()
        process.executableURL = Bundle.main.url(forResource: "python", withExtension: nil, subdirectory: "Backend/venv/bin")
        process.arguments = ["-m", "uvicorn", "photosearch.main:app", "--port", "8765"]
        process.currentDirectoryURL = Bundle.main.url(forResource: "Backend", withExtension: nil)
        try process.run()
        backendProcess = process
    }

    func stopBackend() {
        backendProcess?.terminate()
    }

    func waitForBackend() async throws {
        // Poll /status until backend is ready
    }
}
```

### LaunchAgent (Auto-start)
```xml
<!-- ~/Library/LaunchAgents/com.photosearch.backend.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.photosearch.backend</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/PhotoSearch.app/Contents/Resources/Backend/venv/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>photosearch.main:app</string>
        <string>--port</string>
        <string>8765</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Applications/PhotoSearch.app/Contents/Resources/Backend</string>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

## Performance Considerations

### Indexing
- Batch processing: 10 images at a time to avoid memory spikes
- Progress reporting every 10 images
- Resume capability: track indexed files in SQLite
- GPU acceleration: Use MPS (Metal) on Apple Silicon if available

### Search
- FAISS `IndexIVFFlat` for libraries > 10k photos (sub-100ms search)
- Cache geocoding results (LRU cache with 1000 entries)
- Thumbnail pre-generation during indexing

### Storage
- SQLite: ~1KB per photo
- FAISS index: ~2KB per photo (512-dim float32)
- Thumbnails: ~50KB per photo (256x256 JPEG)
- For 10,000 photos: ~500MB total

## Distribution

### App Bundle Structure
```
PhotoSearch.app/
└── Contents/
    ├── MacOS/
    │   └── PhotoSearch              # Swift app binary
    ├── Resources/
    │   ├── Backend/
    │   │   ├── venv/                # Bundled Python + dependencies
    │   │   ├── photosearch/         # Python source
    │   │   └── requirements.txt
    │   └── Assets.car
    └── Info.plist
```

### Bundling Python
Use `py2app` or custom script to bundle:
1. Create virtual environment with all dependencies
2. Include PyTorch (CPU-only to reduce size, ~200MB)
3. Pre-download ML models during first run or include in bundle
4. Total backend size: ~500MB - 1GB depending on models

## Development Milestones

### Overview

```
Backend Milestones (B1-B8)          Frontend Milestones (F1-F6)
========================          =========================
B1: Project Setup                  F1: Project Setup
        ↓                                  ↓
B2: Database Layer                 F2: API Client
        ↓                                  ↓
B3: EXIF Extraction                F3: Photo Grid & Search UI
        ↓                                  ↓
B4: CLIP Embeddings                F4: Search Integration
        ↓                                  ↓
B5: FAISS Vector Search            F5: Filters & Folder Management
        ↓                                  ↓
B6: Image Captioning               F6: Indexing Progress & Polish
        ↓
B7: Location Service
        ↓
B8: Full Search Integration
```

---

## Backend Milestones

### B1: Project Setup & Basic API
**Goal**: Set up Python project structure with FastAPI and basic health endpoint.

**Deliverables**:
- Project structure with `photosearch/` package
- FastAPI app with `/status` endpoint
- Requirements.txt with dependencies
- Basic configuration management

**Files to Create**:
```
Backend/
├── photosearch/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── config.py            # Configuration
│   └── api/
│       ├── __init__.py
│       └── routes.py        # API routes
├── requirements.txt
├── run.py
└── pytest.ini
```

**Test Plan**:
```bash
# Test 1: Server starts without errors
uvicorn photosearch.main:app --port 8765
# Expected: Server starts, logs "Uvicorn running on http://127.0.0.1:8765"

# Test 2: Health endpoint works
curl http://localhost:8765/api/v1/status
# Expected: {"status": "ok", "version": "0.1.0"}

# Test 3: Unit tests pass
pytest tests/test_api.py -v
# Expected: All tests pass
```

**Acceptance Criteria**:
- [ ] `uvicorn photosearch.main:app` starts without errors
- [ ] `GET /api/v1/status` returns `{"status": "ok"}`
- [ ] All unit tests pass

---

### B2: Database Layer
**Goal**: Implement SQLite database for photo metadata storage.

**Deliverables**:
- Database schema creation
- CRUD operations for photos
- Database connection management

**Files to Create**:
```
Backend/photosearch/
├── database/
│   ├── __init__.py
│   ├── db.py               # Database connection & operations
│   └── schema.sql          # SQL schema
└── models.py               # Pydantic models
```

**Test Plan**:
```bash
# Test 1: Database creation
pytest tests/test_database.py::test_create_database -v
# Expected: Creates photos.db with correct schema

# Test 2: Insert photo record
pytest tests/test_database.py::test_insert_photo -v
# Expected: Photo inserted, can be retrieved by ID

# Test 3: Query by file path
pytest tests/test_database.py::test_query_by_path -v
# Expected: Returns photo record for given path

# Test 4: Update photo record
pytest tests/test_database.py::test_update_photo -v
# Expected: Photo metadata updated correctly

# Test 5: Delete photo record
pytest tests/test_database.py::test_delete_photo -v
# Expected: Photo removed from database

# Test 6: Full-text search on description
pytest tests/test_database.py::test_fts_search -v
# Expected: Returns photos matching text query
```

**Acceptance Criteria**:
- [ ] Database created with correct schema
- [ ] Insert, query, update, delete operations work
- [ ] Full-text search on description field works
- [ ] All unit tests pass

---

### B3: EXIF Extraction
**Goal**: Extract metadata (timestamp, GPS) from photo EXIF data.

**Deliverables**:
- EXIF extraction from JPEG, PNG, HEIC
- GPS coordinate parsing
- Timestamp extraction with timezone handling

**Files to Create**:
```
Backend/photosearch/
└── utils/
    ├── __init__.py
    ├── exif.py             # EXIF extraction
    └── image.py            # Image loading utilities
```

**Test Plan**:
```bash
# Test 1: Extract timestamp from JPEG
pytest tests/test_exif.py::test_extract_timestamp -v
# Expected: Returns correct datetime from EXIF

# Test 2: Extract GPS coordinates
pytest tests/test_exif.py::test_extract_gps -v
# Expected: Returns (latitude, longitude) tuple

# Test 3: Handle missing EXIF data
pytest tests/test_exif.py::test_missing_exif -v
# Expected: Returns None for missing fields, no crash

# Test 4: Handle HEIC format
pytest tests/test_exif.py::test_heic_support -v
# Expected: Extracts EXIF from HEIC files

# Test 5: Handle corrupted files
pytest tests/test_exif.py::test_corrupted_file -v
# Expected: Returns None, logs warning, no crash
```

**Test Fixtures** (create `tests/fixtures/`):
- `photo_with_gps.jpg` - Photo with GPS coordinates
- `photo_with_timestamp.jpg` - Photo with date taken
- `photo_no_exif.png` - Photo without EXIF
- `photo_heic.heic` - HEIC format photo
- `corrupted.jpg` - Corrupted image file

**Acceptance Criteria**:
- [ ] Extracts timestamp from EXIF DateTimeOriginal
- [ ] Extracts GPS coordinates and converts to decimal degrees
- [ ] Handles missing EXIF gracefully
- [ ] Supports JPEG, PNG, HEIC formats
- [ ] All unit tests pass

---

### B4: CLIP Embeddings
**Goal**: Generate image and text embeddings using CLIP model.

**Deliverables**:
- CLIP model loading and caching
- Image embedding generation (512-dim vector)
- Text embedding generation for queries

**Files to Create**:
```
Backend/photosearch/
└── core/
    ├── __init__.py
    └── clip_processor.py   # CLIP model wrapper
```

**Test Plan**:
```bash
# Test 1: Model loads successfully
pytest tests/test_clip.py::test_model_loading -v
# Expected: Model loads without errors (may take 30s first time)

# Test 2: Generate image embedding
pytest tests/test_clip.py::test_image_embedding -v
# Expected: Returns 512-dim numpy array, normalized

# Test 3: Generate text embedding
pytest tests/test_clip.py::test_text_embedding -v
# Expected: Returns 512-dim numpy array, normalized

# Test 4: Similar images have similar embeddings
pytest tests/test_clip.py::test_embedding_similarity -v
# Expected: Cosine similarity > 0.8 for similar images

# Test 5: Text-image matching
pytest tests/test_clip.py::test_text_image_match -v
# Expected: "sunset" embedding closer to sunset photo than cat photo

# Test 6: Batch processing
pytest tests/test_clip.py::test_batch_embedding -v
# Expected: Process 10 images in batch, returns 10 embeddings
```

**Performance Test**:
```bash
# Test: Embedding generation speed
pytest tests/test_clip.py::test_embedding_speed -v
# Expected: < 500ms per image on CPU, < 100ms on MPS
```

**Acceptance Criteria**:
- [ ] CLIP model loads successfully
- [ ] Image embeddings are 512-dimensional, normalized
- [ ] Text embeddings work for search queries
- [ ] Semantically similar content has high cosine similarity
- [ ] Batch processing works
- [ ] All unit tests pass

---

### B5: FAISS Vector Search
**Goal**: Implement vector similarity search using FAISS.

**Deliverables**:
- FAISS index creation and management
- Add/remove embeddings
- Similarity search with top-k results
- Index persistence (save/load)

**Files to Create**:
```
Backend/photosearch/
└── core/
    └── vector_index.py     # FAISS wrapper
```

**Test Plan**:
```bash
# Test 1: Create empty index
pytest tests/test_faiss.py::test_create_index -v
# Expected: Empty FAISS index created

# Test 2: Add embeddings
pytest tests/test_faiss.py::test_add_embeddings -v
# Expected: Embeddings added, index size increases

# Test 3: Search returns correct results
pytest tests/test_faiss.py::test_search -v
# Expected: Query returns top-k similar items with scores

# Test 4: Save and load index
pytest tests/test_faiss.py::test_persistence -v
# Expected: Index saved to file, loaded correctly

# Test 5: Remove embedding
pytest tests/test_faiss.py::test_remove_embedding -v
# Expected: Embedding removed, search doesn't return it

# Test 6: Large index performance
pytest tests/test_faiss.py::test_large_index -v
# Expected: 10k vectors, search < 50ms
```

**Integration Test**:
```bash
# Test: CLIP + FAISS integration
pytest tests/test_integration.py::test_clip_faiss_integration -v
# Expected:
#   1. Generate embeddings for 5 test images
#   2. Add to FAISS index
#   3. Search with text query "sunset"
#   4. Sunset image ranked first
```

**Acceptance Criteria**:
- [ ] FAISS index creation works
- [ ] Add, search, remove operations work correctly
- [ ] Index persists to disk and loads correctly
- [ ] Search performance < 50ms for 10k vectors
- [ ] CLIP + FAISS integration works end-to-end
- [ ] All tests pass

---

### B6: Image Captioning
**Goal**: Generate natural language descriptions using BLIP model.

**Deliverables**:
- BLIP model loading
- Caption generation for images
- Tag extraction from captions

**Files to Create**:
```
Backend/photosearch/
└── core/
    └── caption_generator.py  # BLIP wrapper
```

**Test Plan**:
```bash
# Test 1: Model loads successfully
pytest tests/test_caption.py::test_model_loading -v
# Expected: BLIP model loads without errors

# Test 2: Generate caption for image
pytest tests/test_caption.py::test_generate_caption -v
# Expected: Returns natural language description

# Test 3: Caption quality check
pytest tests/test_caption.py::test_caption_quality -v
# Expected:
#   - Sunset image → caption contains "sunset" or "sky"
#   - Beach image → caption contains "beach" or "ocean"
#   - Person image → caption contains "person" or "people"

# Test 4: Extract tags from caption
pytest tests/test_caption.py::test_extract_tags -v
# Expected: Returns list of noun phrases as tags

# Test 5: Handle various image types
pytest tests/test_caption.py::test_image_types -v
# Expected: Works for JPEG, PNG, various sizes
```

**Acceptance Criteria**:`
- [ ] BLIP model loads successfully
- [ ] Captions are grammatically correct sentences
- [ ] Captions accurately describe image content
- [ ] Tag extraction produces relevant keywords
- [ ] All tests pass

---

### B7: Location Service
**Goal**: Implement geocoding (place name → bounding box) and reverse geocoding (GPS → place name).

**Deliverables**:
- Nominatim geocoding integration
- Bounding box generation for place names
- Reverse geocoding for GPS coordinates
- Caching for geocoding results

**Files to Create**:
```
Backend/photosearch/
└── core/
    └── location_service.py  # Geocoding service
```

**Test Plan**:
```bash
# Test 1: Geocode place name
pytest tests/test_location.py::test_geocode -v
# Expected: "Hawaii" → BoundingBox with correct coordinates

# Test 2: Reverse geocode GPS
pytest tests/test_location.py::test_reverse_geocode -v
# Expected: (37.7749, -122.4194) → {"city": "San Francisco", ...}

# Test 3: Geocoding cache
pytest tests/test_location.py::test_cache -v
# Expected: Second call returns cached result, no API call

# Test 4: Handle unknown location
pytest tests/test_location.py::test_unknown_location -v
# Expected: Returns None, no crash

# Test 5: Rate limiting
pytest tests/test_location.py::test_rate_limiting -v
# Expected: Multiple requests don't exceed 1/sec

# Test 6: Bounding box contains point
pytest tests/test_location.py::test_bbox_contains -v
# Expected: Hawaii bbox contains Honolulu coordinates
```

**API Test**:
```bash
# Test: Geocode API endpoint
curl -X POST http://localhost:8765/api/v1/geocode \
  -H "Content-Type: application/json" \
  -d '{"place_name": "Hawaii"}'
# Expected: {"name": "Hawaii", "bounding_box": {...}, "center": {...}}
```

**Acceptance Criteria**:
- [ ] Geocoding returns correct bounding boxes
- [ ] Reverse geocoding returns city/state/country
- [ ] Caching reduces API calls
- [ ] Rate limiting prevents Nominatim blocks
- [ ] All tests pass

---

### B8: Full Search Integration
**Goal**: Integrate all components into complete search functionality.

**Deliverables**:
- SearchEngine class combining CLIP + FAISS + filters
- Query parser for location extraction
- Complete indexing pipeline
- All API endpoints working

**Files to Create**:
```
Backend/photosearch/
└── core/
    ├── search_engine.py    # Main search engine
    └── query_parser.py     # Query parsing
```

**Test Plan**:
```bash
# Test 1: Index single photo
pytest tests/test_search.py::test_index_single -v
# Expected: Photo indexed with embedding, metadata, caption

# Test 2: Index folder
pytest tests/test_search.py::test_index_folder -v
# Expected: All photos in folder indexed

# Test 3: Basic text search
pytest tests/test_search.py::test_text_search -v
# Expected: "sunset" returns sunset photos ranked by similarity

# Test 4: Time range filter
pytest tests/test_search.py::test_time_filter -v
# Expected: Only photos within date range returned

# Test 5: Location filter
pytest tests/test_search.py::test_location_filter -v
# Expected: "photos from Hawaii" returns only Hawaii photos

# Test 6: Combined search
pytest tests/test_search.py::test_combined_search -v
# Expected: "sunset from Hawaii in 2024" applies all filters

# Test 7: Query parsing
pytest tests/test_search.py::test_query_parsing -v
# Expected:
#   "sunset from Hawaii" → semantic: "sunset", location: "Hawaii"
#   "beach in California" → semantic: "beach", location: "California"
```

**End-to-End API Tests**:
```bash
# Test: Full indexing and search workflow
./tests/e2e/test_full_workflow.sh
# Steps:
#   1. POST /index/batch with test folder
#   2. Poll /index/status until complete
#   3. POST /search with "sunset"
#   4. Verify results contain sunset images
#   5. POST /search with location filter
#   6. Verify location filtering works
```

**Performance Tests**:
```bash
pytest tests/test_performance.py -v
# Expected:
#   - Index 100 photos < 5 minutes
#   - Search query < 200ms
#   - Memory usage < 2GB during indexing
```

**Acceptance Criteria**:
- [ ] Single photo indexing works end-to-end
- [ ] Batch folder indexing works with progress
- [ ] Text search returns relevant results
- [ ] Time range filter works correctly
- [ ] Location search with geocoding works
- [ ] Query parsing extracts location from natural language
- [ ] All API endpoints return correct responses
- [ ] Performance meets targets
- [ ] All tests pass

---

## Frontend Milestones

### F1: Project Setup
**Goal**: Create Xcode project with basic SwiftUI structure.

**Deliverables**:
- Xcode project with SwiftUI app target
- Basic app structure (App, Views, ViewModels, Services, Models)
- App icon and basic assets

**Files to Create**:
```
PhotoSearch/
├── PhotoSearch.xcodeproj
├── PhotoSearch/
│   ├── App/
│   │   └── PhotoSearchApp.swift
│   ├── Views/
│   │   └── ContentView.swift
│   ├── ViewModels/
│   ├── Services/
│   ├── Models/
│   └── Resources/
│       └── Assets.xcassets
└── PhotoSearchTests/
```

**Test Plan**:
```
# Test 1: Project builds
Cmd+B in Xcode
Expected: Build succeeds with no errors

# Test 2: App launches
Cmd+R in Xcode
Expected: App window appears with basic UI

# Test 3: Unit test target works
Cmd+U in Xcode
Expected: Test runner executes (even if no tests yet)
```

**Acceptance Criteria**:
- [ ] Xcode project builds without errors
- [ ] App launches and shows window
- [ ] Project structure follows MVVM pattern

---

### F2: API Client
**Goal**: Implement HTTP client for backend communication.

**Deliverables**:
- APIClient class with async/await
- Request/response models
- Error handling
- Backend status checking

**Files to Create**:
```
PhotoSearch/Services/
├── APIClient.swift
└── APIModels.swift

PhotoSearch/Models/
├── Photo.swift
└── SearchResult.swift
```

**Test Plan**:
```swift
// Test 1: Backend status check
func testBackendStatus() async throws {
    let client = APIClient()
    let status = try await client.getStatus()
    XCTAssertEqual(status.status, "ok")
}

// Test 2: Search request encoding
func testSearchRequestEncoding() throws {
    let request = SearchRequest(query: "sunset", topK: 20)
    let data = try JSONEncoder().encode(request)
    // Verify JSON structure
}

// Test 3: Search response decoding
func testSearchResponseDecoding() throws {
    let json = """
    {"results": [{"id": "123", "path": "/photo.jpg", "score": 0.9}]}
    """
    let response = try JSONDecoder().decode(SearchResponse.self, from: json.data(using: .utf8)!)
    XCTAssertEqual(response.results.count, 1)
}

// Test 4: Error handling
func testNetworkError() async {
    let client = APIClient(baseURL: "http://localhost:9999") // Wrong port
    do {
        _ = try await client.getStatus()
        XCTFail("Should throw error")
    } catch {
        // Expected
    }
}
```

**Manual Test**:
```
1. Start backend: uvicorn photosearch.main:app --port 8765
2. Run app
3. Check console for "Backend connected" log
```

**Acceptance Criteria**:
- [ ] APIClient can check backend status
- [ ] Search requests encode correctly
- [ ] Search responses decode correctly
- [ ] Network errors handled gracefully
- [ ] All unit tests pass

---

### F3: Photo Grid & Search UI
**Goal**: Implement main UI with search bar and photo grid.

**Deliverables**:
- SearchBar component
- PhotoGridView with LazyVGrid
- PhotoThumbnail component
- ThumbnailCache for image loading

**Files to Create**:
```
PhotoSearch/Views/
├── ContentView.swift
├── SearchBar.swift
├── PhotoGridView.swift
└── PhotoThumbnailView.swift

PhotoSearch/Services/
└── ThumbnailCache.swift

PhotoSearch/ViewModels/
└── SearchViewModel.swift
```

**Test Plan**:
```swift
// Test 1: SearchBar binding
func testSearchBarBinding() {
    let viewModel = SearchViewModel()
    viewModel.searchQuery = "sunset"
    XCTAssertEqual(viewModel.searchQuery, "sunset")
}

// Test 2: Thumbnail loading
func testThumbnailCache() async {
    let cache = ThumbnailCache()
    let url = URL(fileURLWithPath: "/path/to/test.jpg")
    let image = await cache.thumbnail(for: url, size: CGSize(width: 200, height: 200))
    XCTAssertNotNil(image)
}

// Test 3: Grid layout
// Visual test - verify in SwiftUI preview
```

**Manual Test**:
```
1. Run app
2. Verify search bar visible at top
3. Type in search bar - verify text updates
4. Verify photo grid scrolls smoothly
5. Verify thumbnails load asynchronously
```

**Acceptance Criteria**:
- [ ] Search bar accepts text input
- [ ] Photo grid displays thumbnails in grid layout
- [ ] Thumbnails load asynchronously without blocking UI
- [ ] Grid scrolls smoothly with 1000+ photos
- [ ] Empty state shows appropriate message

---

### F4: Search Integration
**Goal**: Connect search UI to backend API.

**Deliverables**:
- SearchViewModel with API integration
- Search results display
- Loading and error states
- Debounced search input

**Files to Update**:
```
PhotoSearch/ViewModels/
└── SearchViewModel.swift  # Add API integration

PhotoSearch/Views/
├── PhotoGridView.swift    # Display search results
└── SearchResultView.swift # Individual result item
```

**Test Plan**:
```swift
// Test 1: Search triggers API call
func testSearchTriggersAPI() async {
    let viewModel = SearchViewModel(apiClient: mockClient)
    viewModel.searchQuery = "sunset"
    await viewModel.search()
    XCTAssertTrue(mockClient.searchCalled)
}

// Test 2: Results update UI
func testResultsUpdateUI() async {
    let viewModel = SearchViewModel(apiClient: mockClient)
    mockClient.searchResults = [mockPhoto]
    await viewModel.search()
    XCTAssertEqual(viewModel.results.count, 1)
}

// Test 3: Debounce prevents rapid calls
func testDebounce() async {
    let viewModel = SearchViewModel(apiClient: mockClient)
    viewModel.searchQuery = "s"
    viewModel.searchQuery = "su"
    viewModel.searchQuery = "sun"
    // Wait less than debounce time
    try await Task.sleep(nanoseconds: 100_000_000) // 0.1s
    XCTAssertEqual(mockClient.searchCallCount, 0) // Not called yet
}

// Test 4: Loading state
func testLoadingState() async {
    let viewModel = SearchViewModel()
    XCTAssertFalse(viewModel.isLoading)
    // Trigger search
    Task { await viewModel.search() }
    // Immediately check loading
    XCTAssertTrue(viewModel.isLoading)
}
```

**End-to-End Test**:
```
1. Start backend with indexed test photos
2. Run app
3. Type "sunset" in search bar
4. Verify loading indicator appears
5. Verify results appear in grid
6. Verify results match search query
```

**Acceptance Criteria**:
- [ ] Search queries sent to backend
- [ ] Results displayed in photo grid
- [ ] Loading indicator during search
- [ ] Error message on failure
- [ ] Debounced input (300ms delay)
- [ ] All tests pass

---

### F5: Filters & Folder Management
**Goal**: Add time/location filters and folder selection.

**Deliverables**:
- FilterPanel with date pickers
- Location filter input
- Folder selection with NSOpenPanel
- Sidebar with folder list
- Security-Scoped Bookmarks for folder persistence

**Files to Create**:
```
PhotoSearch/Views/
├── FilterPanel.swift
├── SidebarView.swift
└── FolderListView.swift

PhotoSearch/ViewModels/
└── LibraryViewModel.swift

PhotoSearch/Services/
├── PhotoLoader.swift
└── BookmarkManager.swift
```

**Test Plan**:
```swift
// Test 1: Date filter updates search
func testDateFilter() async {
    let viewModel = SearchViewModel()
    viewModel.startDate = Date(timeIntervalSince1970: 0)
    viewModel.endDate = Date()
    await viewModel.search()
    // Verify API called with date range
}

// Test 2: Location filter
func testLocationFilter() async {
    let viewModel = SearchViewModel()
    viewModel.locationFilter = "Hawaii"
    await viewModel.search()
    // Verify API called with location
}

// Test 3: Folder selection
func testFolderSelection() {
    let loader = PhotoLoader()
    // Mock NSOpenPanel result
    let urls = loader.scanFolder(testFolderURL)
    XCTAssertGreaterThan(urls.count, 0)
}

// Test 4: Bookmark persistence
func testBookmarkPersistence() throws {
    let manager = BookmarkManager()
    try manager.saveBookmark(for: testFolderURL)
    let restored = try manager.restoreBookmarks()
    XCTAssertTrue(restored.contains(testFolderURL))
}
```

**Manual Test**:
```
1. Run app
2. Click "Add Folder" button
3. Select a folder with photos
4. Verify folder appears in sidebar
5. Set date range filter
6. Verify search results respect date filter
7. Quit and relaunch app
8. Verify folder still in sidebar (bookmark persisted)
```

**Acceptance Criteria**:
- [ ] Date range filter works
- [ ] Location filter input works
- [ ] Folder selection via NSOpenPanel
- [ ] Folders listed in sidebar
- [ ] Folder access persists across app restarts
- [ ] All tests pass

---

### F6: Indexing Progress & Polish
**Goal**: Add indexing progress UI and polish the app.

**Deliverables**:
- IndexingProgressView in toolbar
- Progress polling from backend
- Keyboard shortcuts
- Quick Look support
- Photo detail view
- Error handling and edge cases

**Files to Create**:
```
PhotoSearch/Views/
├── IndexingProgressView.swift
├── PhotoDetailView.swift
└── ErrorView.swift

PhotoSearch/ViewModels/
└── IndexingViewModel.swift
```

**Test Plan**:
```swift
// Test 1: Progress updates
func testProgressUpdates() async {
    let viewModel = IndexingViewModel(apiClient: mockClient)
    mockClient.indexProgress = IndexProgress(progress: 0.5, processed: 50, total: 100)
    await viewModel.checkProgress()
    XCTAssertEqual(viewModel.progress, 0.5)
}

// Test 2: Indexing complete notification
func testIndexingComplete() async {
    let viewModel = IndexingViewModel()
    // Simulate completion
    viewModel.onComplete = { XCTAssertTrue(true) }
    await viewModel.simulateComplete()
}

// Test 3: Keyboard shortcuts
// Manual test - verify Cmd+F focuses search
```

**Manual Test Checklist**:
```
[ ] Add folder triggers indexing
[ ] Progress bar shows in toolbar
[ ] Progress updates as indexing proceeds
[ ] "Indexing complete" notification appears
[ ] Cmd+F focuses search bar
[ ] Arrow keys navigate photo grid
[ ] Space bar opens Quick Look
[ ] Enter opens photo in Preview
[ ] Double-click opens photo detail view
[ ] Error states show user-friendly messages
[ ] Dark mode works correctly
[ ] Window resizing works correctly
```

**Acceptance Criteria**:
- [ ] Indexing progress visible in UI
- [ ] Progress updates in real-time
- [ ] Completion notification
- [ ] Keyboard shortcuts work
- [ ] Quick Look integration
- [ ] Photo detail view
- [ ] All edge cases handled gracefully
- [ ] All tests pass

---

## Integration Testing

### Full System Test
After completing all milestones, run full integration test:

```bash
# 1. Start fresh
rm -rf ~/Library/Application\ Support/PhotoSearch/

# 2. Start backend
cd Backend && source venv/bin/activate
uvicorn photosearch.main:app --port 8765

# 3. Run app from Xcode

# 4. Test workflow:
#    a. Add folder with 100+ test photos
#    b. Wait for indexing to complete
#    c. Search "sunset" → verify results
#    d. Search "photos from Hawaii" → verify location filter
#    e. Add date filter → verify results change
#    f. Quit and relaunch → verify folder persisted
#    g. Search again → verify results still work
```

### Performance Benchmarks
```
| Operation              | Target    | Measured |
|------------------------|-----------|----------|
| Index 100 photos       | < 5 min   |          |
| Index 1000 photos      | < 30 min  |          |
| Search (10k photos)    | < 200ms   |          |
| App launch             | < 2s      |          |
| Thumbnail load         | < 100ms   |          |
| Memory (10k photos)    | < 500MB   |          |
```

---

## Future Enhancements

After MVP completion:
1. **Face recognition**: Search by person (add face embeddings to FAISS)
2. **Duplicate detection**: Perceptual hashing
3. **Smart albums**: Auto-categorization
4. **iCloud sync**: Sync index across devices
5. **iOS companion app**: Share backend with iOS via Bonjour
6. **GPU acceleration**: CUDA/MPS for faster indexing

## macOS-Specific Considerations

### Permissions
- Folder access via NSOpenPanel + Security-Scoped Bookmarks
- Network access for localhost (no special permission needed)
- Full Disk Access not required (user selects folders)

### User Experience
- Native macOS design (sidebar, toolbar, split view)
- Keyboard shortcuts: Cmd+F (search), Space (Quick Look), arrows (navigate)
- Dark mode: Automatic via SwiftUI
- Menu bar icon: Optional quick search

### Code Signing & Notarization
- Sign app and bundled Python binaries
- Notarize for Gatekeeper approval
- Hardened runtime with exceptions for Python
