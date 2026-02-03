import SwiftUI

/// View model for search functionality.
@MainActor
class SearchViewModel: ObservableObject {
    // MARK: - Published Properties

    /// Current search query.
    @Published var searchQuery: String = ""

    /// Search results.
    @Published var results: [SearchResult] = []

    /// Whether a search is in progress.
    @Published var isLoading: Bool = false

    /// Error message, if any.
    @Published var errorMessage: String?

    /// Start date for time range filter.
    @Published var startDate: Date?

    /// End date for time range filter.
    @Published var endDate: Date?

    /// Location filter.
    @Published var locationFilter: String?

    /// Resolved location information from the last search.
    @Published var locationResolved: LocationResolved?

    /// Total number of results.
    @Published var totalResults: Int = 0

    // MARK: - Private Properties

    private let apiClient: any APIClientProtocol
    private var searchTask: Task<Void, Never>?

    // MARK: - Initialization

    init(apiClient: any APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    // MARK: - Public Methods

    /// Perform a search with the current query and filters.
    func search() async {
        // Cancel any existing search
        searchTask?.cancel()

        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)

        // Don't search empty queries
        guard !query.isEmpty else {
            results = []
            totalResults = 0
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            // Build time range if dates are set
            var timeRange: TimeRange?
            if let start = startDate, let end = endDate {
                timeRange = TimeRange(start: start, end: end)
            }

            let request = SearchRequest(
                query: query,
                topK: 50,
                timeRange: timeRange,
                location: locationFilter
            )

            let response = try await apiClient.search(request)

            results = response.results
            totalResults = response.totalResults
            locationResolved = response.locationResolved

        } catch let error as APIError where error.isCancellation {
            // Request was cancelled (e.g., by a new search), silently ignore
            return
        } catch {
            errorMessage = error.localizedDescription
            results = []
            totalResults = 0
        }

        isLoading = false
    }

    /// Clear search query and results.
    func clear() {
        searchQuery = ""
        results = []
        totalResults = 0
        errorMessage = nil
        locationResolved = nil
    }

    /// Clear all filters.
    func clearFilters() {
        startDate = nil
        endDate = nil
        locationFilter = nil
    }
}
