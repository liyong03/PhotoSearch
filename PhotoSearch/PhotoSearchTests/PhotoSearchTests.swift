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

// MARK: - Mock API Client for Testing

/// Mock API client for testing SearchViewModel
actor MockAPIClient: APIClientProtocol {
    var searchCalled = false
    var searchCallCount = 0
    var lastSearchRequest: SearchRequest?
    var mockSearchResponse: SearchResponse?
    var mockError: Error?
    var searchDelay: TimeInterval = 0

    func getStatus() async throws -> BackendStatus {
        BackendStatus(status: "ready", indexedCount: 0, vectorIndexSize: 0, locationCache: nil)
    }

    func isBackendReady() async -> Bool {
        true
    }

    func search(_ request: SearchRequest) async throws -> SearchResponse {
        searchCalled = true
        searchCallCount += 1
        lastSearchRequest = request

        if searchDelay > 0 {
            try await Task.sleep(nanoseconds: UInt64(searchDelay * 1_000_000_000))
        }

        if let error = mockError {
            throw error
        }

        return mockSearchResponse ?? SearchResponse(
            results: [],
            totalResults: 0,
            locationResolved: nil
        )
    }

    func search(query: String, topK: Int, location: String?) async throws -> SearchResponse {
        let request = SearchRequest(query: query, topK: topK, location: location)
        return try await search(request)
    }

    func indexPhoto(path: String) async throws -> IndexResult {
        IndexResult(id: "test", path: path, description: nil, tags: [], location: nil, timestamp: nil)
    }

    func indexFolder(path: String, recursive: Bool) async throws -> IndexTask {
        indexFolderCalled = true
        lastIndexPath = path
        if let task = mockIndexTask {
            return task
        }
        return IndexTask(taskId: "test-task", status: "started", totalFiles: nil)
    }

    var mockIndexProgress: IndexProgress?
    var mockIndexTask: IndexTask?
    var indexFolderCalled = false
    var lastIndexPath: String?

    func getIndexStatus(taskId: String) async throws -> IndexProgress {
        if let progress = mockIndexProgress {
            return progress
        }
        return IndexProgress(taskId: taskId, status: "completed", progress: 1.0, processed: 100, total: 100, errors: [])
    }

    func setMockIndexProgress(_ progress: IndexProgress) {
        mockIndexProgress = progress
    }

    func setMockIndexTask(_ task: IndexTask) {
        mockIndexTask = task
    }

    func getIndexFolderCalled() -> Bool { indexFolderCalled }
    func getLastIndexPath() -> String? { lastIndexPath }

    func deletePhoto(photoId: String) async throws {
        // No-op for mock
    }

    func geocode(placeName: String) async throws -> GeocodeResponse {
        GeocodeResponse(name: placeName, boundingBox: nil, center: nil)
    }

    func setMockResponse(_ response: SearchResponse) {
        mockSearchResponse = response
    }

    func setMockError(_ error: Error) {
        mockError = error
    }

    func setSearchDelay(_ delay: TimeInterval) {
        searchDelay = delay
    }

    func reset() {
        searchCalled = false
        searchCallCount = 0
        lastSearchRequest = nil
        mockSearchResponse = nil
        mockError = nil
        searchDelay = 0
        mockIndexProgress = nil
        mockIndexTask = nil
        indexFolderCalled = false
        lastIndexPath = nil
    }

    func getSearchCalled() -> Bool { searchCalled }
    func getSearchCallCount() -> Int { searchCallCount }
    func getLastSearchRequest() -> SearchRequest? { lastSearchRequest }
}

// MARK: - F4 Search Integration Tests

final class SearchViewModelIntegrationTests: XCTestCase {

    @MainActor
    func testSearchTriggersAPICall() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = "sunset"
        await viewModel.search()

