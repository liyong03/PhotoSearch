use anyhow::{Context, Result};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

const EMBEDDING_DIM: usize = 512;

/// On-disk format magic + version. v1 had no magic header (raw count+entries).
/// v2 adds a parallel map of caption text embeddings.
const MAGIC: &[u8; 4] = b"PSVI";
const FORMAT_VERSION: u32 = 2;

/// In-memory vector index with brute-force cosine similarity search.
/// Stores image embeddings and (optionally) caption text embeddings per photo.
pub struct VectorIndex {
    inner: Mutex<VectorIndexInner>,
}

struct VectorIndexInner {
    /// Map from photo_id to image embedding vector.
    embeddings: HashMap<String, Vec<f32>>,
    /// Map from photo_id to caption text embedding vector. May be missing
    /// for photos indexed before v2 or with no description.
    caption_embeddings: HashMap<String, Vec<f32>>,
    /// Path to persist the index on disk.
    index_path: PathBuf,
}

impl VectorIndex {
    /// Create or load a vector index.
    pub fn new(index_path: &str) -> Result<Self> {
        let path = PathBuf::from(index_path);
        let mut inner = VectorIndexInner {
            embeddings: HashMap::new(),
            caption_embeddings: HashMap::new(),
            index_path: path.clone(),
        };

        if path.exists() {
            inner.load().context("Failed to load vector index")?;
        }

        Ok(Self {
            inner: Mutex::new(inner),
        })
    }

    /// Add an image embedding for a photo.
    pub fn add(&self, photo_id: &str, embedding: &[f32]) -> Result<()> {
        let mut inner = self.inner.lock().unwrap();
        assert_eq!(embedding.len(), EMBEDDING_DIM, "Embedding must be {EMBEDDING_DIM}-dim");
        inner.embeddings.insert(photo_id.to_string(), embedding.to_vec());
        inner.save()?;
        Ok(())
    }

    /// Add a caption text embedding for a photo.
    pub fn add_caption(&self, photo_id: &str, embedding: &[f32]) -> Result<()> {
        let mut inner = self.inner.lock().unwrap();
        assert_eq!(embedding.len(), EMBEDDING_DIM, "Caption embedding must be {EMBEDDING_DIM}-dim");
        inner.caption_embeddings.insert(photo_id.to_string(), embedding.to_vec());
        inner.save()?;
        Ok(())
    }

    /// Get a copy of the caption embedding for a photo, if present.
    pub fn get_caption(&self, photo_id: &str) -> Option<Vec<f32>> {
        self.inner.lock().unwrap().caption_embeddings.get(photo_id).cloned()
    }

    /// Whether the photo has a caption embedding stored.
    pub fn has_caption(&self, photo_id: &str) -> bool {
        self.inner.lock().unwrap().caption_embeddings.contains_key(photo_id)
    }

    /// All photo_ids that have an image embedding (for migration scans).
    pub fn all_photo_ids(&self) -> Vec<String> {
        self.inner.lock().unwrap().embeddings.keys().cloned().collect()
    }

    /// Remove an embedding (both image and caption).
    pub fn remove(&self, photo_id: &str) -> Result<()> {
        let mut inner = self.inner.lock().unwrap();
        inner.embeddings.remove(photo_id);
        inner.caption_embeddings.remove(photo_id);
        inner.save()?;
        Ok(())
    }

    /// Search for the top_k most similar image embeddings to the query.
    /// Returns (photo_id, score) pairs sorted by descending score.
    pub fn search(&self, query: &[f32], top_k: usize) -> Result<Vec<(String, f32)>> {
        let inner = self.inner.lock().unwrap();
        assert_eq!(query.len(), EMBEDDING_DIM, "Query must be {EMBEDDING_DIM}-dim");

        let mut scores: Vec<(String, f32)> = inner
            .embeddings
            .iter()
            .map(|(id, emb)| (id.clone(), cosine_similarity(query, emb)))
            .collect();

        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scores.truncate(top_k);

        Ok(scores)
    }

    pub fn len(&self) -> usize {
        self.inner.lock().unwrap().embeddings.len()
    }

    pub fn caption_len(&self) -> usize {
        self.inner.lock().unwrap().caption_embeddings.len()
    }
}

impl VectorIndexInner {
    /// Save the index in v2 format:
    /// [magic 4][version u32][image_count u32][image entries...]
    /// [caption_count u32][caption entries...]
    /// Each entry: [id_len u32][id bytes][512 × f32 LE]
    fn save(&self) -> Result<()> {
        if let Some(parent) = self.index_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let mut data = Vec::new();
        data.extend_from_slice(MAGIC);
        data.extend_from_slice(&FORMAT_VERSION.to_le_bytes());

        write_map(&mut data, &self.embeddings);
        write_map(&mut data, &self.caption_embeddings);

        // Atomic write: tmp + rename, so a crash mid-save doesn't corrupt the index.
        let tmp = self.index_path.with_extension("tmp");
        fs::write(&tmp, data)?;
        fs::rename(&tmp, &self.index_path)?;
        Ok(())
    }

    fn load(&mut self) -> Result<()> {
        let data = fs::read(&self.index_path)?;
        if data.len() >= 4 && &data[0..4] == MAGIC {
            self.load_v2(&data)
        } else {
            self.load_v1(&data)
        }
    }

