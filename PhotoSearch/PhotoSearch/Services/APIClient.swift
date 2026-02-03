import Foundation

/// Protocol for API client operations (enables testing with mocks).
protocol APIClientProtocol: Sendable {
    func getStatus() async throws -> BackendStatus
    func isBackendReady() async -> Bool
    func search(_ request: SearchRequest) async throws -> SearchResponse
    func search(query: String, topK: Int, location: String?) async throws -> SearchResponse
    func indexPhoto(path: String) async throws -> IndexResult
    func indexFolder(path: String, recursive: Bool) async throws -> IndexTask
    func getIndexStatus(taskId: String) async throws -> IndexProgress
    func deletePhoto(photoId: String) async throws
    func geocode(placeName: String) async throws -> GeocodeResponse
}

/// Client for communicating with the PhotoSearch backend API.
/// Thread-safe actor that handles all HTTP communication with the backend.
actor APIClient: APIClientProtocol {
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

    /// Request timeout interval.
    private let timeoutInterval: TimeInterval

    // MARK: - Initialization

    init(baseURL: String = "http://localhost:8765/api/v1", timeoutInterval: TimeInterval = 30) {
        self.baseURL = URL(string: baseURL)!
        self.timeoutInterval = timeoutInterval

        // Configure URL session
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = timeoutInterval
        config.timeoutIntervalForResource = timeoutInterval * 2
        self.session = URLSession(configuration: config)

        // Configure JSON decoder
        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            // Try ISO8601 with fractional seconds
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: dateString) {
                return date
            }

            // Try ISO8601 without fractional seconds
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot decode date: \(dateString)"
            )
        }

        // Configure JSON encoder
        self.encoder = JSONEncoder()
        self.encoder.dateEncodingStrategy = .iso8601
    }

    // MARK: - Status

    /// Get backend status.
    /// - Returns: Backend status information.
    /// - Throws: `APIError` if the request fails.
    func getStatus() async throws -> BackendStatus {
        try await get("status")
    }

    /// Check if the backend is available and ready.
    /// - Returns: `true` if backend is ready, `false` otherwise.
    func isBackendReady() async -> Bool {
        do {
            let status = try await getStatus()
            return status.isReady
        } catch {
            return false
        }
    }

    // MARK: - Search

    /// Search for photos.
    /// - Parameter request: Search request with query and filters.
    /// - Returns: Search response with results.
    /// - Throws: `APIError` if the request fails.
    func search(_ request: SearchRequest) async throws -> SearchResponse {
        try await post("search", body: request)
    }

    /// Search for photos with a simple query.
    /// - Parameters:
    ///   - query: Search query string.
    ///   - topK: Maximum number of results to return.
    ///   - location: Optional location filter.
    /// - Returns: Search response with results.
    /// - Throws: `APIError` if the request fails.
    func search(query: String, topK: Int = 20, location: String? = nil) async throws -> SearchResponse {
        let request = SearchRequest(query: query, topK: topK, location: location)
        return try await search(request)
    }

    // MARK: - Indexing

    /// Index a single photo.
    /// - Parameter path: Path to the photo file.
    /// - Returns: Index result with photo information.
    /// - Throws: `APIError` if the request fails.
    func indexPhoto(path: String) async throws -> IndexResult {
        let request = IndexPhotoRequest(photoPath: path)
        return try await post("index", body: request)
    }

    /// Index a folder of photos.
    /// - Parameters:
    ///   - path: Path to the folder.
    ///   - recursive: Whether to scan subdirectories.
    /// - Returns: Index task with task ID.
    /// - Throws: `APIError` if the request fails.
    func indexFolder(path: String, recursive: Bool = true) async throws -> IndexTask {
        let request = IndexFolderRequest(folderPath: path, recursive: recursive)
        return try await post("index/batch", body: request)
    }

    /// Get indexing progress for a task.
    /// - Parameter taskId: Task ID from `indexFolder`.
    /// - Returns: Index progress information.
    /// - Throws: `APIError` if the request fails.
    func getIndexStatus(taskId: String) async throws -> IndexProgress {
        try await get("index/status/\(taskId)")
    }

    /// Delete a photo from the index.
    /// - Parameter photoId: ID of the photo to remove.
    /// - Throws: `APIError` if the request fails.
    func deletePhoto(photoId: String) async throws {
        let _: EmptyResponse = try await delete("index/\(photoId)")
    }

    // MARK: - Geocoding

    /// Geocode a place name to get its bounding box.
    /// - Parameter placeName: Name of the place to geocode.
    /// - Returns: Geocode response with coordinates.
    /// - Throws: `APIError` if the request fails.
    func geocode(placeName: String) async throws -> GeocodeResponse {
        let request = GeocodeRequest(placeName: placeName)
        return try await post("geocode", body: request)
    }

    // MARK: - Private HTTP Methods

    /// Perform a GET request.
    private func get<T: Decodable>(_ path: String) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = timeoutInterval
        return try await perform(request)
    }

    /// Perform a POST request with a JSON body.
    private func post<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = timeoutInterval
        request.httpBody = try encoder.encode(body)
        return try await perform(request)
    }

    /// Perform a DELETE request.
    private func delete<T: Decodable>(_ path: String) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.timeoutInterval = timeoutInterval
        return try await perform(request)
    }

    /// Perform an HTTP request and decode the response.
    private func perform<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse

        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            if error.code == .cannotConnectToHost || error.code == .networkConnectionLost {
                throw APIError.backendNotAvailable
            }
            throw APIError.networkError(error.localizedDescription)
        } catch {
            throw APIError.networkError(error.localizedDescription)
        }

        // Check HTTP status code
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError("Invalid response type")
        }

        // Handle error status codes
        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMessage = parseErrorMessage(from: data)
            throw APIError.serverError(httpResponse.statusCode, errorMessage)
        }

        // Handle empty response
        if data.isEmpty {
            if let empty = EmptyResponse() as? T {
                return empty
            }
        }

        // Decode response
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error.localizedDescription)
        }
    }

    /// Parse error message from server response.
    private func parseErrorMessage(from data: Data) -> String? {
        if let errorResponse = try? decoder.decode(ServerErrorResponse.self, from: data) {
            return errorResponse.errorMessage
        }
        return String(data: data, encoding: .utf8)
    }
}

// MARK: - Empty Response

/// Placeholder for responses with no body.
struct EmptyResponse: Codable {
    init() {}
}
