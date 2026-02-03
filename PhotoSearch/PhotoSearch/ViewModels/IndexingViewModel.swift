import SwiftUI
import Combine

/// View model for managing photo indexing operations.
@MainActor
class IndexingViewModel: ObservableObject {
    // MARK: - Published Properties

    /// Whether indexing is currently in progress.
    @Published var isIndexing: Bool = false

    /// Current indexing progress (0.0 to 1.0).
    @Published var progress: Double = 0.0

    /// Number of photos processed.
    @Published var processedCount: Int = 0

    /// Total number of photos to process.
    @Published var totalCount: Int = 0

    /// Current task ID being tracked.
    @Published var currentTaskId: String?

    /// Error message, if any.
    @Published var errorMessage: String?

    /// Whether indexing has completed.
    @Published var isComplete: Bool = false

    /// Errors encountered during indexing.
    @Published var errors: [String] = []

    // MARK: - Callbacks

    /// Called when indexing completes successfully.
    var onComplete: (() -> Void)?

    /// Called when indexing fails.
    var onError: ((String) -> Void)?

    // MARK: - Private Properties

    private let apiClient: any APIClientProtocol
    private var pollingTask: Task<Void, Never>?
    private let pollingInterval: TimeInterval = 1.0

    // MARK: - Initialization

    init(apiClient: any APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    deinit {
        pollingTask?.cancel()
    }

    // MARK: - Public Methods

    /// Start indexing a folder.
    /// - Parameters:
    ///   - path: The folder path to index.
    ///   - recursive: Whether to scan subdirectories.
    func startIndexing(path: String, recursive: Bool = true) async {
        isIndexing = true
        isComplete = false
        progress = 0.0
        processedCount = 0
        totalCount = 0
        errorMessage = nil
        errors = []

        do {
            let task = try await apiClient.indexFolder(path: path, recursive: recursive)
            currentTaskId = task.taskId
            totalCount = task.totalFiles ?? 0

            // Start polling for progress
            startPolling()
        } catch {
            isIndexing = false
            errorMessage = error.localizedDescription
            onError?(error.localizedDescription)
        }
    }

    /// Check progress for the current task.
    func checkProgress() async {
        guard let taskId = currentTaskId else { return }

        do {
            let status = try await apiClient.getIndexStatus(taskId: taskId)
            updateFromProgress(status)
        } catch {
            // Don't stop polling on transient errors
            print("Failed to check progress: \(error)")
        }
    }

    /// Cancel the current indexing operation.
    func cancelIndexing() {
        pollingTask?.cancel()
        pollingTask = nil
        isIndexing = false
        currentTaskId = nil
    }

    /// Reset the view model state.
    func reset() {
        cancelIndexing()
        isComplete = false
        progress = 0.0
        processedCount = 0
        totalCount = 0
        errorMessage = nil
        errors = []
    }

    /// Dismiss any error message.
    func dismissError() {
        errorMessage = nil
    }

    // MARK: - Private Methods

    private func startPolling() {
        pollingTask?.cancel()
        pollingTask = Task {
            while !Task.isCancelled && isIndexing {
                await checkProgress()
                try? await Task.sleep(nanoseconds: UInt64(pollingInterval * 1_000_000_000))
            }
        }
    }

    private func updateFromProgress(_ status: IndexProgress) {
        progress = status.progress
        processedCount = status.processed
        totalCount = status.total
        errors = status.errors

        if status.isComplete {
            handleCompletion()
        } else if status.isFailed {
            handleFailure(message: "Indexing failed")
        }
    }

    private func handleCompletion() {
        pollingTask?.cancel()
        pollingTask = nil
        isIndexing = false
        isComplete = true
        progress = 1.0

        // Post notification for completion
        NotificationCenter.default.post(name: .indexingComplete, object: nil)

        onComplete?()
    }

    private func handleFailure(message: String) {
        pollingTask?.cancel()
        pollingTask = nil
        isIndexing = false
        errorMessage = message

        onError?(message)
    }

    // MARK: - Computed Properties

    /// Progress as a percentage string.
    var progressPercent: String {
        "\(Int(progress * 100))%"
    }

    /// Progress description.
    var progressDescription: String {
        if totalCount > 0 {
            return "\(processedCount) of \(totalCount) photos"
        }
        return "Processing..."
    }

    /// Whether there are any errors.
    var hasErrors: Bool {
        !errors.isEmpty
    }
}

// MARK: - Notifications

extension Notification.Name {
    /// Posted when indexing completes.
    static let indexingComplete = Notification.Name("indexingComplete")
}
