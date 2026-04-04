import SwiftUI
import Combine

/// View model for managing the photo library and folders.
@MainActor
class LibraryViewModel: ObservableObject {
    // MARK: - Published Properties

    /// List of user-added folders.
    @Published var folders: [FolderInfo] = []

    /// Currently selected folder, if any.
    @Published var selectedFolder: FolderInfo?

    /// Whether a folder operation is in progress.
    @Published var isLoading: Bool = false

    /// Error message, if any.
    @Published var errorMessage: String?

    // MARK: - Private Properties

    private let bookmarkManager: BookmarkManager
    private let photoLoader: PhotoLoader
    private let apiClient: any APIClientProtocol

    // MARK: - Initialization

    init(
        bookmarkManager: BookmarkManager = .shared,
        photoLoader: PhotoLoader = .shared,
        apiClient: any APIClientProtocol = RustAPIClient.shared
    ) {
        self.bookmarkManager = bookmarkManager
        self.photoLoader = photoLoader
        self.apiClient = apiClient
        loadSavedFolders()
    }

    // MARK: - Public Methods

    /// Add a new folder to the library and start indexing.
    func addFolder() async {
        guard let url = await photoLoader.requestFolderAccess() else {
            return
        }

        // Check if folder already exists
        if folders.contains(where: { $0.url == url }) {
            errorMessage = "This folder is already in your library."
            return
        }

        do {
            // Save the bookmark for persistence
            try bookmarkManager.saveBookmark(for: url)

            // Start accessing the security-scoped resource
            guard bookmarkManager.startAccessing(url) else {
                errorMessage = "Unable to access the selected folder."
                return
            }

            // Count photos in the folder
            let photoCount = photoLoader.countImages(in: url)

            // Create folder info
            let folderInfo = FolderInfo(url: url, photoCount: photoCount, isIndexed: false)
            folders.append(folderInfo)

            // Select the newly added folder
            selectedFolder = folderInfo

            // Indexing is handled by ContentView via IndexingViewModel
            // to provide progress tracking in the toolbar.

        } catch {
            errorMessage = "Failed to save folder: \(error.localizedDescription)"
        }
    }

    /// Remove a folder from the library.
    /// - Parameter folder: The folder to remove.
    /// - Parameter deleteFromIndex: Whether to also delete the photos from the search index.
    func removeFolder(_ folder: FolderInfo, deleteFromIndex: Bool = true) {
        // Remove from local bookmarks
        bookmarkManager.stopAccessing(folder.url)
        bookmarkManager.removeBookmark(for: folder.url)
        folders.removeAll { $0.id == folder.id }

        if selectedFolder?.id == folder.id {
            selectedFolder = folders.first
        }

        // Delete from backend index if requested
        if deleteFromIndex {
            Task {
                do {
                    let response = try await apiClient.deleteFolder(path: folder.path)
                    print("Deleted \(response.deletedCount) photos from index for folder: \(folder.path)")
                } catch {
                    // Log error but don't show to user - folder is already removed locally
                    print("Failed to delete folder from index: \(error.localizedDescription)")
                }
            }
        }
    }

    /// Index a folder.
    /// - Parameter folder: The folder to index.
    /// - Returns: The index task if successful.
    func indexFolder(_ folder: FolderInfo) async throws -> IndexTask {
        isLoading = true
        defer { isLoading = false }

        // Ensure we have access
        guard bookmarkManager.startAccessing(folder.url) else {
            throw LibraryError.accessDenied
        }

        let task = try await apiClient.indexFolder(path: folder.path, recursive: true)

        // Update folder status
        if let index = folders.firstIndex(where: { $0.id == folder.id }) {
            folders[index].isIndexed = true
        }

        return task
    }

    /// Refresh the photo count for a folder.
    /// - Parameter folder: The folder to refresh.
    func refreshPhotoCount(for folder: FolderInfo) {
        guard bookmarkManager.startAccessing(folder.url) else { return }

        let count = photoLoader.countImages(in: folder.url)

        if let index = folders.firstIndex(where: { $0.id == folder.id }) {
            folders[index].photoCount = count
        }
    }

    /// Dismiss any error message.
    func dismissError() {
        errorMessage = nil
    }

    // MARK: - Private Methods

    private func loadSavedFolders() {
        let urls = bookmarkManager.restoreBookmarks()

        for url in urls {
            guard bookmarkManager.startAccessing(url) else { continue }

            let photoCount = photoLoader.countImages(in: url)
            let folderInfo = FolderInfo(url: url, photoCount: photoCount, isIndexed: false)
            folders.append(folderInfo)
        }

        // Select the first folder if any
        selectedFolder = folders.first
    }
}

// MARK: - Library Errors

enum LibraryError: LocalizedError {
    case accessDenied
    case folderNotFound
    case indexingFailed(String)

    var errorDescription: String? {
        switch self {
        case .accessDenied:
            return "Access to the folder was denied. Please grant permission."
        case .folderNotFound:
            return "The folder could not be found. It may have been moved or deleted."
        case .indexingFailed(let message):
            return "Indexing failed: \(message)"
        }
    }
}
