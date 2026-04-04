//! End-to-end integration tests for the search pipeline, database, vector index,
//! query parser, synonyms, and geocoding.
//!
//! These tests exercise the full pipeline WITHOUT requiring ML models (CLIP/BLIP).
//! They use synthetic embeddings and manually-inserted photo records.
//!
//! Run with: cargo test --test integration_test

use std::collections::HashSet;

// =============================================================================
// Synonym Tests (expanded dictionary)
// =============================================================================

#[test]
fn test_synonym_group_coverage() {
    // Verify key groups from the Python dictionary are present
    let test_cases = vec![
        ("dog", vec!["puppy", "canine", "hound", "dogs", "puppies"]),
        ("cat", vec!["kitten", "feline", "kitty", "cats", "kittens", "tabby"]),
        ("car", vec!["vehicle", "automobile", "sedan", "suv", "truck"]),
        ("beach", vec!["shore", "coast", "coastline", "seaside", "beaches"]),
        ("mountain", vec!["hill", "peak", "summit", "alpine", "highlands"]),
        ("happy", vec!["joyful", "cheerful", "smiling", "smile", "glad", "delighted"]),
        ("wedding", vec!["marriage", "bride", "groom", "ceremony", "nuptials"]),
        ("phone", vec!["smartphone", "mobile", "cell", "cellphone", "iphone"]),
        ("rain", vec!["raining", "rainy", "rainfall", "shower", "drizzle"]),
        ("city", vec!["urban", "town", "downtown", "metropolitan", "skyline"]),
    ];

    for (word, expected_synonyms) in test_cases {
        let syns = rust_core::services::synonyms::get_synonyms(word);
        for expected in expected_synonyms {
            assert!(
                syns.contains(expected),
                "'{}' synonyms should contain '{}', got: {:?}",
                word,
                expected,
                syns
            );
        }
    }
}

#[test]
fn test_animal_expansion() {
    let syns = rust_core::services::synonyms::get_synonyms("animal");
    let expected = vec!["dog", "cat", "bird", "fish", "horse", "bear", "lion",
                        "tiger", "elephant", "dolphin", "whale", "snake", "wildlife", "pet"];
    for expected_word in expected {
        assert!(
            syns.contains(expected_word),
            "'animal' synonyms should contain '{}', got: {:?}",
            expected_word,
            syns
        );
    }
}

#[test]
fn test_plural_handling() {
    // "dogs" (plural) should find the "dog" synonym group
    let syns = rust_core::services::synonyms::get_synonyms("dogs");
    assert!(syns.contains("puppy"), "dogs -> puppy");
    assert!(syns.contains("canine"), "dogs -> canine");

    // "babies" (plural) should find the "baby" group
    let syns = rust_core::services::synonyms::get_synonyms("babies");
    assert!(syns.contains("baby"), "babies -> baby");
    assert!(syns.contains("infant"), "babies -> infant");

    // "beaches" should find the "beach" group
    let syns = rust_core::services::synonyms::get_synonyms("beaches");
    assert!(syns.contains("shore"), "beaches -> shore");
    assert!(syns.contains("coast"), "beaches -> coast");
}

#[test]
fn test_check_match_with_synonyms() {
    // Direct match
    assert!(rust_core::services::synonyms::check_match(
        "dog",
        Some("a cute dog playing in the park"),
        None
    ));

    // Synonym match
    assert!(rust_core::services::synonyms::check_match(
        "dog",
        Some("a cute puppy playing in the park"),
        None
    ));

    // Plural match
    assert!(rust_core::services::synonyms::check_match(
        "dogs",
        Some("a cute puppy playing in the park"),
        None
    ));

    // Tag match
    assert!(rust_core::services::synonyms::check_match(
        "cat",
        None,
        Some("kitten,cute,small")
    ));

    // No match
    assert!(!rust_core::services::synonyms::check_match(
        "airplane",
        Some("a beautiful sunset over the ocean"),
        None
    ));

    // Empty query matches everything
    assert!(rust_core::services::synonyms::check_match(
        "",
        Some("anything"),
        None
    ));

    // Animal expansion match
    assert!(rust_core::services::synonyms::check_match(
        "animal",
        Some("a cute puppy in the garden"),
        None
    ));
}

