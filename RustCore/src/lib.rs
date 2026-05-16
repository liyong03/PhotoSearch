uniffi::setup_scaffolding!();

pub mod clip;
pub mod database;
pub mod search;
pub mod services;

use std::collections::HashSet;
use std::sync::{Arc, Mutex};

/// Hybrid scoring weight on the image-CLIP score; the rest goes to caption text-CLIP.
/// 0.6 keeps image-vision dominant but lets the caption channel veto unrelated photos
/// whose image embedding happens to score highly.
const IMAGE_WEIGHT: f32 = 0.6;
const CAPTION_WEIGHT: f32 = 1.0 - IMAGE_WEIGHT;

/// The main entry point for the PhotoSearch Rust core.
/// Wraps all subsystems (CLIP, BLIP, vector search, database, services)
/// and exposes a high-level API to Swift via UniFFI.
#[derive(uniffi::Object)]
pub struct PhotoSearchEngine {
    clip: clip::ClipEngine,
    blip: Mutex<clip::blip::BlipEngine>,
    index: search::VectorIndex,
    db: database::Database,
    geocoder: services::geocoding::GeocodingService,
}

#[derive(uniffi::Record)]
pub struct SearchResult {
    pub photo_id: String,
    pub score: f32,
    pub path: String,
    pub description: Option<String>,
    pub timestamp: Option<i64>,
}

#[derive(uniffi::Record)]
pub struct SearchRequest {
    pub query: String,
    pub top_k: u32,
    pub time_start: Option<i64>,
    pub time_end: Option<i64>,
    pub location: Option<String>,
    pub folder_path: Option<String>,
    pub min_score: Option<f32>,
    pub keyword_filter: Option<bool>,
}

#[derive(uniffi::Record)]
pub struct IndexResult {
    pub photo_id: String,
    pub success: bool,
    pub error: Option<String>,
}

#[derive(uniffi::Record)]
pub struct BackendStatus {
    pub is_ready: bool,
    pub indexed_count: u32,
    pub version: String,
}

#[derive(Debug, thiserror::Error, uniffi::Error)]
pub enum PhotoSearchError {
    #[error("Model error: {message}")]
    ModelError { message: String },
    #[error("Database error: {message}")]
    DatabaseError { message: String },
    #[error("IO error: {message}")]
    IoError { message: String },
    #[error("Image error: {message}")]
    ImageError { message: String },
}

impl From<anyhow::Error> for PhotoSearchError {
    fn from(e: anyhow::Error) -> Self {
        PhotoSearchError::ModelError {
            message: e.to_string(),
        }
    }
}

#[uniffi::export]
impl PhotoSearchEngine {
    /// Create a new PhotoSearchEngine.
    /// data_dir: path to ~/Library/Application Support/PhotoSearch
    #[uniffi::constructor]
    pub fn new(data_dir: String) -> Result<Arc<Self>, PhotoSearchError> {
        let db_path = format!("{}/photos.db", &data_dir);
        let index_path = format!("{}/photo_index", &data_dir);
        let model_cache = format!("{}/models", &data_dir);

        let db = database::Database::new(&db_path).map_err(|e| PhotoSearchError::DatabaseError {
            message: e.to_string(),
        })?;

        let index =
            search::VectorIndex::new(&index_path).map_err(|e| PhotoSearchError::IoError {
                message: e.to_string(),
            })?;

        let clip =
            clip::ClipEngine::new(&model_cache).map_err(|e| PhotoSearchError::ModelError {
                message: e.to_string(),
            })?;

        let blip = clip::blip::BlipEngine::new(&model_cache, &clip.device()).map_err(|e| {
            PhotoSearchError::ModelError {
                message: e.to_string(),
            }
        })?;

        let geocoder = services::geocoding::GeocodingService::new();

        let engine = Arc::new(Self {
            clip,
            blip: Mutex::new(blip),
            db,
            index,
            geocoder,
        });

        // One-time backfill: photos indexed before hybrid scoring (v1 index, or
        // v2 entries without caption embeddings) get their captions encoded now.
        // Cost is bounded by existing index size and only runs once per photo.
        if let Err(e) = engine.backfill_caption_embeddings() {
            log::warn!("Caption backfill failed (non-fatal): {:?}", e);
        }

        Ok(engine)
    }

