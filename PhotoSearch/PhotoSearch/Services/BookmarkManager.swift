import Foundation

/// Manages security-scoped bookmarks for folder access persistence.
class BookmarkManager {
    /// Shared singleton instance.
    static let shared = BookmarkManager()

    /// Key for storing bookmarks in UserDefaults.
    private let bookmarksKey = "savedFolderBookmarks"

    /// UserDefaults instance.
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    // MARK: - Public Methods

    /// Save a security-scoped bookmark for a folder URL.
    /// - Parameter url: The folder URL to save a bookmark for.
    /// - Throws: An error if the bookmark cannot be created.
    func saveBookmark(for url: URL) throws {
        let bookmarkData = try url.bookmarkData(
            options: .withSecurityScope,
            includingResourceValuesForKeys: nil,
            relativeTo: nil
        )

        var bookmarks = loadBookmarkData()
        bookmarks[url.path] = bookmarkData
        saveBookmarkData(bookmarks)
    }

    /// Remove a saved bookmark for a folder URL.
    /// - Parameter url: The folder URL to remove the bookmark for.
    func removeBookmark(for url: URL) {
        var bookmarks = loadBookmarkData()
        bookmarks.removeValue(forKey: url.path)
        saveBookmarkData(bookmarks)
    }

    /// Restore all saved folder URLs from bookmarks.
    /// - Returns: An array of folder URLs that were successfully restored.
    func restoreBookmarks() -> [URL] {
        let bookmarks = loadBookmarkData()
        var restoredURLs: [URL] = []

        for (path, data) in bookmarks {
            do {
                var isStale = false
                let url = try URL(
                    resolvingBookmarkData: data,
                    options: .withSecurityScope,
                    relativeTo: nil,
                    bookmarkDataIsStale: &isStale
                )

                if isStale {
                    // Bookmark is stale, try to recreate it
                    if url.startAccessingSecurityScopedResource() {
                        defer { url.stopAccessingSecurityScopedResource() }
                        try saveBookmark(for: url)
                    }
                }

                restoredURLs.append(url)
            } catch {
                // Remove invalid bookmark
                var updatedBookmarks = bookmarks
                updatedBookmarks.removeValue(forKey: path)
                saveBookmarkData(updatedBookmarks)
                print("Failed to restore bookmark for \(path): \(error)")
            }
        }

        return restoredURLs
    }

    /// Check if a bookmark exists for a URL.
    /// - Parameter url: The URL to check.
    /// - Returns: `true` if a bookmark exists for the URL.
    func hasBookmark(for url: URL) -> Bool {
        let bookmarks = loadBookmarkData()
        return bookmarks[url.path] != nil
    }

    /// Get all saved folder paths.
    /// - Returns: An array of folder paths that have saved bookmarks.
    func savedFolderPaths() -> [String] {
        return Array(loadBookmarkData().keys)
    }

    /// Start accessing a security-scoped resource.
    /// - Parameter url: The URL to access.
    /// - Returns: `true` if access was granted.
    func startAccessing(_ url: URL) -> Bool {
        return url.startAccessingSecurityScopedResource()
    }

    /// Stop accessing a security-scoped resource.
    /// - Parameter url: The URL to stop accessing.
    func stopAccessing(_ url: URL) {
        url.stopAccessingSecurityScopedResource()
    }

    // MARK: - Private Methods

    private func loadBookmarkData() -> [String: Data] {
        guard let data = defaults.data(forKey: bookmarksKey),
              let bookmarks = try? JSONDecoder().decode([String: Data].self, from: data) else {
            return [:]
        }
        return bookmarks
    }

    private func saveBookmarkData(_ bookmarks: [String: Data]) {
        guard let data = try? JSONEncoder().encode(bookmarks) else { return }
        defaults.set(data, forKey: bookmarksKey)
    }
}
