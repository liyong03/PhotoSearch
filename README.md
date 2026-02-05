# PhotoSearch

A native macOS photo search application that automatically indexes your photo library with AI-generated descriptions and enables powerful semantic search capabilities.

## Features

- **Native macOS Experience**: Built with SwiftUI, follows macOS design guidelines
- **AI-Powered Search**: Uses CLIP for semantic understanding - search "sunset on beach" and find matching photos
- **Smart Location Search**: Query "photos from Hawaii" automatically finds photos taken in Hawaii
- **Time Filtering**: Filter results by date range
- **Privacy-First**: All AI processing happens locally via Python backend
- **Fast Vector Search**: FAISS-powered similarity search, sub-100ms for 10k+ photos

## Architecture

SwiftUI frontend + Python backend (FastAPI + FAISS + PyTorch)

```
┌─────────────────────────┐
│   SwiftUI macOS App     │
│   (Search UI, Grid)     │
└───────────┬─────────────┘
            │ HTTP localhost:52849
┌───────────▼─────────────┐
│   Python Backend        │
│   FastAPI + CLIP + FAISS│
└─────────────────────────┘
```

See [DESIGN.md](DESIGN.md) for detailed architecture.

## Requirements

- macOS 13.0 (Ventura) or later
- Python 3.10+
- ~2GB disk space for ML models

## Installation

### 1. Clone and Setup Backend

```bash
git clone <repo-url>
cd PhotoSearch

# Setup Python backend
cd Backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Download ML models (first run only)
python -c "from transformers import CLIPModel, BlipForConditionalGeneration; CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); BlipForConditionalGeneration.from_pretrained('Salesforce/blip-image-captioning-base')"
```

### 2. Build macOS App

```bash
cd PhotoSearch
open PhotoSearch.xcodeproj
# Build and run (Cmd+R)
```

### 3. Start Backend (Development)

```bash
cd Backend
source venv/bin/activate
uvicorn photosearch.main:app --port 52849 --reload
```

## Usage

### 1. Add Photo Folders
- Click "Add Folder" or File → Add Folder (Cmd+O)
- Select folder containing photos
- Wait for indexing to complete (progress shown in toolbar)

### 2. Search Photos

**Semantic search:**
- "sunset on the beach"
- "people smiling"
- "mountain landscape"

**Location search:**
- "photos from Hawaii"
- "beach in California"
- "taken in Paris"

**Combined filters:**
- Use date picker for time range
- Combine with location: "sunset from Hawaii in 2024"

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+F | Focus search bar |
| Cmd+O | Add folder |
| Space | Quick Look |
| Arrow keys | Navigate grid |
| Enter | Open in Preview |

## Technology Stack

- **Frontend**: SwiftUI, AppKit
- **Backend**: Python, FastAPI, Uvicorn
- **ML Models**: CLIP (semantic search), BLIP (image captioning)
- **Vector Search**: FAISS
- **Database**: SQLite
- **Geocoding**: geopy + Nominatim (OpenStreetMap)

## Project Structure

```
PhotoSearch/
├── PhotoSearch/              # SwiftUI macOS app
│   ├── Views/                # UI components
│   ├── ViewModels/           # Business logic
│   ├── Services/             # API client, thumbnail cache
│   └── Models/               # Data models
├── Backend/                  # Python backend
│   ├── photosearch/
│   │   ├── api/              # FastAPI routes
│   │   ├── core/             # CLIP, FAISS, search engine
│   │   └── database/         # SQLite operations
│   └── requirements.txt
└── DESIGN.md                 # Full design document
```

## API Endpoints

The Python backend exposes a REST API at `http://localhost:52849/api/v1`.

Interactive API documentation is available at `http://localhost:52849/docs` when the backend is running.

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/status | Backend status and statistics |
| GET | /api/v1/health | Simple health check |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/search | Semantic photo search with filters |
| POST | /api/v1/geocode | Convert place name to coordinates |

### Indexing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/index | Index a single photo |
| POST | /api/v1/index/batch | Index folder (background task) |
| GET | /api/v1/index/status/{task_id} | Get indexing progress |
| DELETE | /api/v1/index/{photo_id} | Remove photo from index |
| POST | /api/v1/reindex | Rebuild entire index |

### Photos

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/photos | List indexed photos (paginated) |
| GET | /api/v1/photos/{photo_id} | Get photo details |

### Example: Search Request

