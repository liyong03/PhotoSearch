import SwiftUI
import Combine

/// Global application state shared across views.
@MainActor
class AppState: ObservableObject {
    /// Error message to display, if any.
    @Published var errorMessage: String?

    /// Whether an indexing operation is in progress.
    @Published var isIndexing: Bool = false

    /// Progress of current indexing operation (0.0 to 1.0).
    @Published var indexingProgress: Double = 0.0

    /// Total number of indexed photos.
    @Published var indexedCount: Int = 0

    private let apiClient = RustAPIClient.shared

    init() {
        Task {
            await refreshStatus()
        }
    }

    /// Refresh the indexed photo count from the engine.
    func refreshStatus() async {
        do {
            let status = try await apiClient.getStatus()
            indexedCount = status.indexedCount ?? 0
            errorMessage = nil
        } catch {
            if let initError = await apiClient.getInitError() {
                errorMessage = "Engine failed to start: \(initError)"
            } else {
                errorMessage = "Engine error: \(error.localizedDescription)"
            }
        }
    }

    /// Dismiss any error message.
    func dismissError() {
        errorMessage = nil
    }
}