// =============================================================================
// Query Parser Tests
// =============================================================================

#[test]
fn test_query_parser_extracts_location() {
    let cases = vec![
        ("sunset from Hawaii", "sunset", Some("Hawaii")),
        ("dogs in Central Park", "dogs", Some("Central Park")),
        ("birthday party", "birthday party", None),
        ("flowers at the park", "flowers", Some("the park")),
        ("cars", "cars", None),
        ("people at the beach", "people", Some("the beach")),
        ("landscape", "landscape", None),
    ];

    for (query, expected_semantic, expected_location) in cases {
        let (semantic, location) = rust_core::services::query_parser::parse_query(query);
        assert_eq!(
            semantic.trim(),
            expected_semantic,
            "Semantic mismatch for '{}'",
            query
        );
        assert_eq!(
            location.as_deref(),
            expected_location,
            "Location mismatch for '{}'",
            query
        );
    }
}

// =============================================================================
// Database Tests
// =============================================================================

fn create_test_db() -> rust_core::database::Database {
    rust_core::database::Database::new(":memory:").unwrap()
}

fn insert_test_photos(db: &rust_core::database::Database, count: usize) -> Vec<rust_core::database::PhotoRecord> {
    let mut photos = Vec::new();
    for i in 0..count {
        let photo = rust_core::database::PhotoRecord {
            id: format!("photo_{:04}", i),
            path: format!("/photos/folder_{}/test_{}.jpg", i % 3, i),
            timestamp: Some(1700000000 + (i as i64) * 3600),
            latitude: Some(37.0 + (i as f64) * 0.1),
            longitude: Some(-122.0 + (i as f64) * 0.1),
            description: Some(match i % 5 {
                0 => "a cute puppy playing in the garden".to_string(),
                1 => "beautiful sunset over the ocean".to_string(),
                2 => "city skyline with tall buildings".to_string(),
                3 => "family having a birthday party".to_string(),
                4 => "mountain landscape with snow".to_string(),
                _ => unreachable!(),
            }),
            tags: Some(match i % 5 {
                0 => "dog,puppy,garden,outdoor".to_string(),
                1 => "sunset,ocean,beach,nature".to_string(),
                2 => "city,building,urban,skyline".to_string(),
                3 => "family,birthday,party,celebration".to_string(),
                4 => "mountain,snow,landscape,winter".to_string(),
                _ => unreachable!(),
            }),
            camera_make: Some("TestCam".to_string()),
            camera_model: Some("Model X".to_string()),
        };
        db.insert_photo(&photo).unwrap();
        photos.push(photo);
    }
    photos
}

#[test]
fn test_database_crud() {
    let db = create_test_db();
    let photos = insert_test_photos(&db, 20);

    // Count
    assert_eq!(db.photo_count().unwrap(), 20);

    // Get by ID
    let photo = db.get_photo("photo_0005").unwrap().unwrap();
    assert_eq!(photo.path, "/photos/folder_2/test_5.jpg");

    // Delete
    assert!(db.delete_photo("photo_0005").unwrap());
    assert_eq!(db.photo_count().unwrap(), 19);
    assert!(db.get_photo("photo_0005").unwrap().is_none());

    // Non-existent delete
    assert!(!db.delete_photo("nonexistent").unwrap());
}

#[test]
fn test_database_time_range_filter() {
    let db = create_test_db();
    let photos = insert_test_photos(&db, 20);

    // Filter for photos 5-10 (timestamps 1700018000 to 1700036000)
    let start = 1700000000 + 5 * 3600;
    let end = 1700000000 + 10 * 3600;
    let ids = db.filter_by_time_range(start, end).unwrap();
    assert_eq!(ids.len(), 6); // photos 5,6,7,8,9,10
}

