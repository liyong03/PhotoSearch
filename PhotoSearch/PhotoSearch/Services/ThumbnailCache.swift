import AppKit
import SwiftUI

/// Cache for photo thumbnails with async loading.
/// Thread-safe singleton that manages thumbnail generation and caching.
@MainActor
final class ThumbnailCache: ObservableObject {
    /// Shared singleton instance.
    static let shared = ThumbnailCache()

    /// In-memory cache for thumbnails.
    private let cache = NSCache<NSString, NSImage>()

    /// Set of paths currently being loaded.
    private var loadingPaths = Set<String>()

    /// Default thumbnail size.
    private let defaultSize = CGSize(width: 300, height: 300)

    /// Maximum cache size in number of items.
    private let maxCacheSize = 500

    private init() {
        cache.countLimit = maxCacheSize
    }

    // MARK: - Public Methods

    /// Get a thumbnail for the given path, loading it if necessary.
    /// - Parameters:
    ///   - path: File path to the image.
    ///   - size: Desired thumbnail size.
    /// - Returns: Thumbnail image or nil if not yet loaded.
    func thumbnail(for path: String, size: CGSize? = nil) -> NSImage? {
        let cacheKey = cacheKey(for: path, size: size ?? defaultSize)

        // Return cached thumbnail if available
        if let cached = cache.object(forKey: cacheKey as NSString) {
            return cached
        }

        // Start loading if not already in progress
        if !loadingPaths.contains(path) {
            loadThumbnail(path: path, size: size ?? defaultSize)
        }

        return nil
    }

    /// Get a cached thumbnail synchronously without triggering a load.
    /// - Parameter cacheKey: The cache key string.
    /// - Returns: Cached thumbnail or nil.
    func getCachedThumbnail(forKey cacheKey: String) -> NSImage? {
        return cache.object(forKey: cacheKey as NSString)
    }

    /// Load a thumbnail in background (can be called from any thread).
    /// - Parameters:
    ///   - path: File path to the image.
    ///   - size: Desired thumbnail size.
    /// - Returns: Thumbnail image.
    nonisolated func loadThumbnailInBackground(path: String, size: CGSize? = nil) async -> NSImage? {
        let targetSize = size ?? CGSize(width: 300, height: 300)
        let cacheKey = "\(path)_\(Int(targetSize.width))x\(Int(targetSize.height))"

        // Check cache on main actor
        if let cached = await MainActor.run(body: { self.cache.object(forKey: cacheKey as NSString) }) {
            return cached
        }

        // Generate thumbnail (heavy work, runs on current background thread)
        guard let thumbnail = generateThumbnailSync(path: path, size: targetSize) else {
            return nil
        }

        // Cache on main actor
        await MainActor.run {
            self.cache.setObject(thumbnail, forKey: cacheKey as NSString)
        }

        return thumbnail
    }

    /// Synchronous thumbnail generation (for use on background threads).
    private nonisolated func generateThumbnailSync(path: String, size: CGSize) -> NSImage? {
        let url = URL(fileURLWithPath: path)

        // Try CGImageSource first (most efficient)
        if let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil) {
            let maxDimension = max(size.width, size.height) * 2 // Retina

            let options: [CFString: Any] = [
                kCGImageSourceThumbnailMaxPixelSize: maxDimension,
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: true,
                kCGImageSourceShouldCache: false
            ]

            if let cgImage = CGImageSourceCreateThumbnailAtIndex(imageSource, 0, options as CFDictionary) {
                return NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
            }
        }

        // Fallback to NSImage
        guard let image = NSImage(contentsOf: url) else {
            return nil
        }

        let ratio = min(size.width / image.size.width, size.height / image.size.height)
        let newSize = CGSize(
            width: image.size.width * ratio,
            height: image.size.height * ratio
        )

        let thumbnail = NSImage(size: newSize)
        thumbnail.lockFocus()
        image.draw(
            in: NSRect(origin: .zero, size: newSize),
            from: NSRect(origin: .zero, size: image.size),
            operation: .copy,
            fraction: 1.0
        )
        thumbnail.unlockFocus()

