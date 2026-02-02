import Foundation

/// Represents a photo in the library.
struct Photo: Identifiable, Codable, Equatable {
    let id: String
    let filePath: String
    let filename: String
    let timestamp: Date?
    let latitude: Double?
    let longitude: Double?
    let city: String?
    let state: String?
    let country: String?
    let placeName: String?
    let description: String?
    let tags: [String]
    let indexedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case filePath = "file_path"
        case filename
        case timestamp
        case latitude
        case longitude
        case city
        case state
        case country
        case placeName = "place_name"
        case description
        case tags
        case indexedAt = "indexed_at"
    }
}

/// Search result from the backend.
struct SearchResult: Identifiable, Codable, Equatable {
    let id: String
    let path: String
    let score: Double?
    let description: String?
    let timestamp: Date?
    let city: String?
    let state: String?
    let country: String?

    enum CodingKeys: String, CodingKey {
        case id
        case path
        case score
        case description
        case timestamp
        case city
        case state
        case country
    }
}

/// Response from a search query.
struct SearchResponse: Codable, Equatable {
    let results: [SearchResult]
    let totalResults: Int
    let locationResolved: LocationResolved?

    enum CodingKeys: String, CodingKey {
        case results
        case totalResults = "total_results"
        case locationResolved = "location_resolved"
    }
}

/// Resolved location information from a search query.
struct LocationResolved: Codable, Equatable {
    let query: String?
    let boundingBox: BoundingBox?

    enum CodingKeys: String, CodingKey {
        case query
        case boundingBox = "bounding_box"
    }
}

/// Geographic bounding box.
struct BoundingBox: Codable, Equatable {
    let minLat: Double
    let maxLat: Double
    let minLon: Double
    let maxLon: Double

    enum CodingKeys: String, CodingKey {
        case minLat = "min_lat"
        case maxLat = "max_lat"
        case minLon = "min_lon"
        case maxLon = "max_lon"
    }

    /// Check if a coordinate is within the bounding box.
    func contains(latitude: Double, longitude: Double) -> Bool {
        latitude >= minLat && latitude <= maxLat &&
        longitude >= minLon && longitude <= maxLon
    }
}
