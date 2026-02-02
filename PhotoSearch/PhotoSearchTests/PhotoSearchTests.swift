import XCTest
@testable import PhotoSearch

final class PhotoSearchTests: XCTestCase {

    // MARK: - Model Tests

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
    }

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
    }

    func testSearchRequestEncoding() throws {
        let request = SearchRequest(query: "sunset", topK: 20, location: "Hawaii")

        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = String(data: data, encoding: .utf8)!

        XCTAssertTrue(json.contains("\"query\":\"sunset\""))
        XCTAssertTrue(json.contains("\"top_k\":20"))
        XCTAssertTrue(json.contains("\"location\":\"Hawaii\""))
    }

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
    }

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

    // MARK: - ViewModel Tests

    @MainActor
    func testSearchViewModelInitialization() {
        let viewModel = SearchViewModel()

        XCTAssertEqual(viewModel.searchQuery, "")
        XCTAssertTrue(viewModel.results.isEmpty)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
    }

    @MainActor
    func testSearchViewModelClear() {
        let viewModel = SearchViewModel()
        viewModel.searchQuery = "test"
        viewModel.clear()

        XCTAssertEqual(viewModel.searchQuery, "")
        XCTAssertTrue(viewModel.results.isEmpty)
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
}
