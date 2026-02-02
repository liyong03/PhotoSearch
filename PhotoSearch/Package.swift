// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PhotoSearch",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "PhotoSearch", targets: ["PhotoSearch"])
    ],
    targets: [
        .executableTarget(
            name: "PhotoSearch",
            path: "PhotoSearch",
            resources: [
                .process("Resources")
            ]
        ),
        .testTarget(
            name: "PhotoSearchTests",
            dependencies: ["PhotoSearch"],
            path: "PhotoSearchTests"
        )
    ]
)
