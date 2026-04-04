use anyhow::{Context, Result};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

const EMBEDDING_DIM: usize = 512;

/// In-memory vector index with brute-force cosine similarity search.
/// Uses interior mutability (Mutex) so it can be used behind Arc.
pub struct VectorIndex {
    inner: Mutex<VectorIndexInner>,
}

struct VectorIndexInner {
    /// Map from photo_id to embedding vector.
    embeddings: HashMap<String, Vec<f32>>,
    /// Path to persist the index on disk.
    index_path: PathBuf,
}

impl VectorIndex {
    /// Create or load a vector index.
    pub fn new(index_path: &str) -> Result<Self> {
        let path = PathBuf::from(index_path);
        let mut inner = VectorIndexInner {
            embeddings: HashMap::new(),
            index_path: path.clone(),
        };

        // Load from disk if exists
        if path.exists() {
            inner.load().context("Failed to load vector index")?;
        }

        Ok(Self {
            inner: Mutex::new(inner),
        })
    }

    /// Add an embedding for a photo.
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

    /// Search for the top_k most similar embeddings to the query.
    /// Returns (photo_id, score) pairs sorted by descending score.
    pub fn search(&self, query: &[f32], top_k: usize) -> Result<Vec<(String, f32)>> {
        let inner = self.inner.lock().unwrap();
        assert_eq!(query.len(), EMBEDDING_DIM, "Query must be {EMBEDDING_DIM}-dim");

        let mut scores: Vec<(String, f32)> = inner
            .embeddings
            .iter()
            .map(|(id, emb)| {
                let score = cosine_similarity(query, emb);
                (id.clone(), score)
            })
            .collect();

        // Sort by score descending
        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scores.truncate(top_k);

        Ok(scores)
    }

    /// Number of embeddings in the index.
    pub fn len(&self) -> usize {
        self.inner.lock().unwrap().embeddings.len()
    }
}

impl VectorIndexInner {
    /// Save the index to disk as a simple binary format.
    /// Format: [count: u32] [for each: id_len: u32, id_bytes, embedding: [f32; 512]]
    fn save(&self) -> Result<()> {
        if let Some(parent) = self.index_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let mut data = Vec::new();
        let count = self.embeddings.len() as u32;
        data.extend_from_slice(&count.to_le_bytes());

        for (id, emb) in &self.embeddings {
            let id_bytes = id.as_bytes();
            let id_len = id_bytes.len() as u32;
            data.extend_from_slice(&id_len.to_le_bytes());
            data.extend_from_slice(id_bytes);
            for val in emb {
                data.extend_from_slice(&val.to_le_bytes());
            }
        }

        fs::write(&self.index_path, data)?;
        Ok(())
    }

    /// Load the index from disk.
    fn load(&mut self) -> Result<()> {
        let data = fs::read(&self.index_path)?;
        let mut offset = 0;

        if data.len() < 4 {
            return Ok(());
        }

        let count = u32::from_le_bytes(data[offset..offset + 4].try_into()?) as usize;
        offset += 4;

        for _ in 0..count {
            let id_len = u32::from_le_bytes(data[offset..offset + 4].try_into()?) as usize;
            offset += 4;

            let id = String::from_utf8(data[offset..offset + id_len].to_vec())?;
            offset += id_len;

            let mut embedding = Vec::with_capacity(EMBEDDING_DIM);
            for _ in 0..EMBEDDING_DIM {
                let val = f32::from_le_bytes(data[offset..offset + 4].try_into()?);
                embedding.push(val);
                offset += 4;
            }

            self.embeddings.insert(id, embedding);
        }

        log::info!("Loaded {} embeddings from index", count);
        Ok(())
    }
}

/// Cosine similarity between two normalized vectors (equivalent to dot product).
fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_search() {
        let index = VectorIndex::new("/tmp/test_index_search_unused").unwrap();

        // Create some fake normalized embeddings
        let mut emb1 = vec![0.0f32; EMBEDDING_DIM];
        emb1[0] = 1.0;
        let mut emb2 = vec![0.0f32; EMBEDDING_DIM];
        emb2[1] = 1.0;
        let mut query = vec![0.0f32; EMBEDDING_DIM];
        query[0] = 0.9;
        query[1] = 0.1;
        // Normalize query
        let norm: f32 = query.iter().map(|x| x * x).sum::<f32>().sqrt();
        for v in &mut query {
            *v /= norm;
        }

        index.add("photo1", &emb1).unwrap();
        index.add("photo2", &emb2).unwrap();

        let results = index.search(&query, 2).unwrap();
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].0, "photo1"); // More similar to query
        assert!(results[0].1 > results[1].1);
    }

    #[test]
    fn test_save_load() {
        let path = "/tmp/test_index_save_load";
        let _ = fs::remove_file(path);

        let index = VectorIndex::new(path).unwrap();

        let mut emb = vec![0.0f32; EMBEDDING_DIM];
        emb[0] = 1.0;
        index.add("test_photo", &emb).unwrap();

        // Load into new index
        let index2 = VectorIndex::new(path).unwrap();
        assert_eq!(index2.len(), 1);
        let results = index2.search(&emb, 1).unwrap();
        assert_eq!(results[0].0, "test_photo");
        assert!((results[0].1 - 1.0).abs() < 0.001);

        let _ = fs::remove_file(path);
    }
}