#[test]
fn test_database_location_filter() {
    let db = create_test_db();
    insert_test_photos(&db, 20);

    // Filter for photos in a latitude range
    let ids = db.filter_by_location(37.5, 38.0, -122.0, -121.0).unwrap();
    assert!(!ids.is_empty());

    // All returned photos should have coordinates in range
    for id in &ids {
        let photo = db.get_photo(id).unwrap().unwrap();
        let lat = photo.latitude.unwrap();
        let lon = photo.longitude.unwrap();
        assert!(lat >= 37.5 && lat <= 38.0, "lat {} out of range", lat);
        assert!(lon >= -122.0 && lon <= -121.0, "lon {} out of range", lon);
    }
}

#[test]
fn test_database_folder_filter() {
    let db = create_test_db();
    insert_test_photos(&db, 20);

    let ids = db.filter_by_folder("/photos/folder_0/").unwrap();
    // Photos 0, 3, 6, 9, 12, 15, 18 have folder_0
    assert_eq!(ids.len(), 7);
}

#[test]
fn test_database_pagination_sorted_by_timestamp() {
    let db = create_test_db();
    insert_test_photos(&db, 20);

    // Get first page
    let page1 = db.get_photos(5, 0).unwrap();
    assert_eq!(page1.len(), 5);

    // Should be sorted by timestamp DESC (newest first)
    for i in 1..page1.len() {
        let prev_ts = page1[i - 1].timestamp.unwrap_or(0);
        let curr_ts = page1[i].timestamp.unwrap_or(0);
        assert!(
            prev_ts >= curr_ts,
            "Photos should be sorted by timestamp DESC: {} < {}",
            prev_ts,
            curr_ts
        );
    }

    // Get second page
    let page2 = db.get_photos(5, 5).unwrap();
    assert_eq!(page2.len(), 5);

    // No overlap between pages
    let page1_ids: HashSet<_> = page1.iter().map(|p| &p.id).collect();
    let page2_ids: HashSet<_> = page2.iter().map(|p| &p.id).collect();
    assert!(page1_ids.is_disjoint(&page2_ids));
}

#[test]
fn test_database_full_text_search() {
    let db = create_test_db();
    insert_test_photos(&db, 20);

    let ids = db.full_text_search("puppy").unwrap();
    assert!(!ids.is_empty(), "FTS should find photos with 'puppy'");

    let ids = db.full_text_search("sunset ocean").unwrap();
    assert!(!ids.is_empty(), "FTS should find photos with 'sunset ocean'");
}

// =============================================================================
// Database Migration Tests
// =============================================================================

#[test]
fn test_database_migration_from_legacy_python_schema() {
    let dir = tempfile::tempdir().unwrap();
    let db_path = dir.path().join("photos.db");
    let db_path_str = db_path.to_str().unwrap();

    // Create a database with the old Python schema
    {
        let conn = rusqlite::Connection::open(&db_path).unwrap();
        conn.execute_batch(
            "CREATE TABLE photos (
                id TEXT PRIMARY KEY,
                file_path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                timestamp DATETIME,
                latitude REAL,
                longitude REAL,
                city TEXT,
                state TEXT,
                country TEXT,
                place_name TEXT,
                description TEXT,
                tags TEXT,
                indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE photos_fts USING fts5(
                id, description, city, state, country, place_name, tags,
                content='photos', content_rowid='rowid'
            );

            CREATE TRIGGER photos_ai AFTER INSERT ON photos BEGIN
                INSERT INTO photos_fts(rowid, id, description, city, state, country, place_name, tags)
                VALUES (NEW.rowid, NEW.id, NEW.description, NEW.city, NEW.state, NEW.country, NEW.place_name, NEW.tags);
            END;

            CREATE TRIGGER photos_ad AFTER DELETE ON photos BEGIN
                INSERT INTO photos_fts(photos_fts, rowid, id, description, city, state, country, place_name, tags)
                VALUES ('delete', OLD.rowid, OLD.id, OLD.description, OLD.city, OLD.state, OLD.country, OLD.place_name, OLD.tags);
            END;

            CREATE TRIGGER photos_au AFTER UPDATE ON photos BEGIN
                INSERT INTO photos_fts(photos_fts, rowid, id, description, city, state, country, place_name, tags)
                VALUES ('delete', OLD.rowid, OLD.id, OLD.description, OLD.city, OLD.state, OLD.country, OLD.place_name, OLD.tags);
                INSERT INTO photos_fts(rowid, id, description, city, state, country, place_name, tags)
                VALUES (NEW.rowid, NEW.id, NEW.description, NEW.city, NEW.state, NEW.country, NEW.place_name, NEW.tags);
            END;"
        ).unwrap();
    }

    // Now open with the Rust Database — should migrate successfully
    let db = rust_core::database::Database::new(db_path_str).unwrap();

    // Verify the new schema works by inserting a photo
    let photo = rust_core::database::PhotoRecord {
        id: "test_001".to_string(),
        path: "/photos/test.jpg".to_string(),
        timestamp: Some(1700000000),
        latitude: Some(37.0),
        longitude: Some(-122.0),
        description: Some("a test photo".to_string()),
        tags: Some("test,photo".to_string()),
        camera_make: None,
        camera_model: None,
    };
    db.insert_photo(&photo).unwrap();
    assert_eq!(db.photo_count().unwrap(), 1);

    // FTS should work too
    let results = db.full_text_search("test").unwrap();
    assert!(!results.is_empty());
}

