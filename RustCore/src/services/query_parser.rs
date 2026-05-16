use regex::Regex;
use std::sync::LazyLock;

static LOCATION_PATTERN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(?:from|in|at|near|taken\s+in|taken\s+at|shot\s+in|shot\s+at)\s+(.+?)$").unwrap()
});

/// Parse a search query to extract a semantic query and optional location.
/// e.g., "sunset from Hawaii" -> ("sunset", Some("Hawaii"))
pub fn parse_query(query: &str) -> (String, Option<String>) {
    let query = query.trim();
    if query.is_empty() {
        return (String::new(), None);
    }

    // Primary location parsing is done Swift-side via NLTagger (NaturalLanguage
    // framework) before the request reaches Rust — it has a real on-device NER
    // model and only flags actual recognized places. This regex remains as a
    // defensive fallback for callers that don't pre-parse, and uses a
    // capitalization heuristic to avoid false positives like "girls in water".
    if let Some(captures) = LOCATION_PATTERN.captures(query) {
        let full_match = captures.get(0).unwrap();
        let location = captures.get(1).unwrap().as_str().trim().to_string();
        let semantic = query[..full_match.start()].trim().to_string();

        if !location.is_empty() && !semantic.is_empty() && looks_like_place(&location) {
            return (semantic, Some(location));
        }
    }

    (query.to_string(), None)
}

fn looks_like_place(candidate: &str) -> bool {
    candidate
        .split_whitespace()
        .any(|word| word.chars().next().is_some_and(|c| c.is_uppercase()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_query() {
        let (query, location) = parse_query("beautiful sunset");
        assert_eq!(query, "beautiful sunset");
        assert!(location.is_none());
    }

    #[test]
    fn test_query_with_from() {
        let (query, location) = parse_query("sunset from Hawaii");
        assert_eq!(query, "sunset");
        assert_eq!(location.unwrap(), "Hawaii");
    }

    #[test]
    fn test_query_with_in() {
        let (query, location) = parse_query("dogs in Central Park");
        assert_eq!(query, "dogs");
        assert_eq!(location.unwrap(), "Central Park");
    }

    #[test]
    fn test_empty_query() {
        let (query, location) = parse_query("");
        assert_eq!(query, "");
        assert!(location.is_none());
    }

    #[test]
    fn test_query_with_taken_in() {
        let (query, location) = parse_query("birthday taken in Paris");
        assert_eq!(query, "birthday");
        assert_eq!(location.unwrap(), "Paris");
    }

    #[test]
    fn test_lowercase_after_in_is_not_a_place() {
        // "water" / "waterpolo" / "the pool" are common nouns, not places.
        // The regex would match but `looks_like_place` rejects them.
        let (query, location) = parse_query("girls in water");
        assert_eq!(query, "girls in water");
        assert!(location.is_none());

        let (query, location) = parse_query("girls in waterpolo");
        assert_eq!(query, "girls in waterpolo");
        assert!(location.is_none());

        let (query, location) = parse_query("kids in the pool");
        assert_eq!(query, "kids in the pool");
        assert!(location.is_none());
    }

    #[test]
    fn test_capitalized_multiword_place() {
        let (query, location) = parse_query("kids in NYC");
        assert_eq!(query, "kids");
        assert_eq!(location.unwrap(), "NYC");

        let (query, location) = parse_query("walk in Golden Gate Park");
        assert_eq!(query, "walk");
        assert_eq!(location.unwrap(), "Golden Gate Park");
    }
}
