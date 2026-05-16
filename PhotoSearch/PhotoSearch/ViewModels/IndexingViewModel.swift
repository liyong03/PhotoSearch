import SwiftUI
import Combine

/// Status of a single folder in the indexing queue.
enum IndexJobStatus: Equatable {
    case waiting
    case indexing
    case completed
    case failed
}

/// One folder's indexing job.
struct IndexJob: Identifiable, Equatable {
    let id = UUID()
    let path: String
    var status: IndexJobStatus = .waiting
    var taskId: String?
    var processed: Int = 0
    var total: Int = 0
    var errors: [String] = []

    var name: String { (path as NSString).lastPathComponent }
    var progress: Double { total > 0 ? Double(processed) / Double(total) : 0 }

    /// Photos successfully indexed (processed counts every attempt, including
    /// failures, so subtract the errors).
    var succeeded: Int { max(0, processed - errors.count) }
}

/// Manages photo indexing as a sequential queue of folders.
///
/// Indexing runs one folder at a time: the Rust core serialises BLIP
/// captioning behind a mutex, so concurrent folders would not actually run
/// in parallel. Instead, folders added while another is indexing are shown
/// as "waiting" and processed in order.
@MainActor
class IndexingViewModel: ObservableObject {
    // MARK: - Published State

    /// All folders in the current batch — waiting, indexing, and finished.
    @Published var jobs: [IndexJob] = []

    // MARK: - Callbacks

    /// Called when the whole queue has drained.
    var onComplete: (() -> Void)?

    // MARK: - Private

    private let apiClient: any APIClientProtocol
    private var pollingTask: Task<Void, Never>?
    private let pollingInterval: TimeInterval = 1.0

    init(apiClient: any APIClientProtocol = RustAPIClient.shared) {
        self.apiClient = apiClient
    }

    deinit {
        pollingTask?.cancel()
    }

    // MARK: - Derived State

    /// Whether any folder is queued or actively indexing.
    var isIndexing: Bool {
        jobs.contains { $0.status == .waiting || $0.status == .indexing }
    }

    /// The folder currently being indexed, if any.
    var activeJob: IndexJob? {
        jobs.first { $0.status == .indexing }
    }

    /// Number of folders still waiting to start.
    var waitingCount: Int {
        jobs.filter { $0.status == .waiting }.count
    }

    /// 1-based position of the active folder within the batch.
    var currentFolderNumber: Int {
        jobs.filter { $0.status == .completed || $0.status == .failed }.count + 1
    }

    /// Total folders in the current batch.
    var totalFolders: Int { jobs.count }

    /// Errors aggregated across the whole batch.
    var errors: [String] { jobs.flatMap { $0.errors } }
    var hasErrors: Bool { !errors.isEmpty }

    /// Photos successfully indexed across the whole batch.
    var totalSucceeded: Int { jobs.reduce(0) { $0 + $1.succeeded } }

    // MARK: - Queue

    /// Add a folder to the indexing queue. Starts immediately if the queue is
    /// idle, otherwise the folder waits behind the folders already queued.
    func enqueue(path: String) {
        // Idle queue: clear the finished jobs from the previous batch.
        if !isIndexing {
            jobs.removeAll { $0.status == .completed || $0.status == .failed }
        }
        // Skip folders already queued or in progress.
        guard !jobs.contains(where: {
            $0.path == path && ($0.status == .waiting || $0.status == .indexing)
        }) else { return }

        jobs.append(IndexJob(path: path))
        startNextIfIdle()
    }

    /// Remove every folder that has not started yet.
    func cancelPending() {
        jobs.removeAll { $0.status == .waiting }
    }

    // MARK: - Private Driver

    private func startNextIfIdle() {
        guard activeJob == nil else { return }

        guard let idx = jobs.firstIndex(where: { $0.status == .waiting }) else {
            // No folder waiting — the batch is complete.
            if jobs.contains(where: { $0.status == .completed || $0.status == .failed }) {
                NotificationCenter.default.post(name: .indexingComplete, object: nil)
                onComplete?()
            }
            return
        }

        jobs[idx].status = .indexing
        let jobId = jobs[idx].id
        let path = jobs[idx].path

        Task {
            do {
                let task = try await apiClient.indexFolder(path: path, recursive: true)
                if let i = jobs.firstIndex(where: { $0.id == jobId }) {
                    jobs[i].taskId = task.taskId
                    jobs[i].total = task.totalFiles ?? 0
                }
                startPolling(jobId: jobId)
            } catch {
                if let i = jobs.firstIndex(where: { $0.id == jobId }) {
                    jobs[i].status = .failed
                    jobs[i].errors = [error.localizedDescription]
                }
                startNextIfIdle()
            }
        }
    }

    private func startPolling(jobId: UUID) {
        pollingTask?.cancel()
        pollingTask = Task {
            while !Task.isCancelled {
                guard let i = jobs.firstIndex(where: { $0.id == jobId }),
                      let taskId = jobs[i].taskId else { break }

                do {
                    let status = try await apiClient.getIndexStatus(taskId: taskId)
                    if let i = jobs.firstIndex(where: { $0.id == jobId }) {
                        jobs[i].processed = status.processed
                        jobs[i].total = status.total
                        jobs[i].errors = status.errors
                        if status.isComplete {
                            jobs[i].status = .completed
                        } else if status.isFailed {
                            jobs[i].status = .failed
                        }
                    }
                } catch {
                    // Transient polling error — keep going.
                }

                if let i = jobs.firstIndex(where: { $0.id == jobId }),
                   jobs[i].status == .completed || jobs[i].status == .failed {
                    break
                }
                try? await Task.sleep(nanoseconds: UInt64(pollingInterval * 1_000_000_000))
            }
            // This folder finished — advance the queue.
            startNextIfIdle()
        }
    }
}

// MARK: - Notifications

extension Notification.Name {
    /// Posted when the whole indexing queue has drained.
    static let indexingComplete = Notification.Name("indexingComplete")
}
