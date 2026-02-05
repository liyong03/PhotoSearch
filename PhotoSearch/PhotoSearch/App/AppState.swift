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

    /// Whether the embedded backend is being used.
    @Published var isUsingEmbeddedBackend: Bool = false

    private var cancellables = Set<AnyCancellable>()
    private let apiClient = APIClient.shared
    private let backendManager = BackendManager.shared
    private var healthCheckTimer: Timer?

    init() {
        // Start backend and check status
        Task {
            await startBackendAndCheck()
        }
    }

    /// Start the embedded backend and wait for it to be ready.
    func startBackendAndCheck() async {
        // Try to start the embedded backend
        backendManager.start()
        isUsingEmbeddedBackend = backendManager.isRunning

        // Wait for backend to be ready (with retries)
        for attempt in 1...10 {
            try? await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds

            if await backendManager.checkHealth() {
                await checkBackendStatus()
                if isBackendReady {
                    startHealthCheckTimer()
                    return
                }
            }

            if attempt == 10 {
                errorMessage = "Failed to start backend. Please try restarting the app."
            }
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
            if isUsingEmbeddedBackend {
                errorMessage = "Backend stopped unexpectedly. Restarting..."
                await restartBackend()
            } else {
                errorMessage = "Backend not available. Please start the backend server."
            }
        }
    }

    /// Restart the embedded backend.
    func restartBackend() async {
        backendManager.restart()
        try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
        await checkBackendStatus()
    }

    /// Stop the embedded backend.
    func stopBackend() {
        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        backendManager.stop()
    }

    /// Dismiss any error message.
    func dismissError() {
        errorMessage = nil
    }

    // MARK: - Private Methods

    private func startHealthCheckTimer() {
        healthCheckTimer = Timer.scheduledTimer(withTimeInterval: 30.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.checkBackendStatus()
            }
        }
    }
}
