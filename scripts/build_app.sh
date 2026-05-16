#!/bin/bash
#
# Build script for PhotoSearch (Rust core + SwiftUI app).
#
# Pipeline:
#   1. Rebuild the Rust library and regenerate the xcframework + Swift bindings.
#   2. Regenerate the Xcode project from project.yml via XcodeGen.
#   3. Build the macOS app with xcodebuild.
#   4. Copy the built .app to the project root.
#
# Note: the Rust rebuild also runs as a pre-build phase inside Xcode (see
# PhotoSearch/project.yml), so building from Xcode directly will keep Rust
# in sync without invoking this script.
#
# Usage: ./scripts/build_app.sh [--release]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR="$PROJECT_DIR/PhotoSearch"
BUILD_DIR="$PROJECT_DIR/build"

RELEASE_BUILD=false
if [[ "$1" == "--release" ]]; then
    RELEASE_BUILD=true
fi

if [[ "$RELEASE_BUILD" == true ]]; then
    CONFIGURATION="Release"
    RUST_FLAG=""
else
    CONFIGURATION="Debug"
    RUST_FLAG="--debug"
fi

echo "=========================================="
echo "Building PhotoSearch ($CONFIGURATION)"
echo "=========================================="
echo ""

# Step 1: Rust core
echo "Step 1: Building Rust core..."
echo "------------------------------------------"
"$SCRIPT_DIR/build_rust.sh" $RUST_FLAG
echo ""

# Step 2: Regenerate Xcode project
echo "Step 2: Regenerating Xcode project..."
echo "------------------------------------------"
if ! command -v xcodegen >/dev/null 2>&1; then
    echo "ERROR: xcodegen not found. Install with: brew install xcodegen" >&2
    exit 1
fi
(cd "$APP_DIR" && xcodegen generate)
echo ""

# Step 3: Build the app
echo "Step 3: Building macOS app..."
echo "------------------------------------------"
rm -rf "$BUILD_DIR" 2>/dev/null || true

xcodebuild \
    -project "$APP_DIR/PhotoSearch.xcodeproj" \
    -scheme PhotoSearch \
    -configuration "$CONFIGURATION" \
    -derivedDataPath "$BUILD_DIR" \
    ONLY_ACTIVE_ARCH=YES \
    build

APP_PATH=$(find "$BUILD_DIR" -name "PhotoSearch.app" -type d | head -1)
if [[ -z "$APP_PATH" ]]; then
    echo "ERROR: Could not find built app!" >&2
    exit 1
fi
echo "App built at: $APP_PATH"
echo ""

# Step 4: Copy app to project root
echo "Step 4: Copying app to project root..."
echo "------------------------------------------"
FINAL_APP_PATH="$PROJECT_DIR/PhotoSearch.app"
if [[ -d "$FINAL_APP_PATH" ]]; then
    rm -rf "$FINAL_APP_PATH"
fi
cp -R "$APP_PATH" "$FINAL_APP_PATH"
echo "App copied to: $FINAL_APP_PATH"
echo ""

if [[ "$RELEASE_BUILD" == true ]]; then
    echo "Step 5: Code signing..."
    echo "------------------------------------------"
    # SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
    # codesign --force --deep --sign "$SIGNING_IDENTITY" "$FINAL_APP_PATH"
    echo "NOTE: Code signing skipped. Set SIGNING_IDENTITY in the script for distribution builds."
    echo ""
fi

echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "App location: $FINAL_APP_PATH"
echo ""
echo "To run the app:"
echo "  open \"$FINAL_APP_PATH\""
echo ""

read -p "Open the app now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    open "$FINAL_APP_PATH"
fi
