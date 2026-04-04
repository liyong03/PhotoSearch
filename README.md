# PhotoSearch

A native macOS photo search application that indexes your photo library with AI-generated descriptions and enables powerful semantic search — all running locally on your Mac.

## Features

- **AI-Powered Search**: Uses CLIP ViT-B/32 for semantic understanding — search "sunset on beach" and find matching photos
- **Smart Location Search**: Query "photos from Hawaii" automatically finds geotagged photos taken there
- **Auto-Captioning**: BLIP generates natural language descriptions and tags for every photo
- **Time Filtering**: Filter results by date range
- **Privacy-First**: All AI processing happens locally — no cloud APIs, no data leaves your Mac
- **Fast Startup**: Single-process architecture, <0.3s launch time
- **Native macOS**: Built with SwiftUI, follows macOS design guidelines

## Architecture

Single-process SwiftUI app with an embedded Rust library linked via UniFFI.

```
┌──────────────────────────────┐
│     SwiftUI macOS App        │
│     (Search UI, Grid)        │
│                              │
│  ┌────────────────────────┐  │
│  │   RustCore (UniFFI)    │  │
│  │  ┌──────┐ ┌──────┐    │  │
│  │  │ CLIP │ │ BLIP │    │  │
│  │  │(Metal)│ │      │    │  │
│  │  └──────┘ └──────┘    │  │
│  │  ┌──────┐ ┌────────┐  │  │
│  │  │Vector│ │ SQLite  │  │  │
│  │  │Index │ │(FTS5)   │  │  │
│  │  └──────┘ └────────┘  │  │
│  │  Geocoding│Synonyms   │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## Requirements

- macOS 13.0 (Ventura) or later
- Apple Silicon (M1+) recommended for Metal GPU acceleration
- Rust toolchain (for building RustCore)
- Xcode 15+
- ~2GB disk space for ML models (downloaded on first run)

## Installation

### 1. Install Rust Toolchain

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install cargo-swift
```

### 2. Clone and Build RustCore

```bash
git clone <repo-url>
cd PhotoSearch

# Build the Rust library
cd RustCore
cargo build --release --features metal

# Generate Swift package
cargo swift package -p macos -n RustCoreSwift -y
```

### 3. Build macOS App

```bash
cd PhotoSearch
open PhotoSearch.xcodeproj
# Add RustCoreSwift package dependency (File → Add Package → local path to RustCore/RustCoreSwift)
# Build and run (Cmd+R)
```

ML models are downloaded automatically from HuggingFace on first launch to `~/Library/Application Support/PhotoSearch/models/`.

## Usage

### 1. Add Photo Folders
- Click "Add Folder" or File → Add Folder (Cmd+O)
- Select a folder containing photos
- Indexing starts automatically (progress shown in toolbar)

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
- Use the date picker for time range filtering
- Location is auto-extracted from queries: "sunset from Hawaii in 2024"

### 3. Browse All Photos
- Leave the search bar empty to browse all indexed photos sorted by date (newest first)

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+F | Focus search bar |
| Cmd+O | Add folder |
| Space | Quick Look |
| Arrow keys | Navigate grid |
| Enter | Open in Preview |

## Project Structure

```
PhotoSearch/
├── RustCore/                   # Rust core library
│   ├── src/
│   │   ├── lib.rs              # PhotoSearchEngine (main API)
│   │   ├── clip/
│   │   │   ├── mod.rs          # CLIP ViT-B/32 inference
│   │   │   └── blip.rs         # BLIP image captioning
│   │   ├── search/
│   │   │   └── mod.rs          # Brute-force vector search
│   │   ├── database/
│   │   │   └── mod.rs          # SQLite + FTS5
│   │   └── services/
│   │       ├── query_parser.rs # Location extraction from queries
│   │       ├── synonyms.rs     # 166-group synonym dictionary
│   │       ├── geocoding.rs    # Nominatim forward/reverse geocoding
│   │       └── exif.rs         # EXIF metadata extraction
│   ├── tests/
│   │   ├── integration_test.rs # End-to-end pipeline tests
│   │   └── cross_validation.rs # Rust vs Python equivalence tests
│   ├── RustCoreSwift/          # Generated Swift package
│   └── Cargo.toml
├── PhotoSearch/                # SwiftUI macOS app
│   ├── Views/                  # UI components
│   ├── ViewModels/             # Business logic
│   ├── Services/               # RustAPIClient, thumbnail cache
│   └── Models/                 # Data models
├── Backend/                    # Python backend (legacy, being replaced)
├── tests/
│   └── cross_validation/       # Cross-validation test infrastructure
├── ARCHITECTURE.md             # Detailed architecture documentation
├── MIGRATION_PLAN.md           # Python → Rust migration plan
└── DESIGN.md                   # Original system design document
```

## Development

### Running Rust Tests

```bash
cd RustCore

# Run all tests (unit + integration)
cargo test

# Run only integration tests
cargo test --test integration_test

# Run cross-validation tests (requires golden outputs + model download)
cargo test --test cross_validation -- --ignored
```

### Generating Cross-Validation Golden Outputs

To verify the Rust implementation matches the Python backend:

```bash
# 1. Generate golden outputs from Python
cd tests/cross_validation
python generate_golden.py \
  --images fixtures/test_images/ \
  --output fixtures/golden_outputs/

# 2. Run cross-validation tests
cd RustCore
cargo test --test cross_validation -- --ignored
```

### Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| Synonyms (166 groups, plurals, animal expansion) | 12 | Passing |
| Query Parser | 3 | Passing |
| Database (CRUD, filters, FTS5, pagination) | 5 | Passing |
| Vector Index | 2 | Passing |
| EXIF Extraction | 2 | Passing |
| Geocoding | 2 | Passing |
| BLIP Tag Extraction | 3 | Passing |
| **Integration (full search pipeline)** | **25** | **Passing** |
| Cross-Validation (requires models) | 6 | Ignored |
| **Total** | **58** | **Passing** |

### Building for Release

```bash
cd RustCore

# Build with Metal GPU acceleration (recommended for Apple Silicon)
cargo build --release --features metal

# Build with Accelerate framework (CPU optimized)
cargo build --release --features accelerate

# Regenerate Swift package after changes
cargo swift package -p macos -n RustCoreSwift -y
```

## Data Management

### Storage Location

PhotoSearch stores data in `~/Library/Application Support/PhotoSearch/`:
- `photos.db` — SQLite database with photo metadata, captions, and tags
- `photo_index` — Binary vector index for similarity search
- `models/` — Cached ML model weights (CLIP ViT-B/32, BLIP)

### Reset Index

```bash
rm -rf ~/Library/Application\ Support/PhotoSearch/
# Relaunch the app and re-add your photo folders
```

## Privacy

- All AI processing runs locally on your Mac (CLIP, BLIP via Candle + Metal)
- Photos are never uploaded to any server
- Geocoding uses Nominatim (OpenStreetMap) — only place name strings are sent, never photo data
- All index data stays in `~/Library/Application Support/PhotoSearch/`

## License

TBD