// =============================================================================
// Vector Index Tests
// =============================================================================

#[test]
fn test_vector_index_basic_operations() {
    let index = rust_core::search::VectorIndex::new("/tmp/test_integration_idx").unwrap();

    let dim = 512;

    // Create test embeddings
    let mut embeddings: Vec<(String, Vec<f32>)> = Vec::new();
    for i in 0..50 {
        let mut emb = vec![0.0f32; dim];
        emb[i % dim] = 1.0;
        emb[(i * 3) % dim] += 0.5;
        // Normalize
        let norm: f32 = emb.iter().map(|x| x * x).sum::<f32>().sqrt();
        for v in &mut emb {
            *v /= norm;
        }
        let id = format!("vec_{:04}", i);
        index.add(&id, &emb).unwrap();
        embeddings.push((id, emb));
    }

    assert_eq!(index.len(), 50);

    // Search for embedding 0 — should find itself first
    let results = index.search(&embeddings[0].1, 5).unwrap();
    assert_eq!(results[0].0, "vec_0000");
    assert!((results[0].1 - 1.0).abs() < 0.001);

    // Scores should be descending
    for i in 1..results.len() {
        assert!(results[i - 1].1 >= results[i].1);
    }

    // Remove and verify
    index.remove("vec_0000").unwrap();
    assert_eq!(index.len(), 49);
    let results = index.search(&embeddings[0].1, 5).unwrap();
    assert_ne!(results[0].0, "vec_0000");

    // Cleanup
    let _ = std::fs::remove_file("/tmp/test_integration_idx");
}

// =============================================================================
// Search Pipeline Integration Tests (using DB + VectorIndex directly)
// =============================================================================

/// Helper to set up a test search environment with DB, index, and synthetic data.
struct TestSearchEnv {
    db: rust_core::database::Database,
    index: rust_core::search::VectorIndex,
}

impl TestSearchEnv {
    fn new(name: &str) -> Self {
        let idx_path = format!("/tmp/test_search_env_{}", name);
        let _ = std::fs::remove_file(&idx_path);
        Self {
            db: rust_core::database::Database::new(":memory:").unwrap(),
            index: rust_core::search::VectorIndex::new(&idx_path).unwrap(),
        }
    }