    fn load_v2(&mut self, data: &[u8]) -> Result<()> {
        let mut offset = 4; // skip magic
        let version = u32::from_le_bytes(data[offset..offset + 4].try_into()?);
        offset += 4;
        if version != FORMAT_VERSION {
            anyhow::bail!("Unsupported index version: {version}");
        }

        read_map(data, &mut offset, &mut self.embeddings)?;
        read_map(data, &mut offset, &mut self.caption_embeddings)?;

        log::info!(
            "Loaded {} image embeddings and {} caption embeddings (v2)",
            self.embeddings.len(),
            self.caption_embeddings.len()
        );
        Ok(())
    }

    /// Legacy v1 loader: just `[count u32][entries...]` of image embeddings.
    fn load_v1(&mut self, data: &[u8]) -> Result<()> {
        let mut offset = 0;
        if data.len() < 4 {
            return Ok(());
        }
        read_map(data, &mut offset, &mut self.embeddings)?;
        log::info!(
            "Loaded {} image embeddings (legacy v1) — caption embeddings will be backfilled",
            self.embeddings.len()
        );
        Ok(())
    }
}

fn write_map(out: &mut Vec<u8>, map: &HashMap<String, Vec<f32>>) {
    let count = map.len() as u32;
    out.extend_from_slice(&count.to_le_bytes());
    for (id, emb) in map {
        let id_bytes = id.as_bytes();
        out.extend_from_slice(&(id_bytes.len() as u32).to_le_bytes());
        out.extend_from_slice(id_bytes);
        for val in emb {
            out.extend_from_slice(&val.to_le_bytes());
        }
    }
}

fn read_map(data: &[u8], offset: &mut usize, map: &mut HashMap<String, Vec<f32>>) -> Result<()> {
    let count = u32::from_le_bytes(data[*offset..*offset + 4].try_into()?) as usize;
    *offset += 4;
    for _ in 0..count {
        let id_len = u32::from_le_bytes(data[*offset..*offset + 4].try_into()?) as usize;
        *offset += 4;
        let id = String::from_utf8(data[*offset..*offset + id_len].to_vec())?;
        *offset += id_len;
        let mut embedding = Vec::with_capacity(EMBEDDING_DIM);
        for _ in 0..EMBEDDING_DIM {
            let val = f32::from_le_bytes(data[*offset..*offset + 4].try_into()?);
            embedding.push(val);
            *offset += 4;
        }
        map.insert(id, embedding);
    }
    Ok(())
}

/// Cosine similarity between two L2-normalized vectors (= dot product).
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> String {
        let dir = std::env::temp_dir();
        dir.join(format!("photosearch_idx_{}_{}", name, std::process::id()))
            .to_string_lossy()
            .to_string()
    }

    #[test]
    fn test_search() {
        let path = tmp("search");
        let _ = fs::remove_file(&path);
        let index = VectorIndex::new(&path).unwrap();

        let mut emb1 = vec![0.0f32; EMBEDDING_DIM];
        emb1[0] = 1.0;
        let mut emb2 = vec![0.0f32; EMBEDDING_DIM];
        emb2[1] = 1.0;
        let mut query = vec![0.0f32; EMBEDDING_DIM];
        query[0] = 0.9;
        query[1] = 0.1;
        let norm: f32 = query.iter().map(|x| x * x).sum::<f32>().sqrt();
        for v in &mut query {
            *v /= norm;
        }

        index.add("photo1", &emb1).unwrap();
        index.add("photo2", &emb2).unwrap();

        let results = index.search(&query, 2).unwrap();
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].0, "photo1");
        assert!(results[0].1 > results[1].1);
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn test_save_load_v2_with_captions() {
        let path = tmp("v2");
        let _ = fs::remove_file(&path);

        let index = VectorIndex::new(&path).unwrap();
        let mut img = vec![0.0f32; EMBEDDING_DIM];
        img[0] = 1.0;
        let mut cap = vec![0.0f32; EMBEDDING_DIM];
        cap[1] = 1.0;
        index.add("photo1", &img).unwrap();
        index.add_caption("photo1", &cap).unwrap();

        let index2 = VectorIndex::new(&path).unwrap();
        assert_eq!(index2.len(), 1);
        assert_eq!(index2.caption_len(), 1);
        let recalled = index2.get_caption("photo1").unwrap();
        assert!((recalled[1] - 1.0).abs() < 1e-6);

        let _ = fs::remove_file(&path);
    }

    /// Hand-craft a v1 file (no magic, raw image-embedding map) and confirm
    /// the v2 loader reads it and yields zero captions (ready for backfill).
    #[test]
    fn test_load_v1_legacy() {
        let path = tmp("v1_legacy");
        let _ = fs::remove_file(&path);

        let mut data = Vec::new();
        let count: u32 = 1;
        data.extend_from_slice(&count.to_le_bytes());
        let id = "legacy_photo";
        data.extend_from_slice(&(id.len() as u32).to_le_bytes());
        data.extend_from_slice(id.as_bytes());
        let mut emb = vec![0.0f32; EMBEDDING_DIM];
        emb[0] = 1.0;
        for v in &emb {
            data.extend_from_slice(&v.to_le_bytes());
        }
        fs::write(&path, data).unwrap();

        let index = VectorIndex::new(&path).unwrap();
        assert_eq!(index.len(), 1);
        assert_eq!(index.caption_len(), 0);
        assert!(!index.has_caption("legacy_photo"));

        // Adding a caption should upgrade the file to v2.
        let mut cap = vec![0.0f32; EMBEDDING_DIM];
        cap[2] = 1.0;
        index.add_caption("legacy_photo", &cap).unwrap();

        let index2 = VectorIndex::new(&path).unwrap();
        assert_eq!(index2.len(), 1);
        assert_eq!(index2.caption_len(), 1);

        let _ = fs::remove_file(&path);
    }
}