```bash
curl -X POST http://localhost:52849/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "sunset on beach",
    "top_k": 20,
    "location": "Hawaii"
  }'
```

## Building a Standalone App

You can build a fully self-contained PhotoSearch.app that includes the Python backend:

### Quick Build

```bash
./scripts/build_app.sh
```

This will:
1. Build the Python backend with PyInstaller
2. Build the macOS app with Xcode
3. Embed the backend in the app bundle

### Manual Build Steps

#### 1. Build the Python Backend

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller

# Build standalone executable
pyinstaller --clean photosearch.spec
```

This creates `Backend/dist/photosearch-backend/` containing the standalone backend.

#### 2. Build the macOS App

```bash
cd PhotoSearch
xcodebuild -project PhotoSearch.xcodeproj -scheme PhotoSearch -configuration Release build
```

#### 3. Embed Backend in App Bundle

```bash
# Find the built app (usually in DerivedData)
APP_PATH="path/to/PhotoSearch.app"

# Copy backend into Resources
mkdir -p "$APP_PATH/Contents/Resources/Backend"
cp -R Backend/dist/photosearch-backend/* "$APP_PATH/Contents/Resources/Backend/"
```

### How It Works

When the app launches:
1. `BackendManager` looks for the embedded backend in `Contents/Resources/Backend/`
2. If found, it launches the backend as a subprocess
3. The backend runs on `localhost:52849`
4. When the app quits, the backend is automatically stopped

For development, if no embedded backend is found, it will look for a Python virtual environment in the `Backend/` directory and run from source.

## Development

### Running Tests

```bash
# Python backend tests (46 tests)
cd Backend
pytest

# Run specific test file
pytest tests/test_api.py -v

# Swift tests
cd PhotoSearch
xcodebuild test -project PhotoSearch.xcodeproj -scheme PhotoSearch
```

### Backend Development

```bash
cd Backend
source venv/bin/activate
uvicorn photosearch.main:app --port 52849 --reload
```

### Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| API Routes | 46 | ✅ Passing |
| Search Engine | 15 | ✅ Passing |
| CLIP Processor | 20 | ✅ Passing |
| Caption Generator | 20 | ✅ Passing |
| Location Service | 30 | ✅ Passing |
| Database | 25 | ✅ Passing |
| FAISS Index | 15 | ✅ Passing |
| Performance | 15 | ✅ Passing |
| **Total Backend** | **259** | ✅ Passing |

## Data Management

### Storage Location

PhotoSearch stores its data in `~/Library/Application Support/PhotoSearch/`:
- `photosearch.db` - SQLite database with photo metadata and captions
- `faiss.index` - Vector index for fast similarity search

### Delete and Reindex

To completely reset the index and reindex all photos:

```bash
# 1. Stop the backend server (Ctrl+C)

# 2. Delete the database and index
rm -rf ~/Library/Application\ Support/PhotoSearch/

# 3. Restart the backend
cd Backend
source venv/bin/activate
uvicorn photosearch.main:app --port 52849 --reload

# 4. Re-add your photo folders in the app
```

### Reindex via API

You can also reindex using the API:

```bash
# Delete all indexed photos and reindex a folder
curl -X POST http://localhost:52849/api/v1/index/batch \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/your/photos", "recursive": true}'

# Check indexing progress
curl http://localhost:52849/api/v1/index/status/{task_id}
```

### View Indexed Photos

```bash
# List all indexed photos
curl http://localhost:52849/api/v1/photos?limit=100

# Get total count
curl http://localhost:52849/api/v1/status
```

## Privacy

- All AI processing runs locally on your Mac
- Photos are never uploaded to any server
- Geocoding uses Nominatim (OpenStreetMap) - only place names are sent, not photo data
- Index data stored in `~/Library/Application Support/PhotoSearch/`

## Development Status

### Backend (Python) - ✅ Complete
- [x] FastAPI server with all endpoints
- [x] CLIP embeddings for semantic search
- [x] BLIP image captioning
- [x] FAISS vector index
- [x] SQLite database
- [x] Location geocoding service
- [x] Query parsing for natural language
- [x] Comprehensive test suite (100+ tests)

### Frontend (Swift) - ✅ Complete
- [x] Project structure and models
- [x] API client
- [x] Search UI with photo grid
- [x] Thumbnail caching (background loading)
- [x] Folder selection and browsing
- [x] All Photos view
- [x] Backend auto-start (embedded backend support)
- [x] App icon

## License

TBD