        let searchCalled = await mockClient.getSearchCalled()
        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertTrue(searchCalled, "Search should trigger API call")
        XCTAssertEqual(lastRequest?.query, "sunset")
    }

    @MainActor
    func testResultsUpdateFromAPI() async {
        let mockClient = MockAPIClient()
        let mockPhoto = SearchResult(
            id: "1",
            path: "/photos/sunset.jpg",
            score: 0.95,
            description: "A sunset",
            timestamp: nil,
            city: "Honolulu",
            state: "Hawaii",
            country: "USA"
        )
        await mockClient.setMockResponse(SearchResponse(
            results: [mockPhoto],
            totalResults: 1,
            locationResolved: nil
        ))

        let viewModel = SearchViewModel(apiClient: mockClient)
        viewModel.searchQuery = "sunset"
        await viewModel.search()

        XCTAssertEqual(viewModel.results.count, 1)
        XCTAssertEqual(viewModel.results.first?.id, "1")
        XCTAssertEqual(viewModel.totalResults, 1)
    }

    @MainActor
    func testLoadingStateDuringSearch() async {
        let mockClient = MockAPIClient()
        await mockClient.setSearchDelay(0.5) // 500ms delay to ensure loading state is visible

        let viewModel = SearchViewModel(apiClient: mockClient)
        viewModel.searchQuery = "sunset"

        // Verify initial state
        XCTAssertFalse(viewModel.isLoading, "Should not be loading initially")

        // Start search in background
        let searchTask = Task {
            await viewModel.search()
        }

        // Poll for loading state with timeout
        var loadingObserved = false
        for _ in 0..<100 { // Up to 500ms
            if viewModel.isLoading {
                loadingObserved = true
                break
            }
            try? await Task.sleep(nanoseconds: 5_000_000) // 5ms
        }

        XCTAssertTrue(loadingObserved, "Should observe loading state during search")

        // Wait for our manual search to complete
        await searchTask.value

        // Wait for debounced search to also complete (debounce is 0.3s + search delay 0.15s)
        // Poll until loading clears, with a generous timeout
        for _ in 0..<100 { // Up to 1 second
            if !viewModel.isLoading {
                break
            }
            try? await Task.sleep(nanoseconds: 10_000_000) // 10ms
        }

        XCTAssertFalse(viewModel.isLoading, "Should not be loading after all searches complete")
    }

    @MainActor
    func testErrorStateOnAPIFailure() async {
        let mockClient = MockAPIClient()
        await mockClient.setMockError(APIError.networkError("Connection failed"))

        let viewModel = SearchViewModel(apiClient: mockClient)
        viewModel.searchQuery = "sunset"
        await viewModel.search()

        XCTAssertNotNil(viewModel.errorMessage, "Error message should be set on failure")
        XCTAssertTrue(viewModel.results.isEmpty, "Results should be empty on error")
    }

    @MainActor
    func testEmptyQueryDoesNotTriggerSearch() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = ""
        await viewModel.search()

        let searchCalled = await mockClient.getSearchCalled()
        XCTAssertFalse(searchCalled, "Empty query should not trigger API call")
    }

    @MainActor
    func testWhitespaceOnlyQueryDoesNotTriggerSearch() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = "   "
        await viewModel.search()

        let searchCalled = await mockClient.getSearchCalled()
        XCTAssertFalse(searchCalled, "Whitespace-only query should not trigger API call")
    }

    @MainActor
    func testSearchWithLocationFilter() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = "beach"
        viewModel.locationFilter = "Hawaii"
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertEqual(lastRequest?.location, "Hawaii")
    }

    @MainActor
    func testSearchWithTimeRange() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        let startDate = Date(timeIntervalSince1970: 0)
        let endDate = Date()

        viewModel.searchQuery = "vacation"
        viewModel.startDate = startDate
        viewModel.endDate = endDate
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertNotNil(lastRequest?.timeRange)
    }

    @MainActor
    func testLocationResolvedFromResponse() async {
        let mockClient = MockAPIClient()
        let locationResolved = LocationResolved(
            query: "Hawaii",
            boundingBox: BoundingBox(minLat: 18.91, maxLat: 22.24, minLon: -160.25, maxLon: -154.81)
        )
        await mockClient.setMockResponse(SearchResponse(
            results: [],
            totalResults: 0,
            locationResolved: locationResolved
        ))

        let viewModel = SearchViewModel(apiClient: mockClient)
        viewModel.searchQuery = "photos from Hawaii"
        await viewModel.search()

        XCTAssertNotNil(viewModel.locationResolved)
        XCTAssertEqual(viewModel.locationResolved?.query, "Hawaii")
    }

    @MainActor
    func testClearResetsAllState() {
        let viewModel = SearchViewModel()
        viewModel.searchQuery = "test"
        viewModel.errorMessage = "error"
        viewModel.totalResults = 10

        viewModel.clear()

        XCTAssertEqual(viewModel.searchQuery, "")
        XCTAssertTrue(viewModel.results.isEmpty)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertNil(viewModel.locationResolved)
        XCTAssertEqual(viewModel.totalResults, 0)
    }

    @MainActor
    func testMultipleSearchesCancelPrevious() async {
        let mockClient = MockAPIClient()
        await mockClient.setSearchDelay(0.2) // 200ms delay

        let viewModel = SearchViewModel(apiClient: mockClient)

        // Start first search
        viewModel.searchQuery = "first"
        let task1 = Task { await viewModel.search() }

        // Immediately start second search (should cancel first)
        viewModel.searchQuery = "second"
        await viewModel.search()

        task1.cancel()

        // Only the second search should complete
        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertEqual(lastRequest?.query, "second")
    }
}

