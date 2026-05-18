uniffi::setup_scaffolding!();

pub mod clip;
pub mod database;
pub mod search;
pub mod services;

use std::collections::HashSet;
use std::sync::{Arc, Mutex};

/// Relevance cutoff for plain semantic searches. SigLIP cosine scores have no
/// absolute meaning, but a result far below the top score is noise. Results
/// scoring below `top_score * RELEVANCE_RATIO` are dropped. Skipped when a
/// structured (time/folder/location) filter already defines the result set.
const RELEVANCE_RATIO: f32 = 0.35;

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

        // Model-change migration: if the vector index is empty but the database
        // has photos, the index was discarded because it was built with a
        // different model (or the file was lost). Rebuild embeddings from the
        // stored photo records — this re-runs CLIP/SigLIP encoding but reuses
        // the BLIP captions already in the DB, so it skips the slow captioning.
        let needs_reindex = engine.index.len() == 0
            && engine.db.photo_count().unwrap_or(0) > 0;
        if needs_reindex {
            if let Err(e) = engine.reindex_from_database() {
                log::warn!("Re-index from database failed (non-fatal): {:?}", e);
            }
        }

        Ok(engine)
    }

    /// Rebuild image embeddings from the photo records already in the database.
    ///
    /// Used after a model change: the BLIP captions are kept (re-captioning is
    /// the expensive part), only the SigLIP image embeddings are recomputed.
    /// Photos whose image file is missing are skipped.
    pub fn reindex_from_database(&self) -> Result<u32, PhotoSearchError> {
        let total = self.db.photo_count().unwrap_or(0);
        log::info!("Re-indexing {total} photos from database (model change detected)...");

        let mut done = 0u32;
        let mut offset = 0u32;
        const BATCH: u32 = 200;
        loop {
            let photos = self
                .db
                .get_photos(BATCH, offset)
                .map_err(|e| PhotoSearchError::DatabaseError { message: e.to_string() })?;
            if photos.is_empty() {
                break;
            }
            for photo in &photos {
                match self.clip.encode_image(&photo.path) {
                    Ok(emb) => {
                        if let Err(e) = self.index.add(&photo.id, &emb) {
                            log::warn!("reindex: store image emb failed for {}: {e}", photo.id);
                        }
                    }
                    Err(e) => {
                        log::warn!("reindex: image encode failed for {}: {e}", photo.path);
                    }
                }
                done += 1;
            }
            offset += BATCH;
            log::info!("  re-indexed {done}/{total}");
        }
        log::info!("Re-index complete: {done} photos");
        Ok(done)
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
    /// Pipeline: parse query → resolve location → SigLIP text encode →
    /// vector search (oversampled) → filter by time/location/folder → rank → top_k.
    pub fn search(&self, request: SearchRequest) -> Result<Vec<SearchResult>, PhotoSearchError> {
        // Browse mode: empty query returns all photos
        if request.query.trim().is_empty() {
            return self.browse_all(&request);
        }

        // 1. Recover a location from the query text only if the caller did
        //    not supply one. The query itself is NOT stripped — keeping the
        //    place name lets SigLIP visually match photos that have no GPS.
        let (_, parsed_location) =
            services::query_parser::parse_query(&request.query);
        let location = request.location.clone().or(parsed_location);

        // 2. Resolve location to bounding box via geocoding
        let location_bbox = location
            .as_deref()
            .and_then(|loc| self.geocoder.geocode(loc));

        // 3. Encode the full query text with SigLIP
        let query_embedding = self.clip.encode_text(&request.query)?;

        // 4. Vector search with oversampling (10x candidates for post-filtering)
        let oversample = (request.top_k as usize) * 10;
        let candidates = self
            .index
            .search(&query_embedding, oversample)
            .map_err(|e| PhotoSearchError::ModelError {
                message: e.to_string(),
            })?;

        // 5. Build candidate set from DB, applying all filters. Photos are
        // ranked purely by SigLIP image-embedding similarity.
        //
        // A structured filter (time / folder / location) defines the result
        // set on its own; the relevance cutoff below is skipped when one is
        // active, otherwise a generic query would wrongly drop filtered photos.
        let has_structured_filter = request.time_start.is_some()
            || request.time_end.is_some()
            || request.folder_path.is_some()
            || location_bbox.is_some();

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

        // Soft location filter: a geotagged photo outside the bounding box is
        // excluded, but a photo with no GPS is kept (its location is unknown,
        // so it cannot be proven to be elsewhere). `in_bbox` is the set inside
        // the box; `geotagged` is every photo that has GPS at all.
        let in_bbox: Option<HashSet<String>> = location_bbox.as_ref().and_then(|bbox| {
            self.db
                .filter_by_location(bbox.min_lat, bbox.max_lat, bbox.min_lon, bbox.max_lon)
                .ok()
                .map(|ids| ids.into_iter().collect())
        });
        let geotagged: Option<HashSet<String>> = if in_bbox.is_some() {
            self.db
                .photos_with_gps()
                .ok()
                .map(|ids| ids.into_iter().collect())
        } else {
            None
        };

        // (result, location_confirmed): photos whose GPS proves they are
        // inside the requested location are ranked above the rest.
        let mut scored: Vec<(SearchResult, bool)> = Vec::new();

        for (photo_id, image_score) in candidates {
            // Time filter (hard)
            if let Some(ref filter) = time_filter {
                if !filter.contains(&photo_id) {
                    continue;
                }
            }

            // Folder filter (hard)
            if let Some(ref filter) = folder_filter {
                if !filter.contains(&photo_id) {
                    continue;
                }
            }

            // Soft location filter: drop only geotagged photos that fall
            // outside the box; photos with no GPS pass through. A photo
            // whose GPS is inside the box is a confirmed location match.
            let location_confirmed = match (&in_bbox, &geotagged) {
                (Some(in_bbox), Some(geotagged)) => {
                    if geotagged.contains(&photo_id) && !in_bbox.contains(&photo_id) {
                        continue;
                    }
                    in_bbox.contains(&photo_id)
                }
                _ => false,
            };

            if let Ok(Some(photo)) = self.db.get_photo(&photo_id) {
                scored.push((
                    SearchResult {
                        photo_id: photo.id,
                        score: image_score,
                        path: photo.path,
                        description: photo.description,
                        timestamp: photo.timestamp,
                    },
                    location_confirmed,
                ));
            }
        }

        // GPS-confirmed location matches first, then by SigLIP score.
        scored.sort_by(|a, b| {
            b.1.cmp(&a.1)
                .then(b.0.score.partial_cmp(&a.0.score).unwrap_or(std::cmp::Ordering::Equal))
        });

        // Relevance cutoff for plain semantic searches: drop results that fall
        // far below the top score (noise). The absolute score is meaningless;
        // the ratio to the best score is the signal.
        if !has_structured_filter {
            if let Some((top, _)) = scored.first() {
                let top_score = top.score;
                if top_score > 0.0 {
                    let cutoff = top_score * RELEVANCE_RATIO;
                    scored.retain(|(r, _)| r.score >= cutoff);
                }
            }
        }

        let results: Vec<SearchResult> = scored
            .into_iter()
            .take(request.top_k as usize)
            .map(|(r, _)| r)
            .collect();

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

        Ok(IndexResult {
            photo_id,
            success: true,
            error: None,
        })
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
