//! End-to-end test using real images from ~/Desktop/test/.
//! Tests the full pipeline: engine init → index photos → search → verify results.
//! Matches the Python backend's search/filter logic.
//!
//! Run with: cargo test --test e2e_real_images -- --ignored --nocapture --test-threads=1
//! (single-threaded to avoid Metal GPU contention between parallel BLIP engines)

use std::sync::Arc;
use std::sync::atomic::{AtomicU32, Ordering};

const TEST_IMAGES_DIR: &str = "/Users/liyong03/Desktop/test";

static TEST_COUNTER: AtomicU32 = AtomicU32::new(0);

fn get_test_engine() -> Arc<rust_core::PhotoSearchEngine> {
    let id = TEST_COUNTER.fetch_add(1, Ordering::SeqCst);
    let data_dir = format!("/tmp/photosearch_e2e_test_{}", id);
    let _ = std::fs::remove_dir_all(&data_dir);
    std::fs::create_dir_all(&data_dir).unwrap();
    rust_core::PhotoSearchEngine::new(data_dir).unwrap()
}

fn get_test_images() -> Vec<String> {
    let mut images = Vec::new();
    for entry in std::fs::read_dir(TEST_IMAGES_DIR).unwrap() {
        let entry = entry.unwrap();
        let path = entry.path();
        if let Some(ext) = path.extension() {
            let ext = ext.to_str().unwrap().to_lowercase();
            if ["jpg", "jpeg", "png", "heic"].contains(&ext.as_str()) {
                images.push(path.to_str().unwrap().to_string());
            }
        }
    }
    images.sort();
    images
}

fn filename(path: &str) -> &str {
    std::path::Path::new(path).file_name().unwrap().to_str().unwrap()
}

fn search(engine: &rust_core::PhotoSearchEngine, query: &str, top_k: u32) -> Vec<rust_core::SearchResult> {
    engine.search(rust_core::SearchRequest {
        query: query.to_string(),
        top_k,
        time_start: None,
        time_end: None,
        location: None,
        folder_path: None,
        min_score: None,
        keyword_filter: None,
    }).unwrap()
}

/// Index all test images and return the engine.
/// Skips images that fail to decode (e.g., HEIC not supported by the image crate).
fn setup_indexed_engine() -> Arc<rust_core::PhotoSearchEngine> {
    let engine = get_test_engine();
    let images = get_test_images();
    for img in &images {
        let result = engine.index_photo(img.clone()).unwrap();
        if !result.success {
            eprintln!("  Skipped {}: {}", filename(img), result.error.as_deref().unwrap_or("unknown"));
        }
    }
    assert!(engine.get_status().indexed_count > 0, "Should index at least some photos");
    engine
}

// =============================================================================
// Caption Generation Tests
// =============================================================================

#[test]
#[ignore]
fn test_all_photos_get_captions() {
    let engine = setup_indexed_engine();
    let photos = engine.get_photos(100, 0).unwrap();

    println!("\n=== Captions ===");
    for photo in &photos {
        println!("  {}: {:?}", filename(&photo.path), photo.description);
        assert!(photo.description.is_some(),
            "{} should have a caption", filename(&photo.path));
        assert!(!photo.description.as_ref().unwrap().is_empty(),
            "{} caption should not be empty", filename(&photo.path));
    }
}

// =============================================================================
// Search Precision Tests (matching Python test_search_relevance.py)
// =============================================================================

#[test]
#[ignore]
fn test_search_returns_only_matching_photos() {
    let engine = setup_indexed_engine();

    // "dog" should only return dog photo (lexical filter: caption must contain "dog" or synonym)
    let results = search(&engine, "dog", 20);
    println!("\nQuery 'dog': {} results", results.len());
    for r in &results {
        println!("  {:.4}  {}", r.score, filename(&r.path));
    }
    assert!(!results.is_empty(), "Should find dog photo");
    assert!(results[0].path.contains("dog"), "Top result should be dog photo");
    // All results must have dog/puppy/canine in description (lexical filter)
    for r in &results {
        let desc = r.description.as_deref().unwrap_or("").to_lowercase();
        assert!(
            desc.contains("dog") || desc.contains("puppy") || desc.contains("canine"),
            "{} should not appear for 'dog' query (desc: {})", filename(&r.path), desc
        );
    }
}

#[test]
#[ignore]
fn test_no_false_positives() {
    // Matches Python test: check_match should reject non-matching descriptions
    assert!(!rust_core::services::synonyms::check_match("food", Some("a small white house"), None));
    assert!(!rust_core::services::synonyms::check_match("animal", Some("food containers on table"), None));
    assert!(!rust_core::services::synonyms::check_match("car", Some("a cat sleeping"), None));
    assert!(!rust_core::services::synonyms::check_match("dog", Some("a city with buildings"), None));
    assert!(!rust_core::services::synonyms::check_match("ocean", Some("a dog in the grass"), None));
}

