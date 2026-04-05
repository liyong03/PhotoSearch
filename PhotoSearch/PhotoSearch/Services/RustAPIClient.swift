import Foundation
import RustCoreSwift

/// APIClient implementation backed by the Rust PhotoSearchEngine.
/// Replaces the HTTP-based APIClient with direct in-process function calls.
/// Implements the same APIClientProtocol so ViewModels need no changes.
actor RustAPIClient: APIClientProtocol {
    /// Shared singleton instance.
    static let shared: RustAPIClient = {
        let dataDir = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first!.appendingPathComponent("PhotoSearch").path
        return RustAPIClient(dataDir: dataDir)
    }()

    /// The Rust PhotoSearch engine.
    private let engine: PhotoSearchEngine?

    /// Initialization error, if any.
    private let initError: String?

    /// Active indexing tasks, keyed by task ID.
    private var indexingTasks: [String: IndexingTask] = [:]

    init(dataDir: String) {
        do {
            try FileManager.default.createDirectory(
                atPath: dataDir,
                withIntermediateDirectories: true
            )
            self.engine = try PhotoSearchEngine(dataDir: dataDir)
            self.initError = nil
        } catch {
            self.engine = nil
            self.initError = error.localizedDescription
        }
    }

    // MARK: - Status

    /// Returns the initialization error, if the engine failed to start.
    func getInitError() -> String? {
        return initError
    }

    func getStatus() async throws -> BackendStatus {
        guard let engine = engine else {
            throw APIError.backendNotAvailable
        }
        let status = engine.getStatus()
        return BackendStatus(
            status: status.isReady ? "ready" : "error",
            version: status.version,
            indexedCount: Int(status.indexedCount),
            indexSizeMb: nil
        )
    }

    // MARK: - Search

    func search(_ request: SearchRequest) async throws -> SearchResponse {
        guard let engine = engine else {
            throw APIError.backendNotAvailable
        }

        // Convert Swift SearchRequest to Rust SearchRequest
        let rustRequest = RustCoreSwift.SearchRequest(
            query: request.query,
            topK: UInt32(request.topK),
            timeStart: request.timeRange.map { Int64($0.start.timeIntervalSince1970) },
            timeEnd: request.timeRange.map { Int64($0.end.timeIntervalSince1970) },
            location: request.location,
            folderPath: request.folderPath,
            minScore: Float(request.minScore),
            keywordFilter: request.keywordFilter
        )

        let rustResults = try engine.search(request: rustRequest)

        // Convert Rust SearchResults to Swift SearchResults
        let results = rustResults.map { r in
            SearchResult(
                id: r.photoId,
                path: r.path,
                score: Double(r.score),
                description: r.description,
                timestamp: r.timestamp.map { Date(timeIntervalSince1970: TimeInterval($0)) },
                city: nil,
                state: nil,
                country: nil
            )
        }

        return SearchResponse(
            results: results,
            totalResults: results.count,
            locationResolved: nil
        )
    }

    func search(query: String, topK: Int, location: String?) async throws -> SearchResponse {
        let request = SearchRequest(query: query, topK: topK, location: location)
        return try await search(request)
    }

    // MARK: - Indexing

    func indexPhoto(path: String) async throws -> IndexResult {
        guard let engine = engine else {
            throw APIError.backendNotAvailable
        }

        let rustResult = try engine.indexPhoto(path: path)

        return IndexResult(
            id: rustResult.photoId,
            path: path,
            description: nil,
            tags: [],
            location: nil,
            timestamp: nil
        )
    }

    func indexFolder(path: String, recursive: Bool) async throws -> IndexTask {
        guard let engine = engine else {
            throw APIError.backendNotAvailable
        }

        let taskId = UUID().uuidString

        // Find image files in the folder
        let fileManager = FileManager.default
        var imageFiles: [String] = []

        if recursive {
            if let enumerator = fileManager.enumerator(atPath: path) {
                while let file = enumerator.nextObject() as? String {
                    if isImageFile(file) {
                        imageFiles.append((path as NSString).appendingPathComponent(file))
                    }
                }
            }
        } else {
            if let files = try? fileManager.contentsOfDirectory(atPath: path) {
                for file in files {
                    if isImageFile(file) {
                        imageFiles.append((path as NSString).appendingPathComponent(file))
                    }
                }
            }
        }

        // Create and start the indexing task
        let task = IndexingTask(
            taskId: taskId,
            totalFiles: imageFiles.count,
            engine: engine
        )
        indexingTasks[taskId] = task

        // Run indexing in background
        Task.detached { [weak task] in
            guard let task = task else { return }
            await task.run(files: imageFiles)
        }

        return IndexTask(
            taskId: taskId,
            status: "running",
            totalFiles: imageFiles.count
        )
    }

    func getIndexStatus(taskId: String) async throws -> IndexProgress {
        guard let task = indexingTasks[taskId] else {
            throw APIError.serverError(404, "Task not found: \(taskId)")
        }

        let state = await task.getState()

        if state.isComplete {
            indexingTasks.removeValue(forKey: taskId)
        }

        return IndexProgress(
            taskId: taskId,
            status: state.status,
            progress: state.total > 0 ? Double(state.processed) / Double(state.total) : 0,
            processed: state.processed,
            total: state.total,
            errors: state.errors
        )
    }

    // MARK: - Delete

    func deletePhoto(photoId: String) async throws {
        guard let engine = engine else {
            throw APIError.backendNotAvailable
        }
        _ = try engine.deletePhoto(photoId: photoId)
    }

    func deleteFolder(path: String) async throws -> DeleteFolderResponse {
        guard let engine = engine else {
            throw APIError.backendNotAvailable
        }
        let count = try engine.deleteFolder(folderPath: path)
        return DeleteFolderResponse(
            success: true,
            message: "Deleted \(count) photos",
            deletedCount: Int(count)
        )
    }

    // MARK: - Geocoding

    func geocode(placeName: String) async throws -> GeocodeResponse {
        guard let engine = engine else {
            throw APIError.backendNotAvailable
        }

        if let coords = engine.geocode(placeName: placeName), coords.count == 2 {
            return GeocodeResponse(
                name: placeName,
                boundingBox: nil,
                center: Coordinate(lat: coords[0], lon: coords[1])
            )
        }

        return GeocodeResponse(name: placeName, boundingBox: nil, center: nil)
    }

    // MARK: - Helpers

    private func isImageFile(_ filename: String) -> Bool {
        let ext = (filename as NSString).pathExtension.lowercased()
        return ["jpg", "jpeg", "png", "heic", "heif", "tiff", "tif", "webp", "bmp"].contains(ext)
    }
}

// MARK: - Background Indexing Task

/// Manages a background indexing operation.
actor IndexingTask {
    let taskId: String
    private let engine: PhotoSearchEngine
    private var processed: Int = 0
    private var total: Int
    private var errors: [String] = []
    private var isComplete: Bool = false

    struct State {
        let status: String
        let processed: Int
        let total: Int
        let errors: [String]
        let isComplete: Bool
    }

    init(taskId: String, totalFiles: Int, engine: PhotoSearchEngine) {
        self.taskId = taskId
        self.total = totalFiles
        self.engine = engine
    }

    func getState() -> State {
        State(
            status: isComplete ? "completed" : "running",
            processed: processed,
            total: total,
            errors: errors,
            isComplete: isComplete
        )
    }

    func run(files: [String]) async {
        for file in files {
            do {
                let result = try engine.indexPhoto(path: file)
                if !result.success {
                    if let error = result.error {
                        errors.append("\(file): \(error)")
                    }
                }
            } catch {
                errors.append("\(file): \(error.localizedDescription)")
            }
            processed += 1
            // Yield so the actor can respond to getState() progress queries
            await Task.yield()
        }
        isComplete = true
    }
}
