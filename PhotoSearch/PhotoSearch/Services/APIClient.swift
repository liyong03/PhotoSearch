import Foundation

/// Client for communicating with the PhotoSearch backend API.
actor APIClient {
    /// Shared singleton instance.
    static let shared = APIClient()

    /// Base URL for the backend API.
    private let baseURL: URL

    /// URL session for making requests.
    private let session: URLSession

    /// JSON decoder configured for the API.
    private let decoder: JSONDecoder

    /// JSON encoder configured for the API.
    private let encoder: JSONEncoder

    init(baseURL: String = "http://localhost:8765/api/v1") {
        self.baseURL = URL(string: baseURL)!
        self.session = URLSession.shared

        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601

        self.encoder = JSONEncoder()
        self.encoder.dateEncodingStrategy = .iso8601
    }

    // MARK: - Status

    /// Get backend status.
    func getStatus() async throws -> BackendStatus {
        let url = baseURL.appendingPathComponent("status")
        let (data, _) = try await session.data(from: url)
        return try decoder.decode(BackendStatus.self, from: data)
    }

    // MARK: - Search

    /// Search for photos.
    func search(_ request: SearchRequest) async throws -> SearchResponse {
        let url = baseURL.appendingPathComponent("search")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try encoder.encode(request)

        let (data, _) = try await session.data(for: urlRequest)
        return try decoder.decode(SearchResponse.self, from: data)
    }

    // MARK: - Indexing

    /// Index a single photo.
    func indexPhoto(path: String) async throws -> IndexResult {
        let url = baseURL.appendingPathComponent("index")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try encoder.encode(["photo_path": path])

        let (data, _) = try await session.data(for: urlRequest)
        return try decoder.decode(IndexResult.self, from: data)
    }

    /// Index a folder of photos.
    func indexFolder(path: String, recursive: Bool = true) async throws -> IndexTask {
        let url = baseURL.appendingPathComponent("index/batch")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let request = IndexFolderRequest(folderPath: path, recursive: recursive)
        urlRequest.httpBody = try encoder.encode(request)

        let (data, _) = try await session.data(for: urlRequest)
        return try decoder.decode(IndexTask.self, from: data)
    }

    /// Get indexing progress.
    func getIndexStatus(taskId: String) async throws -> IndexProgress {
        let url = baseURL.appendingPathComponent("index/status/\(taskId)")
        let (data, _) = try await session.data(from: url)
        return try decoder.decode(IndexProgress.self, from: data)
    }

    // MARK: - Geocoding

    /// Geocode a place name to bounding box.
    func geocode(placeName: String) async throws -> GeocodeResponse {
        let url = baseURL.appendingPathComponent("geocode")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try encoder.encode(["place_name": placeName])

        let (data, _) = try await session.data(for: urlRequest)
        return try decoder.decode(GeocodeResponse.self, from: data)
    }
}

// MARK: - API Models

/// Backend status response.
struct BackendStatus: Codable {
    let status: String
    let indexedCount: Int?
    let vectorIndexSize: Int?

    enum CodingKeys: String, CodingKey {
        case status
        case indexedCount = "indexed_count"
        case vectorIndexSize = "vector_index_size"
    }
}

/// Request to index a folder.
struct IndexFolderRequest: Codable {
    let folderPath: String
    let recursive: Bool

    enum CodingKeys: String, CodingKey {
        case folderPath = "folder_path"
        case recursive
    }
}

/// Search request.
struct SearchRequest: Codable {
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
struct TimeRange: Codable {
    let start: Date
    let end: Date
}

/// Result of indexing a single photo.
struct IndexResult: Codable {
    let id: String
    let path: String
    let description: String?
    let tags: [String]
    let location: LocationInfo?
    let timestamp: Date?
}

/// Location information.
struct LocationInfo: Codable {
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
struct IndexTask: Codable {
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
struct IndexProgress: Codable {
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
}

/// Geocode response.
struct GeocodeResponse: Codable {
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
struct Coordinate: Codable {
    let lat: Double
    let lon: Double
}

// MARK: - API Error

enum APIError: LocalizedError {
    case invalidURL
    case networkError(Error)
    case decodingError(Error)
    case serverError(Int, String?)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .decodingError(let error):
            return "Failed to decode response: \(error.localizedDescription)"
        case .serverError(let code, let message):
            return "Server error \(code): \(message ?? "Unknown error")"
        }
    }
}
