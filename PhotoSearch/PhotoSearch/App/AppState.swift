import SwiftUI
import Combine

/// Global application state shared across views.
@MainActor
class AppState: ObservableObject {
    /// Whether the backend is connected and ready.
    @Published var isBackendReady: Bool = false

    /// Error message to display, if any.
    @Published var errorMessage: String?

    /// Whether an indexing operation is in progress.
    @Published var isIndexing: Bool = false

    /// Progress of current indexing operation (0.0 to 1.0).
    @Published var indexingProgress: Double = 0.0

    /// Total number of indexed photos.
    @Published var indexedCount: Int = 0

    private var cancellables = Set<AnyCancellable>()
    private let apiClient = APIClient.shared

    init() {
        // Check backend status on init
        Task {
            await checkBackendStatus()
        }
    }

    /// Check if the backend is running and ready.
    func checkBackendStatus() async {
        do {
            let status = try await apiClient.getStatus()
            isBackendReady = status.status == "ready" || status.status == "ok"
            indexedCount = status.indexedCount ?? 0
            errorMessage = nil
        } catch {
            isBackendReady = false
            errorMessage = "Backend not available. Please start the backend server."
        }
    }

    /// Dismiss any error message.
    func dismissError() {
        errorMessage = nil
    }
}