        return thumbnail
    }

    /// Asynchronously load a thumbnail.
    /// - Parameters:
    ///   - path: File path to the image.
    ///   - size: Desired thumbnail size.
    /// - Returns: Thumbnail image.
    func loadThumbnail(path: String, size: CGSize? = nil) async -> NSImage? {
        let targetSize = size ?? defaultSize
        let cacheKey = cacheKey(for: path, size: targetSize)

        // Return cached thumbnail if available
        if let cached = cache.object(forKey: cacheKey as NSString) {
            return cached
        }

        // Generate thumbnail
        guard let thumbnail = await generateThumbnail(path: path, size: targetSize) else {
            return nil
        }

        // Cache and return
        cache.setObject(thumbnail, forKey: cacheKey as NSString)
        return thumbnail
    }

    /// Preload thumbnails for multiple paths.
    /// - Parameter paths: Array of file paths to preload.
    func preloadThumbnails(for paths: [String]) {
        for path in paths {
            if cache.object(forKey: cacheKey(for: path, size: defaultSize) as NSString) == nil {
                loadThumbnail(path: path, size: defaultSize)
            }
        }
    }

    /// Clear all cached thumbnails.
    func clearCache() {
        cache.removeAllObjects()
        loadingPaths.removeAll()
    }

    /// Remove a specific thumbnail from cache.
    /// - Parameter path: File path to remove.
    func removeThumbnail(for path: String) {
        let cacheKey = cacheKey(for: path, size: defaultSize)
        cache.removeObject(forKey: cacheKey as NSString)
    }

    // MARK: - Private Methods

    private func cacheKey(for path: String, size: CGSize) -> String {
        "\(path)_\(Int(size.width))x\(Int(size.height))"
    }

    private func loadThumbnail(path: String, size: CGSize) {
        loadingPaths.insert(path)

        Task.detached(priority: .background) { [weak self] in
            let thumbnail = await self?.generateThumbnail(path: path, size: size)

            await MainActor.run { [weak self] in
                guard let self = self, let thumbnail = thumbnail else { return }

                let cacheKey = self.cacheKey(for: path, size: size)
                self.cache.setObject(thumbnail, forKey: cacheKey as NSString)
                self.loadingPaths.remove(path)
                self.objectWillChange.send()
            }
        }
    }

    private func generateThumbnail(path: String, size: CGSize) async -> NSImage? {
        let url = URL(fileURLWithPath: path)

        // Try to use CGImageSource for better performance with large images
        if let thumbnail = await generateThumbnailWithCGImage(url: url, size: size) {
            return thumbnail
        }

        // Fallback to NSImage
        return await generateThumbnailWithNSImage(url: url, size: size)
    }

    private func generateThumbnailWithCGImage(url: URL, size: CGSize) async -> NSImage? {
        guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil) else {
            return nil
        }

        let maxDimension = max(size.width, size.height) * 2 // Account for Retina

        let options: [CFString: Any] = [
            kCGImageSourceThumbnailMaxPixelSize: maxDimension,
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true
        ]

        guard let cgImage = CGImageSourceCreateThumbnailAtIndex(imageSource, 0, options as CFDictionary) else {
            return nil
        }

        return NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
    }

    private func generateThumbnailWithNSImage(url: URL, size: CGSize) async -> NSImage? {
        guard let image = NSImage(contentsOf: url) else {
            return nil
        }

        let ratio = min(size.width / image.size.width, size.height / image.size.height)
        let newSize = CGSize(
            width: image.size.width * ratio,
            height: image.size.height * ratio
        )

        let thumbnail = NSImage(size: newSize)
        thumbnail.lockFocus()
        image.draw(
            in: NSRect(origin: .zero, size: newSize),
            from: NSRect(origin: .zero, size: image.size),
            operation: .copy,
            fraction: 1.0
        )
        thumbnail.unlockFocus()

        return thumbnail
    }
}

// MARK: - Thumbnail Loader for SwiftUI

/// Observable thumbnail loader for use in SwiftUI views.
@MainActor
class ThumbnailLoader: ObservableObject {
    @Published var image: NSImage?
    @Published var isLoading: Bool = false

    private var loadedPath: String?
    private var loadTask: Task<Void, Never>?

    func load(from path: String, size: CGSize? = nil) {
        // Don't reload if already loaded for this path
        if loadedPath == path && image != nil {
            return
        }

        // Cancel any existing load task
        loadTask?.cancel()
        loadedPath = path

        // Check cache first (synchronous, on main thread)
        let targetSize = size ?? CGSize(width: 300, height: 300)
        let cacheKey = "\(path)_\(Int(targetSize.width))x\(Int(targetSize.height))"
        if let cached = ThumbnailCache.shared.getCachedThumbnail(forKey: cacheKey) {
            self.image = cached
            return
        }

        // Load asynchronously on background thread
        isLoading = true
        loadTask = Task {
            // Run heavy image loading on background thread
            let thumbnail = await Task.detached(priority: .utility) {
                await ThumbnailCache.shared.loadThumbnailInBackground(path: path, size: size)
            }.value

            // Check if task was cancelled or path changed
            guard !Task.isCancelled, self.loadedPath == path else { return }

            // Update UI on main thread (automatic since class is @MainActor)
            self.image = thumbnail
            self.isLoading = false
        }
    }

    func cancel() {
        loadTask?.cancel()
        loadTask = nil
        loadedPath = nil
    }
}

// MARK: - NSImage Extension

extension NSImage {
    /// Create a thumbnail of the image with the specified maximum size.
    func thumbnailImage(maxSize: CGSize) -> NSImage {
        let ratio = min(maxSize.width / size.width, maxSize.height / size.height)
        let newSize = CGSize(width: size.width * ratio, height: size.height * ratio)

        let thumbnail = NSImage(size: newSize)
        thumbnail.lockFocus()
        draw(
            in: NSRect(origin: .zero, size: newSize),
            from: NSRect(origin: .zero, size: size),
            operation: .copy,
            fraction: 1.0
        )
        thumbnail.unlockFocus()
        return thumbnail
    }
}
