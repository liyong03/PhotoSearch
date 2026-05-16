use anyhow::{Context, Result};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

use crate::clip::{EMBEDDING_DIM, MODEL_TAG};

/// On-disk format magic + version.
/// v1: raw `[count][entries]` of image embeddings (legacy CLIP, no header).
/// v2/v3: header + image map + caption map (hybrid scoring, since removed).
/// v4: header + image map only. The caption map is gone — pure image scoring.
const MAGIC: &[u8; 4] = b"PSVI";
const FORMAT_VERSION: u32 = 4;

/// In-memory vector index with brute-force cosine similarity search.
pub struct VectorIndex {
    inner: Mutex<VectorIndexInner>,
}

struct VectorIndexInner {
    /// Map from photo_id to image embedding vector.
    embeddings: HashMap<String, Vec<f32>>,
    /// Path to persist the index on disk.
    index_path: PathBuf,
}

impl VectorIndex {
    /// Create or load a vector index.
    ///
    /// If the on-disk index was written by a different model (different tag or
    /// embedding dimension) or an older format, it is silently discarded — the
    /// engine is expected to re-index from the database afterwards.
    pub fn new(index_path: &str) -> Result<Self> {
        let path = PathBuf::from(index_path);
        let mut inner = VectorIndexInner {
            embeddings: HashMap::new(),
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

    /// Remove an embedding.
    pub fn remove(&self, photo_id: &str) -> Result<()> {
        let mut inner = self.inner.lock().unwrap();
        inner.embeddings.remove(photo_id);
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
}

impl VectorIndexInner {
    /// Save the index in v4 format:
    /// [magic 4][version u32][tag_len u32][tag bytes][embedding_dim u32][image_map]
    /// Map: [count u32] then per entry [id_len u32][id][dim × f32 LE].
    fn save(&self) -> Result<()> {
        if let Some(parent) = self.index_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let mut data = Vec::new();
        data.extend_from_slice(MAGIC);
        data.extend_from_slice(&FORMAT_VERSION.to_le_bytes());

        let tag = MODEL_TAG.as_bytes();
        data.extend_from_slice(&(tag.len() as u32).to_le_bytes());
        data.extend_from_slice(tag);
        data.extend_from_slice(&(EMBEDDING_DIM as u32).to_le_bytes());

        write_map(&mut data, &self.embeddings);

        // Atomic write: tmp + rename, so a crash mid-save can't corrupt the index.
        let tmp = self.index_path.with_extension("tmp");
        fs::write(&tmp, data)?;
        fs::rename(&tmp, &self.index_path)?;
        Ok(())
    }

    fn load(&mut self) -> Result<()> {
        let data = fs::read(&self.index_path)?;
        if data.len() >= 4 && &data[0..4] == MAGIC {
            self.load_versioned(&data)
        } else {
            log::warn!("Vector index is legacy format — discarding; re-index required");
            Ok(())
        }
    }

    fn load_versioned(&mut self, data: &[u8]) -> Result<()> {
        let mut offset = 4; // skip magic
        let version = u32::from_le_bytes(data[offset..offset + 4].try_into()?);
        offset += 4;

        if version != FORMAT_VERSION {
            log::warn!(
                "Vector index format v{version} != current v{FORMAT_VERSION} — \
                 discarding; re-index required"
            );
            return Ok(());
        }

        let tag_len = u32::from_le_bytes(data[offset..offset + 4].try_into()?) as usize;
        offset += 4;
        let tag = String::from_utf8(data[offset..offset + tag_len].to_vec())?;
        offset += tag_len;
        let dim = u32::from_le_bytes(data[offset..offset + 4].try_into()?) as usize;
        offset += 4;

        if tag != MODEL_TAG || dim != EMBEDDING_DIM {
            log::warn!(
                "Vector index was built with model '{tag}' (dim {dim}), current is \
                 '{MODEL_TAG}' (dim {EMBEDDING_DIM}) — discarding; re-index required"
            );
            return Ok(());
        }

        read_map(data, &mut offset, &mut self.embeddings)?;

        log::info!(
            "Loaded {} image embeddings (v4, {MODEL_TAG})",
            self.embeddings.len()
        );
        Ok(())
    }
}

fn write_map(out: &mut Vec<u8>, map: &HashMap<String, Vec<f32>>) {
    out.extend_from_slice(&(map.len() as u32).to_le_bytes());
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
        std::env::temp_dir()
            .join(format!("photosearch_idx_{}_{}", name, std::process::id()))
            .to_string_lossy()
            .to_string()
    }

    fn unit_vec(i: usize) -> Vec<f32> {
        let mut v = vec![0.0f32; EMBEDDING_DIM];
        v[i % EMBEDDING_DIM] = 1.0;
        v
    }

    #[test]
    fn test_search() {
        let path = tmp("search");
        let _ = fs::remove_file(&path);
        let index = VectorIndex::new(&path).unwrap();

        let emb1 = unit_vec(0);
        let emb2 = unit_vec(1);
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
    fn test_save_load_v4() {
        let path = tmp("v4");
        let _ = fs::remove_file(&path);

        let index = VectorIndex::new(&path).unwrap();
        index.add("photo1", &unit_vec(0)).unwrap();
        index.add("photo2", &unit_vec(1)).unwrap();

        let index2 = VectorIndex::new(&path).unwrap();
        assert_eq!(index2.len(), 2);

        let _ = fs::remove_file(&path);
    }

    /// A legacy v1 file (no magic header) must be discarded, not misread.
    #[test]
    fn test_legacy_v1_discarded() {
        let path = tmp("v1_legacy");
        let _ = fs::remove_file(&path);

        let mut data = Vec::new();
        data.extend_from_slice(&1u32.to_le_bytes());
        let id = "legacy_photo";
        data.extend_from_slice(&(id.len() as u32).to_le_bytes());
        data.extend_from_slice(id.as_bytes());
        for _ in 0..512 {
            data.extend_from_slice(&0.0f32.to_le_bytes());
        }
        fs::write(&path, data).unwrap();

        let index = VectorIndex::new(&path).unwrap();
        assert_eq!(index.len(), 0, "legacy index must be discarded");

        let _ = fs::remove_file(&path);
    }

    /// An older v3 (caption-map) file must be discarded on version mismatch.
    #[test]
    fn test_old_v3_discarded() {
        let path = tmp("v3_old");
        let _ = fs::remove_file(&path);

        let mut data = Vec::new();
        data.extend_from_slice(MAGIC);
        data.extend_from_slice(&3u32.to_le_bytes()); // old version
        let tag = MODEL_TAG.as_bytes();
        data.extend_from_slice(&(tag.len() as u32).to_le_bytes());
        data.extend_from_slice(tag);
        data.extend_from_slice(&(EMBEDDING_DIM as u32).to_le_bytes());
        data.extend_from_slice(&0u32.to_le_bytes());
        fs::write(&path, data).unwrap();

        let index = VectorIndex::new(&path).unwrap();
        assert_eq!(index.len(), 0, "old-format index must be discarded");

        let _ = fs::remove_file(&path);
    }

    /// A v4 file written with a different model tag must be discarded.
    #[test]
    fn test_foreign_model_tag_discarded() {
        let path = tmp("foreign_tag");
        let _ = fs::remove_file(&path);

        let mut data = Vec::new();
        data.extend_from_slice(MAGIC);
        data.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
        let tag = b"some-other-model";
        data.extend_from_slice(&(tag.len() as u32).to_le_bytes());
        data.extend_from_slice(tag);
        data.extend_from_slice(&(EMBEDDING_DIM as u32).to_le_bytes());
        data.extend_from_slice(&0u32.to_le_bytes());
        fs::write(&path, data).unwrap();

        let index = VectorIndex::new(&path).unwrap();
        assert_eq!(index.len(), 0, "foreign-model index must be discarded");

        let _ = fs::remove_file(&path);
    }
}
