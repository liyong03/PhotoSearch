#!/bin/bash
#
# Rebuilds the Rust core library and regenerates the Swift package
# (xcframework + UniFFI bindings) at RustCore/RustCoreSwift/.
#
# Cargo's incremental compilation makes this cheap to call on every
# Xcode build — when no .rs files have changed, it finishes in seconds.
#
# Why this script exists instead of just calling `cargo swift package`:
# cargo-swift bundles its own `uniffi-bindgen` whose contract version may
# not match the `uniffi` crate version in our Cargo.toml. We've hit a
# crash where bindings expect contract v30 but the .a returns v29
# ("UniFFI contract version mismatch" fatal error at runtime). The fix:
# let cargo-swift build the .a and xcframework, then regenerate the Swift
# bindings using OUR own version-matched uniffi-bindgen and overwrite
# cargo-swift's bindings with the correct ones.
#
# Usage: ./scripts/build_rust.sh [--debug]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_DIR="$(dirname "$SCRIPT_DIR")/RustCore"

BUILD_MODE="--release"
TARGET_DIR="release"
if [[ "$1" == "--debug" ]]; then
    BUILD_MODE=""
    TARGET_DIR="debug"
fi

# Xcode build phases don't inherit the user shell's PATH.
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v cargo-swift >/dev/null 2>&1; then
    echo "ERROR: cargo-swift not found. Install with: cargo install cargo-swift" >&2
    exit 1
fi

cd "$RUST_DIR"

# Step 1: cargo-swift builds the staticlib + xcframework.
# (Its bindings are wrong-version; we throw them away in step 2.)
cargo swift package \
    --platforms macos \
    --name RustCoreSwift \
    -y \
    --silent \
    $BUILD_MODE

# Step 2: regenerate bindings with our version-matched uniffi-bindgen.
# `--library` mode reads UniFFI proc-macro metadata from a built cdylib.
# The cargo build for the `uniffi-bindgen` bin uses the same lockfile as
# the staticlib, so the contract version is guaranteed to match.
DYLIB="target/aarch64-apple-darwin/$TARGET_DIR/librust_core.dylib"
if [[ ! -f "$DYLIB" ]]; then
    DYLIB="target/$TARGET_DIR/librust_core.dylib"
fi
if [[ ! -f "$DYLIB" ]]; then
    echo "ERROR: cdylib not found at $DYLIB after cargo-swift build" >&2
    exit 1
fi

GEN_TMP="$(mktemp -d)"
trap 'rm -rf "$GEN_TMP"' EXIT

cargo run --quiet --bin uniffi-bindgen -- generate \
    --library "$DYLIB" \
    --language swift \
    --out-dir "$GEN_TMP"

# Step 3: overwrite cargo-swift's wrong-version bindings with ours.
# - rust_core.swift goes into the SPM Sources dir (compiled into the app).
# - rust_coreFFI.h + modulemap go into the xcframework Headers dir
#   (consumed by Swift's clang module import).
SWIFT_DEST="RustCoreSwift/Sources/RustCoreSwift/rust_core.swift"
XCF_HEADERS="RustCoreSwift/rust_coreFFI.xcframework/macos-arm64_x86_64/Headers/rust_coreFFI"

cp "$GEN_TMP/rust_core.swift"        "$SWIFT_DEST"
cp "$GEN_TMP/rust_coreFFI.h"         "$XCF_HEADERS/rust_coreFFI.h"
cp "$GEN_TMP/rust_coreFFI.modulemap" "$XCF_HEADERS/module.modulemap"