    fn add_photo(
        &self,
        id: &str,
        path: &str,
        description: &str,
        tags: &str,
        timestamp: i64,
        lat: Option<f64>,
        lon: Option<f64>,
        embedding_direction: usize,
    ) {
        let dim = 512;
        let mut emb = vec![0.0f32; dim];
        emb[embedding_direction % dim] = 1.0;
        let norm: f32 = emb.iter().map(|x| x * x).sum::<f32>().sqrt();
        for v in &mut emb {
            *v /= norm;
        }

        let photo = rust_core::database::PhotoRecord {
            id: id.to_string(),
            path: path.to_string(),
            timestamp: Some(timestamp),
            latitude: lat,
            longitude: lon,
            description: Some(description.to_string()),
            tags: Some(tags.to_string()),
            camera_make: None,
            camera_model: None,
        };

        self.db.insert_photo(&photo).unwrap();
        self.index.add(id, &emb).unwrap();
    }

    fn search_pipeline(
        &self,
        query: &str,
        top_k: usize,
        time_start: Option<i64>,
        time_end: Option<i64>,
        folder_path: Option<&str>,
    ) -> Vec<(String, f32)> {
        // Simulate the search pipeline from lib.rs without needing CLIP
        let (semantic_query, _location) = rust_core::services::query_parser::parse_query(query);

        if query.trim().is_empty() {
            // Browse mode
            let photos = self.db.get_photos(top_k as u32, 0).unwrap();
            return photos
                .into_iter()
                .map(|p| (p.id, 0.0))
                .collect();
        }

        // Create a synthetic query embedding pointing in direction 0
        let dim = 512;
        let mut query_emb = vec![0.0f32; dim];
        query_emb[0] = 1.0; // Always points in direction 0 for test

        let oversample = top_k * 10;
        let candidates = self.index.search(&query_emb, oversample).unwrap();

        // Apply filters
        let time_filter: Option<HashSet<String>> = if time_start.is_some() || time_end.is_some() {
            let start = time_start.unwrap_or(0);
            let end = time_end.unwrap_or(i64::MAX);
            Some(self.db.filter_by_time_range(start, end).unwrap().into_iter().collect())
        } else {
            None
        };

        let folder_filter: Option<HashSet<String>> = folder_path.map(|f| {
            self.db.filter_by_folder(f).unwrap().into_iter().collect()
        });

        let mut results = Vec::new();
        for (photo_id, score) in candidates {
            if let Some(ref filter) = time_filter {
                if !filter.contains(&photo_id) {
                    continue;
                }
            }
            if let Some(ref filter) = folder_filter {
                if !filter.contains(&photo_id) {
                    continue;
                }
            }
            if let Ok(Some(photo)) = self.db.get_photo(&photo_id) {
                if !rust_core::services::synonyms::check_match(
                    &semantic_query,
                    photo.description.as_deref(),
                    photo.tags.as_deref(),
                ) {
                    continue;
                }
                results.push((photo_id, score));
                if results.len() >= top_k {
                    break;
                }
            }
        }

        results
    }
}

#[test]
fn test_search_pipeline_basic_query() {
    let env = TestSearchEnv::new("basic");

    env.add_photo("p1", "/photos/dog.jpg", "a cute puppy playing", "dog,puppy,garden", 1700000000, None, None, 0);
    env.add_photo("p2", "/photos/sunset.jpg", "beautiful sunset", "sunset,ocean", 1700003600, None, None, 1);
    env.add_photo("p3", "/photos/city.jpg", "city skyline", "city,building", 1700007200, None, None, 2);

    // Search for "dog" — should find p1 via synonym match (puppy)
    let results = env.search_pipeline("dog", 10, None, None, None);
    assert!(!results.is_empty(), "Should find dog photos");
    assert!(results.iter().any(|(id, _)| id == "p1"), "Should find p1 (puppy = dog synonym)");

    // Search for "sunset" — should find p2
    let results = env.search_pipeline("sunset", 10, None, None, None);
    assert!(results.iter().any(|(id, _)| id == "p2"), "Should find p2 (sunset)");

    // Search for non-matching query
    let results = env.search_pipeline("airplane", 10, None, None, None);
    assert!(results.is_empty(), "Should not find airplane photos");

    // Cleanup
    let _ = std::fs::remove_file("/tmp/test_search_env_basic");
}

