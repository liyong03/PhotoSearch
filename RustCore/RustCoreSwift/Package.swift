// swift-tools-version:5.5
// The swift-tools-version declares the minimum version of Swift required to build this package.
// Swift Package: RustCoreSwift

import PackageDescription;

let package = Package(
    name: "RustCoreSwift",
    platforms: [
        .macOS(.v10_15)
    ],
    products: [
        .library(
            name: "RustCoreSwift",
            targets: ["RustCoreSwift"]
        )
    ],
    dependencies: [ ],
    targets: [
        .binaryTarget(name: "rust_coreFFI", path: "./rust_coreFFI.xcframework"),
        .target(
            name: "RustCoreSwift",
            dependencies: [
                .target(name: "rust_coreFFI")
            ]
        ),
    ]
)