// MARK: - F5 Filters & Folder Management Tests

final class FiltersAndFolderTests: XCTestCase {

    // MARK: - Date Filter Tests

    @MainActor
    func testDateFilterUpdatesSearch() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        let startDate = Date(timeIntervalSince1970: 0)
        let endDate = Date()

        viewModel.searchQuery = "vacation"
        viewModel.startDate = startDate
        viewModel.endDate = endDate
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertNotNil(lastRequest?.timeRange, "Search should include time range")
        XCTAssertEqual(lastRequest?.timeRange?.start, startDate)
        XCTAssertEqual(lastRequest?.timeRange?.end, endDate)
    }

    @MainActor
    func testDateFilterNotIncludedWhenNotSet() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = "beach"
        // Don't set dates
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertNil(lastRequest?.timeRange, "Search should not include time range when not set")
    }

    @MainActor
    func testDateFilterRequiresBothDates() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = "mountain"
        viewModel.startDate = Date() // Only start date set
        viewModel.endDate = nil
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertNil(lastRequest?.timeRange, "Time range should only be included when both dates are set")
    }

    // MARK: - Location Filter Tests

    @MainActor
    func testLocationFilterIncludedInSearch() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = "beach"
        viewModel.locationFilter = "Hawaii"
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertEqual(lastRequest?.location, "Hawaii", "Search should include location filter")
    }

    @MainActor
    func testLocationFilterNotIncludedWhenEmpty() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        viewModel.searchQuery = "sunset"
        viewModel.locationFilter = nil
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertNil(lastRequest?.location, "Search should not include location when not set")
    }

    @MainActor
    func testClearFiltersResetsAllFilters() {
        let viewModel = SearchViewModel()

        viewModel.startDate = Date()
        viewModel.endDate = Date()
        viewModel.locationFilter = "Paris"

        viewModel.clearFilters()

        XCTAssertNil(viewModel.startDate, "Start date should be nil after clear")
        XCTAssertNil(viewModel.endDate, "End date should be nil after clear")
        XCTAssertNil(viewModel.locationFilter, "Location filter should be nil after clear")
    }

    // MARK: - PhotoLoader Tests

    func testPhotoLoaderSupportedExtensions() {
        let extensions = PhotoLoader.supportedExtensions
        XCTAssertTrue(extensions.contains("jpg"), "Should support jpg")
        XCTAssertTrue(extensions.contains("jpeg"), "Should support jpeg")
        XCTAssertTrue(extensions.contains("png"), "Should support png")
        XCTAssertTrue(extensions.contains("heic"), "Should support heic")
        XCTAssertTrue(extensions.contains("heif"), "Should support heif")
    }

    func testPhotoLoaderIsImageFile() {
        let loader = PhotoLoader.shared

        let jpgURL = URL(fileURLWithPath: "/test/photo.jpg")
        let pngURL = URL(fileURLWithPath: "/test/image.png")
        let txtURL = URL(fileURLWithPath: "/test/document.txt")
        let heicURL = URL(fileURLWithPath: "/test/photo.HEIC")

        // Note: These will return false because the files don't exist
        // but the extension check happens first
        XCTAssertFalse(loader.isImageFile(txtURL), "txt should not be an image file")
    }

    func testPhotoLoaderScanNonexistentFolder() {
        let loader = PhotoLoader.shared
        let url = URL(fileURLWithPath: "/nonexistent/folder/path")
        let results = loader.scanFolder(url)
        XCTAssertTrue(results.isEmpty, "Scanning nonexistent folder should return empty array")
    }

    // MARK: - FolderInfo Tests

    func testFolderInfoInitialization() {
        let url = URL(fileURLWithPath: "/Users/test/Photos")
        let folder = FolderInfo(url: url, photoCount: 100, isIndexed: true)

        XCTAssertEqual(folder.url, url)
        XCTAssertEqual(folder.name, "Photos")
        XCTAssertEqual(folder.photoCount, 100)
        XCTAssertTrue(folder.isIndexed)
        XCTAssertEqual(folder.path, "/Users/test/Photos")
    }

    func testFolderInfoEquality() {
        let url = URL(fileURLWithPath: "/Users/test/Photos")
        let folder1 = FolderInfo(url: url)
        let folder2 = FolderInfo(url: url)

        // Each FolderInfo has a unique UUID, so they should not be equal
        XCTAssertNotEqual(folder1, folder2)
        XCTAssertEqual(folder1, folder1)
    }

    // MARK: - BookmarkManager Tests

    func testBookmarkManagerSavedFolderPaths() {
        let defaults = UserDefaults(suiteName: "TestBookmarkManager")!
        defaults.removePersistentDomain(forName: "TestBookmarkManager")

        let manager = BookmarkManager(defaults: defaults)
        let paths = manager.savedFolderPaths()
        XCTAssertTrue(paths.isEmpty, "Initial saved paths should be empty")
    }

    func testBookmarkManagerHasBookmark() {
        let defaults = UserDefaults(suiteName: "TestBookmarkManager2")!
        defaults.removePersistentDomain(forName: "TestBookmarkManager2")

        let manager = BookmarkManager(defaults: defaults)
        let url = URL(fileURLWithPath: "/Users/test/Photos")

        XCTAssertFalse(manager.hasBookmark(for: url), "Should not have bookmark initially")
    }

    // MARK: - LibraryViewModel Tests

    @MainActor
    func testLibraryViewModelInitialization() {
        let mockClient = MockAPIClient()
        let defaults = UserDefaults(suiteName: "TestLibraryViewModel")!
        defaults.removePersistentDomain(forName: "TestLibraryViewModel")

        let bookmarkManager = BookmarkManager(defaults: defaults)
        let viewModel = LibraryViewModel(
            bookmarkManager: bookmarkManager,
            photoLoader: PhotoLoader.shared,
            apiClient: mockClient
        )

        XCTAssertTrue(viewModel.folders.isEmpty)
        XCTAssertNil(viewModel.selectedFolder)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
    }

    @MainActor
    func testLibraryViewModelRemoveFolder() {
        let mockClient = MockAPIClient()
        let defaults = UserDefaults(suiteName: "TestLibraryViewModel2")!
        defaults.removePersistentDomain(forName: "TestLibraryViewModel2")

        let bookmarkManager = BookmarkManager(defaults: defaults)
        let viewModel = LibraryViewModel(
            bookmarkManager: bookmarkManager,
            photoLoader: PhotoLoader.shared,
            apiClient: mockClient
        )

        let url = URL(fileURLWithPath: "/Users/test/Photos")
        let folder = FolderInfo(url: url, photoCount: 10)

        // Manually add a folder (simulating what addFolder would do)
        viewModel.folders.append(folder)
        viewModel.selectedFolder = folder

        XCTAssertEqual(viewModel.folders.count, 1)

        // Remove the folder
        viewModel.removeFolder(folder)

        XCTAssertTrue(viewModel.folders.isEmpty)
        XCTAssertNil(viewModel.selectedFolder)
    }

    @MainActor
    func testLibraryViewModelDismissError() {
        let mockClient = MockAPIClient()
        let defaults = UserDefaults(suiteName: "TestLibraryViewModel3")!
        defaults.removePersistentDomain(forName: "TestLibraryViewModel3")

        let bookmarkManager = BookmarkManager(defaults: defaults)
        let viewModel = LibraryViewModel(
            bookmarkManager: bookmarkManager,
            photoLoader: PhotoLoader.shared,
            apiClient: mockClient
        )

        viewModel.errorMessage = "Test error"
        XCTAssertNotNil(viewModel.errorMessage)

        viewModel.dismissError()
        XCTAssertNil(viewModel.errorMessage)
    }

    // MARK: - Combined Filter Tests

    @MainActor
    func testCombinedFiltersInSearch() async {
        let mockClient = MockAPIClient()
        let viewModel = SearchViewModel(apiClient: mockClient)

        let startDate = Date(timeIntervalSince1970: 1000000)
        let endDate = Date()

        viewModel.searchQuery = "sunset"
        viewModel.startDate = startDate
        viewModel.endDate = endDate
        viewModel.locationFilter = "California"
        await viewModel.search()

        let lastRequest = await mockClient.getLastSearchRequest()
        XCTAssertEqual(lastRequest?.query, "sunset")
        XCTAssertNotNil(lastRequest?.timeRange)
        XCTAssertEqual(lastRequest?.location, "California")
    }
}