#[test]
fn test_search_pipeline_with_time_filter() {
    let env = TestSearchEnv::new("time");

    // All photos match "dog" via description, but at different times
    for i in 0..10 {
        env.add_photo(
            &format!("p{}", i),
            &format!("/photos/dog_{}.jpg", i),
            "a cute puppy playing",
            "dog,puppy",
            1700000000 + i * 3600,
            None,
            None,
            0,
        );
    }

    // Filter to photos 3-6
    let start = 1700000000 + 3 * 3600;
    let end = 1700000000 + 6 * 3600;
    let results = env.search_pipeline("dog", 10, Some(start), Some(end), None);
    assert_eq!(results.len(), 4, "Should find photos 3,4,5,6");

    let _ = std::fs::remove_file("/tmp/test_search_env_time");
}

#[test]
fn test_search_pipeline_with_folder_filter() {
    let env = TestSearchEnv::new("folder");

    env.add_photo("p1", "/photos/vacations/beach.jpg", "a cute puppy on beach", "dog,beach", 1700000000, None, None, 0);
    env.add_photo("p2", "/photos/work/meeting.jpg", "puppy in office", "dog,office", 1700003600, None, None, 0);
    env.add_photo("p3", "/photos/vacations/sunset.jpg", "puppy at sunset", "dog,sunset", 1700007200, None, None, 0);

    let results = env.search_pipeline("dog", 10, None, None, Some("/photos/vacations/"));
    assert_eq!(results.len(), 2, "Should find only vacation photos");
    let ids: Vec<_> = results.iter().map(|(id, _)| id.as_str()).collect();
    assert!(ids.contains(&"p1"));
    assert!(ids.contains(&"p3"));

    let _ = std::fs::remove_file("/tmp/test_search_env_folder");
}

#[test]
fn test_search_pipeline_synonym_matching() {
    let env = TestSearchEnv::new("synonym");

    env.add_photo("p1", "/photos/1.jpg", "a canine running", "hound,running", 1700000000, None, None, 0);
    env.add_photo("p2", "/photos/2.jpg", "a feline sleeping", "kitty,sleeping", 1700003600, None, None, 0);
    env.add_photo("p3", "/photos/3.jpg", "an automobile on highway", "sedan,driving", 1700007200, None, None, 0);

    // "dog" should match "canine" and "hound"
    let results = env.search_pipeline("dog", 10, None, None, None);
    assert!(results.iter().any(|(id, _)| id == "p1"), "dog -> canine/hound");

    // "cat" should match "feline" and "kitty"
    let results = env.search_pipeline("cat", 10, None, None, None);
    assert!(results.iter().any(|(id, _)| id == "p2"), "cat -> feline/kitty");

    // "car" should match "automobile" and "sedan"
    let results = env.search_pipeline("car", 10, None, None, None);
    assert!(results.iter().any(|(id, _)| id == "p3"), "car -> automobile/sedan");

    let _ = std::fs::remove_file("/tmp/test_search_env_synonym");
}

#[test]
fn test_search_pipeline_browse_mode() {
    let env = TestSearchEnv::new("browse");

    for i in 0..10 {
        env.add_photo(
            &format!("p{}", i),
            &format!("/photos/{}.jpg", i),
            &format!("photo {}", i),
            "test",
            1700000000 + i * 3600,
            None,
            None,
            i as usize,
        );
    }

    // Empty query = browse mode, returns all sorted by timestamp DESC
    let results = env.search_pipeline("", 5, None, None, None);
    assert_eq!(results.len(), 5);
    // First result should be the newest (p9)
    assert_eq!(results[0].0, "p9");

    let _ = std::fs::remove_file("/tmp/test_search_env_browse");
}

