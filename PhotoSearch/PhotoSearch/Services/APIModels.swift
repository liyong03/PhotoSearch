import Foundation

// MARK: - Backend Status

/// Backend status response.
struct BackendStatus: Codable, Equatable {
    let status: String
    let version: String?
    let indexedCount: Int?
    let indexSizeMb: Double?

    enum CodingKeys: String, CodingKey {
        case status
        case version
        case indexedCount = "indexed_count"
        case indexSizeMb = "index_size_mb"
    }

    /// Whether the backend is ready for requests.
    var isReady: Bool {
        status == "ready" || status == "ok"
    }
}

// MARK: - Search

/// Search request.
struct SearchRequest: Codable, Equatable {
    let query: String
    let topK: Int
    let timeRange: TimeRange?
    let location: String?

    init(query: String, topK: Int = 20, timeRange: TimeRange? = nil, location: String? = nil) {
        self.query = query
        self.topK = topK
        self.timeRange = timeRange
        self.location = location
    }

    enum CodingKeys: String, CodingKey {
        case query
        case topK = "top_k"
        case timeRange = "time_range"
        case location
    }
}

/// Time range for filtering.
struct TimeRange: Codable, Equatable {
    let start: Date
    let end: Date

    init(start: Date, end: Date) {
        self.start = start
        self.end = end
    }
}

// MARK: - Indexing

/// Request to index a single photo.
struct IndexPhotoRequest: Codable, Equatable {
    let photoPath: String

    enum CodingKeys: String, CodingKey {
        case photoPath = "photo_path"
    }
}

/// Request to index a folder.
struct IndexFolderRequest: Codable, Equatable {
    let folderPath: String
    let recursive: Bool

    init(folderPath: String, recursive: Bool = true) {
        self.folderPath = folderPath
        self.recursive = recursive
    }

    enum CodingKeys: String, CodingKey {
        case folderPath = "folder_path"
        case recursive
    }
}

/// Result of indexing a single photo.
struct IndexResult: Codable, Equatable {
    let id: String
    let path: String
    let description: String?
    let tags: [String]
    let location: LocationInfo?
    let timestamp: Date?
}

/// Location information from indexing.
struct LocationInfo: Codable, Equatable {
    let city: String?
    let state: String?
    let country: String?
    let placeName: String?

    enum CodingKeys: String, CodingKey {
        case city
        case state
        case country
        case placeName = "place_name"
    }
}

/// Task for batch indexing.
struct IndexTask: Codable, Equatable {
    let taskId: String
    let status: String
    let totalFiles: Int?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case totalFiles = "total_files"
    }
}

/// Progress of an indexing task.
struct IndexProgress: Codable, Equatable {
    let taskId: String
    let status: String
    let progress: Double
    let processed: Int
    let total: Int
    let errors: [String]

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case progress
        case processed
        case total
        case errors
    }

    /// Whether indexing is complete.
    var isComplete: Bool {
        status == "completed"
    }

    /// Whether indexing failed.
    var isFailed: Bool {
        status == "failed"
    }

    /// Whether indexing is still running.
    var isRunning: Bool {
        status == "running"
    }

    /// Progress as a percentage (0-100).
    var progressPercent: Int {
        Int(progress * 100)
    }
}

// MARK: - Geocoding

/// Request to geocode a place name.
struct GeocodeRequest: Codable, Equatable {
    let placeName: String

    enum CodingKeys: String, CodingKey {
        case placeName = "place_name"
    }
}

/// Geocode response.
struct GeocodeResponse: Codable, Equatable {
    let name: String
    let boundingBox: BoundingBox?
    let center: Coordinate?

    enum CodingKeys: String, CodingKey {
        case name
        case boundingBox = "bounding_box"
        case center
    }
}

/// Geographic coordinate.
struct Coordinate: Codable, Equatable {
    let lat: Double
    let lon: Double
}

// MARK: - API Error

/// Errors that can occur when communicating with the backend API.
enum APIError: LocalizedError, Equatable {
    case invalidURL
    case networkError(String)
    case decodingError(String)
    case serverError(Int, String?)
    case backendNotAvailable
    case requestCancelled

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .networkError(let message):
            return "Network error: \(message)"
        case .decodingError(let message):
            return "Failed to decode response: \(message)"
        case .serverError(let code, let message):
            return "Server error \(code): \(message ?? "Unknown error")"
        case .backendNotAvailable:
            return "Backend server is not available. Please start the backend."
        case .requestCancelled:
            return nil  // Cancelled requests should not show error to user
        }
    }

    /// Whether this error indicates the backend is not running.
    var isConnectionError: Bool {
        switch self {
        case .networkError, .backendNotAvailable:
            return true
        default:
            return false
        }
    }

    /// Whether this error is a cancellation (should be silently ignored).
    var isCancellation: Bool {
        self == .requestCancelled
    }
}

// MARK: - Server Error Response

/// Error response from the server.
struct ServerErrorResponse: Codable {
    let detail: String?
    let message: String?

    var errorMessage: String? {
        detail ?? message
    }
}