    /// Encode a text query into a CLIP embedding.
    pub fn encode_text(&self, query: String) -> Result<Vec<f32>, PhotoSearchError> {
        self.clip.encode_text(&query).map_err(Into::into)
    }

    /// Encode an image file into a CLIP embedding.
    pub fn encode_image(&self, path: String) -> Result<Vec<f32>, PhotoSearchError> {
        self.clip.encode_image(&path).map_err(Into::into)
    }

    /// Generate a caption for an image file.
    pub fn generate_caption(&self, path: String) -> Result<String, PhotoSearchError> {
        let mut blip = self.blip.lock().unwrap();
        blip.generate_caption(&path).map_err(Into::into)
    }

    /// Get the backend status.
    pub fn get_status(&self) -> BackendStatus {
        BackendStatus {
            is_ready: true,
            indexed_count: self.index.len() as u32,
            version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }

    /// Search for photos matching a query.
    /// Implements full pipeline: parse query → resolve location → CLIP encode →
    /// vector search (oversampled) → filter by time/location/folder → lexical match → rank → top_k.
    pub fn search(&self, request: SearchRequest) -> Result<Vec<SearchResult>, PhotoSearchError> {
        // Browse mode: empty query returns all photos
        if request.query.trim().is_empty() {
            return self.browse_all(&request);
        }

        // 1. Parse query for embedded location
        let (semantic_query, parsed_location) =
            services::query_parser::parse_query(&request.query);
        let location = request.location.or(parsed_location);

        // 2. Resolve location to bounding box via geocoding
        let location_bbox = location
            .as_deref()
            .and_then(|loc| self.geocoder.geocode(loc));

        // 3. Encode text query with CLIP
        let query_embedding = self.clip.encode_text(&semantic_query)?;

        // 4. Vector search with oversampling (10x candidates for post-filtering)
        let oversample = (request.top_k as usize) * 10;
        let candidates = self
            .index
            .search(&query_embedding, oversample)
            .map_err(|e| PhotoSearchError::ModelError {
                message: e.to_string(),
            })?;

        // 5. Build candidate set from DB, applying all filters.
        // `keyword_filter` is repurposed: true (default) = hybrid CLIP image+caption rerank,
        // false = pure image CLIP (legacy "off" — useful for A/B comparison).
        let use_hybrid = request.keyword_filter.unwrap_or(true);
        let mut results: Vec<SearchResult> = Vec::new();
        let min_score = request.min_score.unwrap_or(0.0);

        // Pre-compute time filter IDs if needed
        let time_filter: Option<HashSet<String>> =
            if request.time_start.is_some() || request.time_end.is_some() {
                let start = request.time_start.unwrap_or(0);
                let end = request.time_end.unwrap_or(i64::MAX);
                self.db
                    .filter_by_time_range(start, end)
                    .ok()
                    .map(|ids| ids.into_iter().collect())
            } else {
                None
            };

        // Pre-compute folder filter IDs if needed
        let folder_filter: Option<HashSet<String>> =
            request.folder_path.as_deref().and_then(|folder| {
                self.db
                    .filter_by_folder(folder)
                    .ok()
                    .map(|ids| ids.into_iter().collect())
            });

        // Pre-compute location bounding box filter IDs if needed
        let location_filter: Option<HashSet<String>> = location_bbox.as_ref().and_then(|bbox| {
            self.db
                .filter_by_location(bbox.min_lat, bbox.max_lat, bbox.min_lon, bbox.max_lon)
                .ok()
                .map(|ids| ids.into_iter().collect())
        });

        for (photo_id, image_score) in candidates {
            // Time filter
            if let Some(ref filter) = time_filter {
                if !filter.contains(&photo_id) {
                    continue;
                }
            }

            // Folder filter
            if let Some(ref filter) = folder_filter {
                if !filter.contains(&photo_id) {
                    continue;
                }
            }

            // Location filter
            if let Some(ref filter) = location_filter {
                if !filter.contains(&photo_id) {
                    continue;
                }
            }

            // Hybrid score: combine image-CLIP with caption text-CLIP if available.
            // Pure-image mode (keyword_filter=false) skips the caption channel.
            let final_score = if use_hybrid {
                if let Some(caption_emb) = self.index.get_caption(&photo_id) {
                    let caption_score = search::cosine_similarity(&query_embedding, &caption_emb);
                    IMAGE_WEIGHT * image_score + CAPTION_WEIGHT * caption_score
                } else {
                    // No caption embedding (e.g. photo had no description) — fall back
                    // to the image score so it doesn't get unfairly demoted.
                    image_score
                }
            } else {
                image_score
            };

            if final_score < min_score {
                continue;
            }

            if let Ok(Some(photo)) = self.db.get_photo(&photo_id) {
                results.push(SearchResult {
                    photo_id: photo.id,
                    score: final_score,
                    path: photo.path,
                    description: photo.description,
                    timestamp: photo.timestamp,
                });
            }
        }

        // Re-sort by combined score (image-only candidate order may not match hybrid order).
        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
        results.truncate(request.top_k as usize);

        Ok(results)
    }

    /// Browse mode: return all photos with optional time/folder filtering, no query needed.
    fn browse_all(&self, request: &SearchRequest) -> Result<Vec<SearchResult>, PhotoSearchError> {
        // Start with all photo IDs, then filter
        let mut candidate_ids: Option<HashSet<String>> = None;

        // Apply time filter
        if request.time_start.is_some() || request.time_end.is_some() {
            let start = request.time_start.unwrap_or(0);
            let end = request.time_end.unwrap_or(i64::MAX);
            let ids: HashSet<String> = self
                .db
                .filter_by_time_range(start, end)
                .map_err(|e| PhotoSearchError::DatabaseError {
                    message: e.to_string(),
                })?
                .into_iter()
                .collect();
            candidate_ids = Some(ids);
        }

        // Apply folder filter
        if let Some(ref folder) = request.folder_path {
            let folder_ids: HashSet<String> = self
                .db
                .filter_by_folder(folder)
                .map_err(|e| PhotoSearchError::DatabaseError {
                    message: e.to_string(),
                })?
                .into_iter()
                .collect();
            candidate_ids = Some(match candidate_ids {
                Some(existing) => existing.intersection(&folder_ids).cloned().collect(),
                None => folder_ids,
            });
        }

        // Apply location filter
        if let Some(ref loc) = request.location {
            if let Some(bbox) = self.geocoder.geocode(loc) {
                let loc_ids: HashSet<String> = self
                    .db
                    .filter_by_location(bbox.min_lat, bbox.max_lat, bbox.min_lon, bbox.max_lon)
                    .map_err(|e| PhotoSearchError::DatabaseError {
                        message: e.to_string(),
                    })?
                    .into_iter()
                    .collect();
                candidate_ids = Some(match candidate_ids {
                    Some(existing) => existing.intersection(&loc_ids).cloned().collect(),
                    None => loc_ids,
                });
            }
        }

        // If no filters, just fetch with limit. Otherwise, fetch all and filter.
        if candidate_ids.is_none() {
            let photos = self
                .db
                .get_photos(request.top_k, 0)
                .map_err(|e| PhotoSearchError::DatabaseError {
                    message: e.to_string(),
                })?;

            return Ok(photos
                .into_iter()
                .map(|p| SearchResult {
                    photo_id: p.id,
                    score: 0.0,
                    path: p.path,
                    description: p.description,
                    timestamp: p.timestamp,
                })
                .collect());
        }

        // With filters: fetch a large batch sorted by timestamp, then filter
        let filter_ids = candidate_ids.unwrap();
        let total = self.db.photo_count().unwrap_or(0);
        let photos = self
            .db
            .get_photos(total, 0)
            .map_err(|e| PhotoSearchError::DatabaseError {
                message: e.to_string(),
            })?;

        let results: Vec<SearchResult> = photos
            .into_iter()
            .filter(|p| filter_ids.contains(&p.id))
            .take(request.top_k as usize)
            .map(|p| SearchResult {
                photo_id: p.id,
                score: 0.0,
                path: p.path,
                description: p.description,
                timestamp: p.timestamp,
            })
            .collect();

        Ok(results)
    }

    /// Index a single photo (CLIP embedding + BLIP caption + EXIF + DB).
    pub fn index_photo(&self, path: String) -> Result<IndexResult, PhotoSearchError> {
        let photo_id = database::generate_photo_id(&path);

        // Generate CLIP embedding
        let embedding = match self.clip.encode_image(&path) {
            Ok(emb) => emb,
            Err(e) => {
                return Ok(IndexResult {
                    photo_id,
                    success: false,
                    error: Some(e.to_string()),
                });
            }
        };

        // Generate BLIP caption
        let (description, tags) = match self.blip.lock().unwrap().generate_caption(&path) {
            Ok(caption) => {
                let tags = clip::blip::BlipEngine::extract_tags(&caption);
                (Some(caption), Some(tags.join(",")))
            }
            Err(e) => {
                log::warn!("BLIP caption failed for {}: {}", path, e);
                (None, None)
            }
        };

        // Extract EXIF
        let exif = services::exif::extract_exif(&path).unwrap_or_default();

        // Reverse geocode GPS coordinates to get location name
        let location_tags = if let (Some(lat), Some(lon)) = (exif.latitude, exif.longitude) {
            self.geocoder
                .reverse_geocode(lat, lon)
                .map(|place| {
                    let mut parts = Vec::new();
                    if let Some(ref city) = place.city {
                        parts.push(city.clone());
                    }
                    if let Some(ref state) = place.state {
                        parts.push(state.clone());
                    }
                    if let Some(ref country) = place.country {
                        parts.push(country.clone());
                    }
                    parts.join(",")
                })
                .unwrap_or_default()
        } else {
            String::new()
        };

        // Merge BLIP tags with location tags
        let combined_tags = match (tags, location_tags.is_empty()) {
            (Some(t), false) => Some(format!("{},{}", t, location_tags)),
            (Some(t), true) => Some(t),
            (None, false) => Some(location_tags),
            (None, true) => None,
        };

        // Store in database
        let photo = database::PhotoRecord {
            id: photo_id.clone(),
            path: path.clone(),
            timestamp: exif.timestamp,
            latitude: exif.latitude,
            longitude: exif.longitude,
            description,
            tags: combined_tags,
            camera_make: exif.camera_make,
            camera_model: exif.camera_model,
        };

        self.db
            .insert_photo(&photo)
            .map_err(|e| PhotoSearchError::DatabaseError {
                message: e.to_string(),
            })?;

        // Add to vector index
        self.index
            .add(&photo_id, &embedding)
            .map_err(|e| PhotoSearchError::IoError {
                message: e.to_string(),
            })?;

        // Encode the caption (BLIP description) into a CLIP text embedding so the
        // hybrid scorer can compare query↔caption alongside query↔image.
        if let Some(ref desc) = photo.description {
            if !desc.trim().is_empty() {
                match self.clip.encode_text(desc) {
                    Ok(cap_emb) => {
                        if let Err(e) = self.index.add_caption(&photo_id, &cap_emb) {
                            log::warn!("Failed to store caption embedding for {}: {}", photo_id, e);
                        }
                    }
                    Err(e) => log::warn!("CLIP text encode failed for caption of {}: {}", photo_id, e),
                }
            }
        }

        Ok(IndexResult {
            photo_id,
            success: true,
            error: None,
        })
    }

    /// Backfill caption embeddings for any indexed photo that has a description in
    /// the DB but no caption embedding in the vector index. Safe to call at startup;
    /// no-op once the index is fully migrated.
    pub fn backfill_caption_embeddings(&self) -> Result<u32, PhotoSearchError> {
        let mut migrated = 0u32;
        for photo_id in self.index.all_photo_ids() {
            if self.index.has_caption(&photo_id) {
                continue;
            }
            let Ok(Some(photo)) = self.db.get_photo(&photo_id) else {
                continue;
            };
            let Some(desc) = photo.description.as_deref() else {
                continue;
            };
            if desc.trim().is_empty() {
                continue;
            }
            match self.clip.encode_text(desc) {
                Ok(cap_emb) => {
                    if let Err(e) = self.index.add_caption(&photo_id, &cap_emb) {
                        log::warn!("Backfill: failed to store caption embedding for {}: {}", photo_id, e);
                        continue;
                    }
                    migrated += 1;
                    if migrated % 50 == 0 {
                        log::info!("Backfill progress: {} caption embeddings", migrated);
                    }
                }
                Err(e) => log::warn!("Backfill: CLIP text encode failed for {}: {}", photo_id, e),
            }
        }
        if migrated > 0 {
            log::info!("Backfill complete: encoded {} caption embeddings", migrated);
        }
        Ok(migrated)
    }

    /// Delete a photo from the index and database.
    pub fn delete_photo(&self, photo_id: String) -> Result<bool, PhotoSearchError> {
        self.index
            .remove(&photo_id)
            .map_err(|e| PhotoSearchError::IoError {
                message: e.to_string(),
            })?;
        self.db
            .delete_photo(&photo_id)
            .map_err(|e| PhotoSearchError::DatabaseError {
                message: e.to_string(),
            })
    }

    /// Delete all photos in a folder from the index and database.
    pub fn delete_folder(&self, folder_path: String) -> Result<u32, PhotoSearchError> {
        let photo_ids =
            self.db
                .filter_by_folder(&folder_path)
                .map_err(|e| PhotoSearchError::DatabaseError {
                    message: e.to_string(),
                })?;

        let count = photo_ids.len() as u32;
        for id in &photo_ids {
            let _ = self.index.remove(id);
            let _ = self.db.delete_photo(id);
        }

        Ok(count)
    }

    /// Get the number of indexed photos.
    pub fn indexed_count(&self) -> u32 {
        self.index.len() as u32
    }

    /// Get photos with pagination.
    pub fn get_photos(&self, limit: u32, offset: u32) -> Result<Vec<SearchResult>, PhotoSearchError> {
        let photos = self.db.get_photos(limit, offset).map_err(|e| {
            PhotoSearchError::DatabaseError {
                message: e.to_string(),
            }
        })?;

        Ok(photos
            .into_iter()
            .map(|p| SearchResult {
                photo_id: p.id,
                score: 0.0,
                path: p.path,
                description: p.description,
                timestamp: p.timestamp,
            })
            .collect())
    }

    /// Reverse geocode GPS coordinates to a place name.
    pub fn reverse_geocode(&self, lat: f64, lon: f64) -> Option<String> {
        self.geocoder
            .reverse_geocode(lat, lon)
            .map(|place| place.place_name)
    }

    /// Forward geocode a place name to coordinates (lat, lon).
    pub fn geocode(&self, place_name: String) -> Option<Vec<f64>> {
        self.geocoder.geocode(&place_name).map(|bbox| {
            vec![bbox.center_lat, bbox.center_lon]
        })
    }

    /// Health check - returns true if the engine is ready.
    pub fn is_ready(&self) -> bool {
        true
    }
}