#[test]
fn test_search_pipeline_query_with_location_parsing() {
    let env = TestSearchEnv::new("qparse");

    env.add_photo("p1", "/photos/1.jpg", "sunset over the ocean", "sunset,ocean,dusk", 1700000000, None, None, 0);
    env.add_photo("p2", "/photos/2.jpg", "dog in the park", "dog,park", 1700003600, None, None, 0);

    // "sunset from Hawaii" should parse to semantic="sunset", location="Hawaii"
    // It should still match p1 via "sunset" synonym match (sunset -> dusk, etc.)
    let results = env.search_pipeline("sunset from Hawaii", 10, None, None, None);
    assert!(results.iter().any(|(id, _)| id == "p1"), "Should match sunset via semantic query");

    let _ = std::fs::remove_file("/tmp/test_search_env_qparse");
}

// =============================================================================
// Geocoding Tests (unit level, no network required)
// =============================================================================

#[test]
fn test_geocoding_service_creation() {
    // Just verify the service can be created without panicking
    let _service = rust_core::services::geocoding::GeocodingService::new();
}

// =============================================================================
// EXIF Tests
// =============================================================================

#[test]
fn test_exif_returns_none_for_nonexistent_file() {
    let result = rust_core::services::exif::extract_exif("/nonexistent/file.jpg");
    assert!(result.is_none());
}

// =============================================================================
// Combined: Lexical Filter + Time + Folder
// =============================================================================

#[test]
fn test_combined_filters() {
    let env = TestSearchEnv::new("combined");

    // Create photos: some match "dog", at different times, in different folders
    env.add_photo("p1", "/photos/a/1.jpg", "puppy in garden", "dog,garden", 1700000000, None, None, 0);
    env.add_photo("p2", "/photos/a/2.jpg", "puppy at beach", "dog,beach", 1700010000, None, None, 0);
    env.add_photo("p3", "/photos/b/3.jpg", "puppy in snow", "dog,snow", 1700020000, None, None, 0);
    env.add_photo("p4", "/photos/a/4.jpg", "cat sleeping", "cat,home", 1700005000, None, None, 0);

    // "dog" + folder /photos/a/ + time range covering p1 and p2
    let results = env.search_pipeline(
        "dog",
        10,
        Some(1700000000),
        Some(1700015000),
        Some("/photos/a/"),
    );

    let ids: Vec<_> = results.iter().map(|(id, _)| id.as_str()).collect();
    assert!(ids.contains(&"p1"), "Should include p1 (dog, folder a, in time range)");
    assert!(ids.contains(&"p2"), "Should include p2 (dog, folder a, in time range)");
    assert!(!ids.contains(&"p3"), "Should exclude p3 (wrong folder)");
    assert!(!ids.contains(&"p4"), "Should exclude p4 (not a dog photo)");

    let _ = std::fs::remove_file("/tmp/test_search_env_combined");
}

// =============================================================================
// Edge Cases
// =============================================================================

#[test]
fn test_empty_database_search() {
    let env = TestSearchEnv::new("empty");
    let results = env.search_pipeline("dog", 10, None, None, None);
    assert!(results.is_empty());
    let _ = std::fs::remove_file("/tmp/test_search_env_empty");
}

#[test]
fn test_empty_database_browse() {
    let env = TestSearchEnv::new("empty_browse");
    let results = env.search_pipeline("", 10, None, None, None);
    assert!(results.is_empty());
    let _ = std::fs::remove_file("/tmp/test_search_env_empty_browse");
}

#[test]
fn test_special_characters_in_query() {
    let env = TestSearchEnv::new("special");
    env.add_photo("p1", "/photos/1.jpg", "a cute dog", "dog", 1700000000, None, None, 0);

    let results = env.search_pipeline("dog's toy", 10, None, None, None);
    // Should still work — "dog" matches via tokenization
    assert!(!results.is_empty(), "Should handle special characters gracefully");

    let _ = std::fs::remove_file("/tmp/test_search_env_special");
}

#[test]
fn test_photo_id_generation_deterministic() {
    let id1 = rust_core::database::generate_photo_id("/photos/test.jpg");
    let id2 = rust_core::database::generate_photo_id("/photos/test.jpg");
    assert_eq!(id1, id2, "Same path should generate same ID");

    let id3 = rust_core::database::generate_photo_id("/photos/other.jpg");
    assert_ne!(id1, id3, "Different paths should generate different IDs");
}
