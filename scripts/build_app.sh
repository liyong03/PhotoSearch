#!/bin/bash
#
# Build script for PhotoSearch app with embedded backend.
#
# This script:
# 1. Builds the Python backend using PyInstaller
# 2. Builds the macOS app using Xcode
# 3. Copies the backend into the app bundle
# 4. Moves the final app to the project directory
#
# Usage: ./scripts/build_app.sh [--release]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/Backend"
IOS_DIR="$PROJECT_DIR/PhotoSearch"
BUILD_DIR="$PROJECT_DIR/build"

# Parse arguments
RELEASE_BUILD=false
if [[ "$1" == "--release" ]]; then
    RELEASE_BUILD=true
fi

echo "=========================================="
echo "Building PhotoSearch App"
echo "=========================================="
echo "Project directory: $PROJECT_DIR"
echo "Release build: $RELEASE_BUILD"
echo ""

# Step 1: Build the Python backend
echo "Step 1: Building Python backend..."
echo "------------------------------------------"

cd "$BACKEND_DIR"

# Ensure virtual environment exists
if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv and install dependencies
source .venv/bin/activate
pip install -q -r requirements.txt
pip install -q pyinstaller

# Build with PyInstaller
echo "Running PyInstaller..."
pyinstaller --clean --noconfirm photosearch.spec

# Check if build succeeded
if [[ ! -d "dist/photosearch-backend" ]]; then
    echo "ERROR: PyInstaller build failed!"
    exit 1
fi

echo "Backend build complete: dist/photosearch-backend"
echo ""

# Step 2: Build the macOS app
echo "Step 2: Building macOS app..."
echo "------------------------------------------"

cd "$IOS_DIR"

# Determine build configuration
if [[ "$RELEASE_BUILD" == true ]]; then
    CONFIGURATION="Release"
else
    CONFIGURATION="Debug"
fi

# Clean any previous build artifacts with permission issues
rm -rf "$BUILD_DIR" 2>/dev/null || true

# Build with xcodebuild
xcodebuild -project PhotoSearch.xcodeproj \
    -scheme PhotoSearch \
    -configuration "$CONFIGURATION" \
    -derivedDataPath "$BUILD_DIR" \
    ONLY_ACTIVE_ARCH=YES \
    build

# Find the built app
APP_PATH=$(find "$BUILD_DIR" -name "PhotoSearch.app" -type d | head -1)

if [[ -z "$APP_PATH" ]]; then
    echo "ERROR: Could not find built app!"
    exit 1
fi

echo "App built at: $APP_PATH"
echo ""

# Step 3: Copy backend into app bundle
echo "Step 3: Embedding backend in app bundle..."
echo "------------------------------------------"

BACKEND_DEST="$APP_PATH/Contents/Resources/Backend"
mkdir -p "$BACKEND_DEST"

# Copy the PyInstaller output
cp -R "$BACKEND_DIR/dist/photosearch-backend/"* "$BACKEND_DEST/"

echo "Backend copied to: $BACKEND_DEST"
echo ""

# Step 4: Move app to project directory
echo "Step 4: Moving app to project directory..."
echo "------------------------------------------"

FINAL_APP_PATH="$PROJECT_DIR/PhotoSearch.app"

# Remove existing app if present
if [[ -d "$FINAL_APP_PATH" ]]; then
    echo "Removing existing app..."
    rm -rf "$FINAL_APP_PATH"
fi

# Copy the built app to project directory
cp -R "$APP_PATH" "$FINAL_APP_PATH"
echo "App copied to: $FINAL_APP_PATH"
echo ""

# Step 5: Code sign (optional, for distribution)
if [[ "$RELEASE_BUILD" == true ]]; then
    echo "Step 5: Code signing..."
    echo "------------------------------------------"
    
    # You would need to set your signing identity here
    # SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
    # codesign --force --deep --sign "$SIGNING_IDENTITY" "$FINAL_APP_PATH"
    
    echo "NOTE: Code signing skipped. Set SIGNING_IDENTITY in the script for distribution builds."
    echo ""
fi

# Clean up build directory (optional)
# rm -rf "$BUILD_DIR"

# Done!
echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "App location: $FINAL_APP_PATH"
echo ""
echo "To run the app:"
echo "  open \"$FINAL_APP_PATH\""
echo ""

# Optionally open the app
read -p "Open the app now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    open "$FINAL_APP_PATH"
fi