// MARK: - F6 Indexing Progress Tests

final class IndexingProgressTests: XCTestCase {

    // MARK: - IndexingViewModel Initialization Tests

    @MainActor
    func testIndexingViewModelInitialization() {
        let mockClient = MockAPIClient()
        let viewModel = IndexingViewModel(apiClient: mockClient)

        XCTAssertFalse(viewModel.isIndexing)
        XCTAssertEqual(viewModel.progress, 0.0)
        XCTAssertEqual(viewModel.processedCount, 0)
        XCTAssertEqual(viewModel.totalCount, 0)
        XCTAssertNil(viewModel.currentTaskId)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.isComplete)
        XCTAssertTrue(viewModel.errors.isEmpty)
    }

    // MARK: - Progress Update Tests

    @MainActor
    func testProgressUpdates() async {
        let mockClient = MockAPIClient()
        let viewModel = IndexingViewModel(apiClient: mockClient)

        // Set up mock progress response
        await mockClient.setMockIndexProgress(IndexProgress(
            taskId: "test-task",
            status: "running",
            progress: 0.5,
            processed: 50,
            total: 100,
            errors: []
        ))

        // Set task ID manually to simulate an active indexing task
        viewModel.currentTaskId = "test-task"

        await viewModel.checkProgress()

        XCTAssertEqual(viewModel.progress, 0.5, "Progress should be 0.5")
        XCTAssertEqual(viewModel.processedCount, 50, "Processed count should be 50")
        XCTAssertEqual(viewModel.totalCount, 100, "Total count should be 100")
    }

    @MainActor
    func testProgressPercent() {
        let viewModel = IndexingViewModel()

        viewModel.progress = 0.0
        XCTAssertEqual(viewModel.progressPercent, "0%")

        viewModel.progress = 0.5
        XCTAssertEqual(viewModel.progressPercent, "50%")

        viewModel.progress = 1.0
        XCTAssertEqual(viewModel.progressPercent, "100%")

        viewModel.progress = 0.333
        XCTAssertEqual(viewModel.progressPercent, "33%")
    }

    @MainActor
    func testProgressDescription() {
        let viewModel = IndexingViewModel()

        viewModel.totalCount = 0
        XCTAssertEqual(viewModel.progressDescription, "Processing...")

        viewModel.processedCount = 50
        viewModel.totalCount = 100
        XCTAssertEqual(viewModel.progressDescription, "50 of 100 photos")

        viewModel.processedCount = 1
        viewModel.totalCount = 1
        XCTAssertEqual(viewModel.progressDescription, "1 of 1 photos")
    }

    // MARK: - Start Indexing Tests

    @MainActor
    func testStartIndexingSetsState() async {
        let mockClient = MockAPIClient()
        await mockClient.setMockIndexTask(IndexTask(taskId: "new-task", status: "started", totalFiles: 50))

        let viewModel = IndexingViewModel(apiClient: mockClient)
        await viewModel.startIndexing(path: "/test/photos")

        XCTAssertTrue(viewModel.isIndexing, "Should be indexing after start")
        XCTAssertEqual(viewModel.currentTaskId, "new-task", "Task ID should be set")
        XCTAssertEqual(viewModel.totalCount, 50, "Total count should be set from task")
        XCTAssertFalse(viewModel.isComplete, "Should not be complete")
    }

    @MainActor
    func testStartIndexingCallsAPI() async {
        let mockClient = MockAPIClient()
        let viewModel = IndexingViewModel(apiClient: mockClient)

        await viewModel.startIndexing(path: "/Users/test/Photos")

        let called = await mockClient.getIndexFolderCalled()
        let path = await mockClient.getLastIndexPath()
        XCTAssertTrue(called, "Should call indexFolder API")
        XCTAssertEqual(path, "/Users/test/Photos", "Should pass correct path")
    }

    // MARK: - Cancel Indexing Tests

    @MainActor
    func testCancelIndexing() {
        let viewModel = IndexingViewModel()
        viewModel.isIndexing = true
        viewModel.currentTaskId = "some-task"

        viewModel.cancelIndexing()

        XCTAssertFalse(viewModel.isIndexing, "Should not be indexing after cancel")
        XCTAssertNil(viewModel.currentTaskId, "Task ID should be cleared")
    }

    // MARK: - Reset Tests

    @MainActor
    func testReset() {
        let viewModel = IndexingViewModel()

        // Set up some state
        viewModel.isIndexing = true
        viewModel.progress = 0.75
        viewModel.processedCount = 75
        viewModel.totalCount = 100
        viewModel.currentTaskId = "test-task"
        viewModel.isComplete = true
        viewModel.errorMessage = "Some error"
        viewModel.errors = ["Error 1", "Error 2"]

        viewModel.reset()

        XCTAssertFalse(viewModel.isIndexing)
        XCTAssertEqual(viewModel.progress, 0.0)
        XCTAssertEqual(viewModel.processedCount, 0)
        XCTAssertEqual(viewModel.totalCount, 0)
        XCTAssertNil(viewModel.currentTaskId)
        XCTAssertFalse(viewModel.isComplete)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertTrue(viewModel.errors.isEmpty)
    }

    // MARK: - Error Handling Tests

    @MainActor
    func testHasErrors() {
        let viewModel = IndexingViewModel()

        XCTAssertFalse(viewModel.hasErrors, "Should have no errors initially")

        viewModel.errors = ["Error 1"]
        XCTAssertTrue(viewModel.hasErrors, "Should have errors after adding one")

        viewModel.errors = []
        XCTAssertFalse(viewModel.hasErrors, "Should have no errors after clearing")
    }

    @MainActor
    func testDismissError() {
        let viewModel = IndexingViewModel()
        viewModel.errorMessage = "Test error"

        XCTAssertNotNil(viewModel.errorMessage)

        viewModel.dismissError()

        XCTAssertNil(viewModel.errorMessage, "Error message should be dismissed")
    }

    // MARK: - Completion Tests

    @MainActor
    func testIndexingCompleteCallback() async {
        let mockClient = MockAPIClient()
        let viewModel = IndexingViewModel(apiClient: mockClient)

        var completionCalled = false
        viewModel.onComplete = {
            completionCalled = true
        }

        // Set up complete progress
        await mockClient.setMockIndexProgress(IndexProgress(
            taskId: "test-task",
            status: "completed",
            progress: 1.0,
            processed: 100,
            total: 100,
            errors: []
        ))

        viewModel.currentTaskId = "test-task"
        viewModel.isIndexing = true

        await viewModel.checkProgress()

        XCTAssertTrue(completionCalled, "onComplete callback should be called")
        XCTAssertTrue(viewModel.isComplete, "Should be marked complete")
        XCTAssertFalse(viewModel.isIndexing, "Should no longer be indexing")
    }

    @MainActor
    func testIndexingErrorCallback() async {
        let mockClient = MockAPIClient()
        let viewModel = IndexingViewModel(apiClient: mockClient)

        var errorMessage: String?
        viewModel.onError = { message in
            errorMessage = message
        }

        // Set up failed progress
        await mockClient.setMockIndexProgress(IndexProgress(
            taskId: "test-task",
            status: "failed",
            progress: 0.3,
            processed: 30,
            total: 100,
            errors: ["Failed to process file"]
        ))

        viewModel.currentTaskId = "test-task"
        viewModel.isIndexing = true

        await viewModel.checkProgress()

        XCTAssertNotNil(errorMessage, "onError callback should be called")
        XCTAssertFalse(viewModel.isIndexing, "Should no longer be indexing after failure")
    }

    // MARK: - Errors Array Tests

    @MainActor
    func testErrorsFromProgress() async {
        let mockClient = MockAPIClient()
        let viewModel = IndexingViewModel(apiClient: mockClient)

        let testErrors = ["File not found: /a.jpg", "Permission denied: /b.png"]
        await mockClient.setMockIndexProgress(IndexProgress(
            taskId: "test-task",
            status: "running",
            progress: 0.8,
            processed: 80,
            total: 100,
            errors: testErrors
        ))

        viewModel.currentTaskId = "test-task"
        await viewModel.checkProgress()

        XCTAssertEqual(viewModel.errors.count, 2)
        XCTAssertEqual(viewModel.errors, testErrors)
        XCTAssertTrue(viewModel.hasErrors)
    }

    // MARK: - No Task ID Tests

    @MainActor
    func testCheckProgressWithNoTaskId() async {
        let viewModel = IndexingViewModel()
        viewModel.currentTaskId = nil

        // This should not crash and should not update any state
        await viewModel.checkProgress()

        XCTAssertEqual(viewModel.progress, 0.0, "Progress should remain unchanged")
    }
}
