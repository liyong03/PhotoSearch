import Foundation
import AppKit

/// Service for loading and scanning photos from folders.
class PhotoLoader {
    /// Supported image file extensions.
    static let supportedExtensions = ["jpg", "jpeg", "png", "heic", "heif", "tiff", "tif", "gif", "bmp"]

    /// Shared singleton instance.
    static let shared = PhotoLoader()

    private let fileManager = FileManager.default

    // MARK: - Folder Selection

    /// Present a folder selection dialog.
    /// - Returns: The selected folder URL, or nil if cancelled.
    @MainActor
    func requestFolderAccess() async -> URL? {
        return await withCheckedContinuation { continuation in
            let panel = NSOpenPanel()
            panel.canChooseFiles = false
            panel.canChooseDirectories = true
            panel.allowsMultipleSelection = false
            panel.message = "Select a folder containing photos to index"
            panel.prompt = "Select Folder"

            panel.begin { response in
                if response == .OK, let url = panel.url {
                    continuation.resume(returning: url)
                } else {
                    continuation.resume(returning: nil)
                }
            }
        }
    }

    // MARK: - Folder Scanning

    /// Scan a folder for image files.
    /// - Parameters:
    ///   - url: The folder URL to scan.
    ///   - recursive: Whether to scan subdirectories.
    ///   - extensions: File extensions to include. Defaults to supported image extensions.
    /// - Returns: An array of image file URLs found in the folder.
    func scanFolder(
        _ url: URL,
        recursive: Bool = true,
        extensions: [String] = PhotoLoader.supportedExtensions
    ) -> [URL] {
        var imageURLs: [URL] = []
        let lowercaseExtensions = Set(extensions.map { $0.lowercased() })

        let resourceKeys: Set<URLResourceKey> = [.isDirectoryKey, .isRegularFileKey]

        if recursive {
            guard let enumerator = fileManager.enumerator(
                at: url,
                includingPropertiesForKeys: Array(resourceKeys),
                options: [.skipsHiddenFiles, .skipsPackageDescendants]
            ) else {
                return []
            }

            for case let fileURL as URL in enumerator {
                if isImageFile(fileURL, extensions: lowercaseExtensions) {
                    imageURLs.append(fileURL)
                }
            }
        } else {
            guard let contents = try? fileManager.contentsOfDirectory(
                at: url,
                includingPropertiesForKeys: Array(resourceKeys),
                options: [.skipsHiddenFiles]
            ) else {
                return []
            }

            for fileURL in contents {
                if isImageFile(fileURL, extensions: lowercaseExtensions) {
                    imageURLs.append(fileURL)
                }
            }
        }

        return imageURLs.sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    /// Count image files in a folder without loading all URLs.
    /// - Parameters:
    ///   - url: The folder URL to scan.
    ///   - recursive: Whether to scan subdirectories.
    /// - Returns: The number of image files found.
    func countImages(in url: URL, recursive: Bool = true) -> Int {
        return scanFolder(url, recursive: recursive).count
    }

    /// Check if a URL points to a supported image file.
    /// - Parameter url: The URL to check.
    /// - Returns: `true` if the URL is a supported image file.
    func isImageFile(_ url: URL) -> Bool {
        return isImageFile(url, extensions: Set(PhotoLoader.supportedExtensions))
    }

    // MARK: - Private Methods

    private func isImageFile(_ url: URL, extensions: Set<String>) -> Bool {
        let ext = url.pathExtension.lowercased()
        guard extensions.contains(ext) else { return false }

        // Verify it's a regular file
        guard let resourceValues = try? url.resourceValues(forKeys: [.isRegularFileKey]),
              resourceValues.isRegularFile == true else {
            return false
        }

        return true
    }
}

// MARK: - Folder Info

/// Information about a user-added folder.
struct FolderInfo: Identifiable, Equatable, Hashable {
    let id: UUID
    let url: URL
    let name: String
    var photoCount: Int
    var isIndexed: Bool

    init(url: URL, photoCount: Int = 0, isIndexed: Bool = false) {
        self.id = UUID()
        self.url = url
        self.name = url.lastPathComponent
        self.photoCount = photoCount
        self.isIndexed = isIndexed
    }

    /// The folder path.
    var path: String {
        url.path
    }
}
