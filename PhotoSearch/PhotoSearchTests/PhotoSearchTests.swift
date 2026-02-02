import XCTest
@testable import PhotoSearch

final class PhotoSearchTests: XCTestCase {

    // MARK: - Search Result Decoding Tests

    func testSearchResultDecoding() throws {
        let json = """
        {
            "id": "123",
            "path": "/path/to/photo.jpg",
            "score": 0.95,
            "description": "A sunset over the ocean",
            "city": "Honolulu",
            "state": "Hawaii",
            "country": "USA"
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let result = try decoder.decode(SearchResult.self, from: data)

        XCTAssertEqual(result.id, "123")
        XCTAssertEqual(result.path, "/path/to/photo.jpg")
        XCTAssertEqual(result.score, 0.95)
        XCTAssertEqual(result.description, "A sunset over the ocean")
        XCTAssertEqual(result.city, "Honolulu")
        XCTAssertEqual(result.state, "Hawaii")
        XCTAssertEqual(result.country, "USA")
    }

    func testSearchResultDecodingMinimalFields() throws {
        let json = """
        {
            "id": "456",
            "path": "/photo.jpg"
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let result = try decoder.decode(SearchResult.self, from: data)

        XCTAssertEqual(result.id, "456")
        XCTAssertEqual(result.path, "/photo.jpg")
        XCTAssertNil(result.score)
        XCTAssertNil(result.description)
        XCTAssertNil(result.city)
    }

    // MARK: - Search Response Decoding Tests

    func testSearchResponseDecoding() throws {
        let json = """
        {
            "results": [
                {"id": "1", "path": "/a.jpg", "score": 0.9},
                {"id": "2", "path": "/b.jpg", "score": 0.8}
            ],
            "total_results": 2
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let response = try decoder.decode(SearchResponse.self, from: data)

        XCTAssertEqual(response.results.count, 2)
        XCTAssertEqual(response.totalResults, 2)
        XCTAssertEqual(response.results[0].id, "1")
        XCTAssertEqual(response.results[0].score, 0.9)
        XCTAssertNil(response.locationResolved)
    }

    func testSearchResponseWithLocationResolved() throws {
        let json = """
        {
            "results": [{"id": "1", "path": "/a.jpg"}],
            "total_results": 1,
            "location_resolved": {
                "query": "Hawaii",
                "bounding_box": {
                    "min_lat": 18.91,
                    "max_lat": 22.24,
                    "min_lon": -160.25,
                    "max_lon": -154.81
                }
            }
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let response = try decoder.decode(SearchResponse.self, from: data)

        XCTAssertNotNil(response.locationResolved)
        XCTAssertEqual(response.locationResolved?.query, "Hawaii")
        XCTAssertNotNil(response.locationResolved?.boundingBox)
        XCTAssertEqual(response.locationResolved?.boundingBox?.minLat, 18.91)
    }

    // MARK: - Search Request Encoding Tests

    func testSearchRequestEncoding() throws {
        let request = SearchRequest(query: "sunset", topK: 20, location: "Hawaii")

        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = String(data: data, encoding: .utf8)!

        XCTAssertTrue(json.contains("\"query\":\"sunset\""))
        XCTAssertTrue(json.contains("\"top_k\":20"))
        XCTAssertTrue(json.contains("\"location\":\"Hawaii\""))
    }

    func testSearchRequestEncodingDefaults() throws {
        let request = SearchRequest(query: "beach")

        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = String(data: data, encoding: .utf8)!

        XCTAssertTrue(json.contains("\"query\":\"beach\""))
        XCTAssertTrue(json.contains("\"top_k\":20")) // default value
    }

    // MARK: - Backend Status Decoding Tests

    func testBackendStatusDecoding() throws {
        let json = """
        {
            "status": "ready",
            "indexed_count": 1500,
            "vector_index_size": 1500
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let status = try decoder.decode(BackendStatus.self, from: data)

        XCTAssertEqual(status.status, "ready")
        XCTAssertEqual(status.indexedCount, 1500)
        XCTAssertEqual(status.vectorIndexSize, 1500)
        XCTAssertTrue(status.isReady)
    }

    func testBackendStatusNotReady() throws {
        let json = """
        {
            "status": "initializing"
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let status = try decoder.decode(BackendStatus.self, from: data)

        XCTAssertEqual(status.status, "initializing")
        XCTAssertFalse(status.isReady)
    }

    // MARK: - Bounding Box Tests

    func testBoundingBoxDecoding() throws {
        let json = """
        {
            "min_lat": 18.91,
            "max_lat": 22.24,
            "min_lon": -160.25,
            "max_lon": -154.81
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let bbox = try decoder.decode(BoundingBox.self, from: data)

        XCTAssertEqual(bbox.minLat, 18.91)
        XCTAssertEqual(bbox.maxLat, 22.24)
        XCTAssertEqual(bbox.minLon, -160.25)
        XCTAssertEqual(bbox.maxLon, -154.81)
    }

    func testBoundingBoxContains() throws {
        let bbox = BoundingBox(minLat: 18.91, maxLat: 22.24, minLon: -160.25, maxLon: -154.81)

        // Honolulu coordinates (inside Hawaii)
        XCTAssertTrue(bbox.contains(latitude: 21.3069, longitude: -157.8583))

        // San Francisco coordinates (outside Hawaii)
        XCTAssertFalse(bbox.contains(latitude: 37.7749, longitude: -122.4194))
    }

    // MARK: - Index Progress Tests

    func testIndexProgressDecoding() throws {
        let json = """
        {
            "task_id": "abc123",
            "status": "running",
            "progress": 0.75,
            "processed": 75,
            "total": 100,
            "errors": ["error1"]
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let progress = try decoder.decode(IndexProgress.self, from: data)

        XCTAssertEqual(progress.taskId, "abc123")
        XCTAssertEqual(progress.status, "running")
        XCTAssertEqual(progress.progress, 0.75)
        XCTAssertEqual(progress.processed, 75)
        XCTAssertEqual(progress.total, 100)
        XCTAssertEqual(progress.errors, ["error1"])
        XCTAssertTrue(progress.isRunning)
        XCTAssertFalse(progress.isComplete)
        XCTAssertEqual(progress.progressPercent, 75)
    }

    func testIndexProgressComplete() throws {
        let json = """
        {
            "task_id": "abc123",
            "status": "completed",
            "progress": 1.0,
            "processed": 100,
            "total": 100,
            "errors": []
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let progress = try decoder.decode(IndexProgress.self, from: data)

        XCTAssertTrue(progress.isComplete)
        XCTAssertFalse(progress.isRunning)
        XCTAssertEqual(progress.progressPercent, 100)
    }

    // MARK: - Index Result Tests

    func testIndexResultDecoding() throws {
        let json = """
        {
            "id": "photo123",
            "path": "/photos/sunset.jpg",
            "description": "A beautiful sunset",
            "tags": ["sunset", "nature", "sky"],
            "location": {
                "city": "Honolulu",
                "state": "Hawaii",
                "country": "USA"
            }
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let result = try decoder.decode(IndexResult.self, from: data)

        XCTAssertEqual(result.id, "photo123")
        XCTAssertEqual(result.path, "/photos/sunset.jpg")
        XCTAssertEqual(result.description, "A beautiful sunset")
        XCTAssertEqual(result.tags, ["sunset", "nature", "sky"])
        XCTAssertEqual(result.location?.city, "Honolulu")
    }

    // MARK: - Geocode Response Tests

    func testGeocodeResponseDecoding() throws {
        let json = """
        {
            "name": "Hawaii",
            "bounding_box": {
                "min_lat": 18.91,
                "max_lat": 22.24,
                "min_lon": -160.25,
                "max_lon": -154.81
            },
            "center": {
                "lat": 20.57,
                "lon": -157.53
            }
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        let response = try decoder.decode(GeocodeResponse.self, from: data)

        XCTAssertEqual(response.name, "Hawaii")
        XCTAssertNotNil(response.boundingBox)
        XCTAssertNotNil(response.center)
        XCTAssertEqual(response.center?.lat, 20.57)
    }

    // MARK: - API Error Tests

    func testAPIErrorDescriptions() {
        XCTAssertEqual(APIError.invalidURL.errorDescription, "Invalid URL")
        XCTAssertEqual(APIError.backendNotAvailable.errorDescription,
                       "Backend server is not available. Please start the backend.")

        let networkError = APIError.networkError("Connection refused")
        XCTAssertTrue(networkError.errorDescription?.contains("Connection refused") ?? false)

        let serverError = APIError.serverError(500, "Internal error")
        XCTAssertTrue(serverError.errorDescription?.contains("500") ?? false)
        XCTAssertTrue(serverError.errorDescription?.contains("Internal error") ?? false)
    }

    func testAPIErrorIsConnectionError() {
        XCTAssertTrue(APIError.backendNotAvailable.isConnectionError)
        XCTAssertTrue(APIError.networkError("error").isConnectionError)
        XCTAssertFalse(APIError.serverError(500, nil).isConnectionError)
        XCTAssertFalse(APIError.decodingError("error").isConnectionError)
    }

    // MARK: - ViewModel Tests

    @MainActor
    func testSearchViewModelInitialization() {
        let viewModel = SearchViewModel()

        XCTAssertEqual(viewModel.searchQuery, "")
        XCTAssertTrue(viewModel.results.isEmpty)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertNil(viewModel.startDate)
        XCTAssertNil(viewModel.endDate)
        XCTAssertNil(viewModel.locationFilter)
    }

    @MainActor
    func testSearchViewModelClear() {
        let viewModel = SearchViewModel()
        viewModel.searchQuery = "test"
        viewModel.errorMessage = "error"

        viewModel.clear()

        XCTAssertEqual(viewModel.searchQuery, "")
        XCTAssertTrue(viewModel.results.isEmpty)
        XCTAssertNil(viewModel.errorMessage)
    }

    @MainActor
    func testSearchViewModelClearFilters() {
        let viewModel = SearchViewModel()
        viewModel.startDate = Date()
        viewModel.endDate = Date()
        viewModel.locationFilter = "Hawaii"

        viewModel.clearFilters()

        XCTAssertNil(viewModel.startDate)
        XCTAssertNil(viewModel.endDate)
        XCTAssertNil(viewModel.locationFilter)
    }

    // MARK: - Network Error Tests

    func testNetworkErrorWithWrongPort() async {
        let client = APIClient(baseURL: "http://localhost:9999/api/v1", timeoutInterval: 2)

        do {
            _ = try await client.getStatus()
            XCTFail("Should throw an error")
        } catch let error as APIError {
            // Should be a connection error
            XCTAssertTrue(error.isConnectionError,
                          "Expected connection error but got: \(error)")
        } catch {
            // Other network errors are also acceptable
            XCTAssertTrue(error.localizedDescription.contains("Could not connect") ||
                         error.localizedDescription.contains("connection"),
                          "Unexpected error: \(error)")
        }
    }

    // MARK: - Photo Model Tests

    func testPhotoDecoding() throws {
        let json = """
        {
            "id": "photo123",
            "file_path": "/photos/sunset.jpg",
            "filename": "sunset.jpg",
            "timestamp": "2024-06-15T18:30:00Z",
            "latitude": 21.3069,
            "longitude": -157.8583,
            "city": "Honolulu",
            "state": "Hawaii",
            "country": "USA",
            "description": "A sunset",
            "tags": ["sunset"],
            "indexed_at": "2024-06-20T10:00:00Z"
        }
        """

        let data = json.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let photo = try decoder.decode(Photo.self, from: data)

        XCTAssertEqual(photo.id, "photo123")
        XCTAssertEqual(photo.filePath, "/photos/sunset.jpg")
        XCTAssertEqual(photo.filename, "sunset.jpg")
        XCTAssertEqual(photo.city, "Honolulu")
        XCTAssertEqual(photo.tags, ["sunset"])
        XCTAssertNotNil(photo.timestamp)
    }

    // MARK: - ThumbnailCache Tests

    @MainActor
    func testThumbnailCacheSharedInstance() {
        let cache1 = ThumbnailCache.shared
        let cache2 = ThumbnailCache.shared
        XCTAssertTrue(cache1 === cache2, "ThumbnailCache should be a singleton")
    }

    @MainActor
    func testThumbnailCacheClearCache() {
        let cache = ThumbnailCache.shared
        cache.clearCache()
        // Should not crash
        XCTAssertTrue(true)
    }

    @MainActor
    func testThumbnailLoaderInitialization() {
        let loader = ThumbnailLoader()
        XCTAssertNil(loader.image)
        XCTAssertFalse(loader.isLoading)
    }

    // MARK: - SearchFilter Tests

    func testSearchFilterEquality() {
        let filter1 = SearchFilter(type: .location, value: "Hawaii")
        let filter2 = SearchFilter(type: .location, value: "Hawaii")

        // Each filter has unique ID, so they should not be equal
        XCTAssertNotEqual(filter1, filter2)
        XCTAssertEqual(filter1, filter1)
    }

    func testSearchFilterTypeProperties() {
        XCTAssertEqual(SearchFilter.FilterType.location.icon, "location.fill")
        XCTAssertEqual(SearchFilter.FilterType.dateRange.icon, "calendar")
        XCTAssertEqual(SearchFilter.FilterType.tag.icon, "tag.fill")

        XCTAssertEqual(SearchFilter.FilterType.location.rawValue, "Location")
        XCTAssertEqual(SearchFilter.FilterType.dateRange.rawValue, "Date")
        XCTAssertEqual(SearchFilter.FilterType.tag.rawValue, "Tag")
    }

    // MARK: - SearchResult Array Tests

    func testSearchResultArrayOperations() {
        let results = [
            SearchResult(id: "1", path: "/a.jpg", score: 0.9, description: nil, timestamp: nil, city: nil, state: nil, country: nil),
            SearchResult(id: "2", path: "/b.jpg", score: 0.8, description: nil, timestamp: nil, city: nil, state: nil, country: nil),
            SearchResult(id: "3", path: "/c.jpg", score: 0.7, description: nil, timestamp: nil, city: nil, state: nil, country: nil)
        ]

        XCTAssertEqual(results.count, 3)
        XCTAssertEqual(results.first?.id, "1")
        XCTAssertEqual(results.last?.id, "3")

        // Find by ID
        let found = results.first { $0.id == "2" }
        XCTAssertEqual(found?.path, "/b.jpg")
    }
}
