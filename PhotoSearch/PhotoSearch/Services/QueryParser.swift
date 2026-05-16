import Foundation
import NaturalLanguage

/// Splits a free-text search query into a semantic part and an optional
/// location, using Apple's on-device named-entity recognizer.
///
/// Replaces a naive Rust-side regex+capitalization heuristic that was
/// over-eager (it extracted "water" from "girls in water" and triggered a
/// blocking geocoding network call). NLTagger ships with a real NER model,
/// runs locally with no model download, and only tags strings it recognizes
/// as actual place names — so common nouns are left alone.
enum QueryParser {
    /// Parse a query into `(semanticQuery, location)`.
    ///
    /// - "sunset in Hawaii"        → ("sunset", "Hawaii")
    /// - "kids in NYC"             → ("kids", "NYC")
    /// - "walk in Golden Gate Park"→ ("walk", "Golden Gate Park")
    /// - "girls in water"          → ("girls in water", nil)
    /// - "kids in the pool"        → ("kids in the pool", nil)
    static func parse(_ query: String) -> (semantic: String, location: String?) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return ("", nil) }

        guard let placeRange = firstPlaceNameRange(in: trimmed) else {
            return (trimmed, nil)
        }

        let location = String(trimmed[placeRange])
        // Strip the place AND any trailing preposition that introduced it
        // ("in", "from", "at", "near", "taken in"…), so the residual reads
        // cleanly as a CLIP query.
        let semantic = stripPlace(from: trimmed, range: placeRange)

        // If stripping leaves nothing meaningful, treat the whole query as
        // semantic — no point searching with an empty embedding.
        let cleanSemantic = semantic.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleanSemantic.isEmpty {
            return (trimmed, nil)
        }

        return (cleanSemantic, location)
    }

    // MARK: - Internals

    private static let prepositions: [String] = [
        "taken in", "taken at", "shot in", "shot at",
        "from", "in", "at", "near"
    ]

    /// Returns the range of the first NLTagger-recognized place name in `s`.
    private static func firstPlaceNameRange(in s: String) -> Range<String.Index>? {
        let tagger = NLTagger(tagSchemes: [.nameType])
        tagger.string = s
        let options: NLTagger.Options = [.omitPunctuation, .omitWhitespace, .joinNames]

        var found: Range<String.Index>?
        tagger.enumerateTags(
            in: s.startIndex..<s.endIndex,
            unit: .word,
            scheme: .nameType,
            options: options
        ) { tag, range in
            if tag == .placeName {
                found = range
                return false   // stop at first hit
            }
            return true
        }
        return found
    }

    /// Removes the place plus any leading preposition immediately before it.
    private static func stripPlace(from s: String, range: Range<String.Index>) -> String {
        // Look at the substring before the place; drop a trailing preposition
        // if present. This handles "sunset in Hawaii" → "sunset".
        var prefix = String(s[..<range.lowerBound])
            .trimmingCharacters(in: .whitespacesAndNewlines)

        let prefixLower = prefix.lowercased()
        for prep in prepositions {
            if prefixLower.hasSuffix(" " + prep) || prefixLower == prep {
                let dropCount = (prefixLower == prep) ? prep.count : prep.count + 1
                prefix = String(prefix.dropLast(dropCount))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                break
            }
        }

        let suffix = String(s[range.upperBound...])
            .trimmingCharacters(in: .whitespacesAndNewlines)

        if suffix.isEmpty { return prefix }
        if prefix.isEmpty { return suffix }
        return prefix + " " + suffix
    }
}
