import Foundation
import NaturalLanguage

/// Detects a place name inside a free-text search query, using Apple's
/// on-device named-entity recognizer.
///
/// Only the place *detection* is used — the query is no longer stripped.
/// The full query (place name included) is sent to SigLIP so photos with no
/// GPS can still be matched visually, while the detected place drives the
/// (soft) location filter for geotagged photos.
enum QueryParser {
    /// Return the first place name NLTagger recognizes in `query`, if any.
    ///
    /// - "sunset in Hawaii"        → "Hawaii"
    /// - "walk in Golden Gate Park"→ "Golden Gate Park"
    /// - "girls in water"          → nil  (common noun, not a place)
    static func detectLocation(_ query: String) -> String? {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        let tagger = NLTagger(tagSchemes: [.nameType])
        tagger.string = trimmed
        let options: NLTagger.Options = [.omitPunctuation, .omitWhitespace, .joinNames]

        var place: String?
        tagger.enumerateTags(
            in: trimmed.startIndex..<trimmed.endIndex,
            unit: .word,
            scheme: .nameType,
            options: options
        ) { tag, range in
            if tag == .placeName {
                place = String(trimmed[range])
                return false   // stop at first hit
            }
            return true
        }
        return place
    }
}