#[test]
#[ignore]
fn test_synonym_matching() {
    // Matches Python synonym tests
    assert!(rust_core::services::synonyms::check_match("dog", Some("a cute puppy playing"), None));
    assert!(rust_core::services::synonyms::check_match("kid", Some("a child on a swing"), None));
    assert!(rust_core::services::synonyms::check_match("sunset", Some("beautiful dusk over the ocean"), None));
    assert!(rust_core::services::synonyms::check_match("ocean", Some("waves on the beach"), None));
    assert!(rust_core::services::synonyms::check_match("building", Some("a small house with a porch"), None));
}

#[test]
#[ignore]
fn test_animal_search_finds_all_animals() {
    let engine = setup_indexed_engine();

    // "animal" should find both otter and dog photos
    let results = search(&engine, "animal", 20);
    println!("\nQuery 'animal': {} results", results.len());
    for r in &results {
        println!("  {:.4}  {}", r.score, filename(&r.path));
    }
    assert!(results.len() >= 2, "Should find at least otter and dog");
    let filenames: Vec<&str> = results.iter().map(|r| filename(&r.path)).collect();
    assert!(filenames.contains(&"animal.jpg"), "Should find animal.jpg");
    assert!(filenames.contains(&"dog.jpeg"), "Should find dog.jpeg");
}

#[test]
#[ignore]
fn test_pet_search_finds_animals() {
    let engine = setup_indexed_engine();

    // "pet" should expand to animal terms and find dog+otter
    let results = search(&engine, "pet", 20);
    println!("\nQuery 'pet': {} results", results.len());
    for r in &results {
        println!("  {:.4}  {}", r.score, filename(&r.path));
    }
    assert!(results.len() >= 2, "Should find at least otter and dog via synonym expansion");
}

#[test]
#[ignore]
fn test_search_no_results_for_absent_content() {
    let engine = setup_indexed_engine();

    // "car" — no car photos in test set, no captions mention car
    let results = search(&engine, "car", 20);
    assert!(results.is_empty(), "Should return no results for 'car' (no car photos)");

    // "airplane" — no airplane photos
    let results = search(&engine, "airplane", 20);
    assert!(results.is_empty(), "Should return no results for 'airplane'");
}

#[test]
#[ignore]
fn test_each_query_finds_correct_photo() {
    let engine = setup_indexed_engine();

    let cases = vec![
        ("dog", "dog.jpeg"),
        ("food", "food.jpg"),
        ("city", "city.jpg"),
        ("house", "house.jpeg"),
    ];

    for (query, expected_file) in &cases {
        let results = search(&engine, query, 5);
        println!("\nQuery '{}': {} results, top={}", query, results.len(),
            results.first().map(|r| filename(&r.path)).unwrap_or("none"));
        assert!(!results.is_empty(), "'{}' should return results", query);
        assert_eq!(filename(&results[0].path), *expected_file,
            "'{}' top result should be {}", query, expected_file);
    }
}

// =============================================================================
// Browse & Filter Tests
// =============================================================================

#[test]
#[ignore]
fn test_browse_all_returns_all_indexed() {
    let engine = setup_indexed_engine();

    let results = search(&engine, "", 100);
    let indexed = engine.get_status().indexed_count;
    assert_eq!(results.len(), indexed as usize, "Browse all should return all indexed photos");
}

#[test]
#[ignore]
fn test_folder_filter() {
    let engine = setup_indexed_engine();

    let results = engine.search(rust_core::SearchRequest {
        query: "".to_string(),
        top_k: 100,
        time_start: None,
        time_end: None,
        location: None,
        folder_path: Some(TEST_IMAGES_DIR.to_string()),
        min_score: None,
        keyword_filter: None,
    }).unwrap();
    assert!(!results.is_empty(), "Folder filter should return photos in test folder");
}

#[test]
#[ignore]
fn test_delete_and_reindex() {
    let engine = setup_indexed_engine();
    let count_before = engine.get_status().indexed_count;

    let deleted = engine.delete_folder(TEST_IMAGES_DIR.to_string()).unwrap();
    assert_eq!(deleted, count_before, "Should delete all photos in folder");
    assert_eq!(engine.get_status().indexed_count, 0);

    // Re-index
    for img in &get_test_images() {
        engine.index_photo(img.clone()).unwrap();
    }
    assert_eq!(engine.get_status().indexed_count, count_before);
}
