pub mod blip;

use anyhow::{Context, Result};
use candle::{DType, Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::clip::div_l2_norm;
use candle_transformers::models::siglip;
use tokenizers::Tokenizer;

use crate::services::image_loader;

/// Embedding dimension produced by SigLIP base (text & image share this).
pub const EMBEDDING_DIM: usize = 768;

/// SigLIP text encoder uses the hidden state at the last token position with
/// bidirectional attention, so every input must be padded/truncated to a
/// fixed length (max_position_embeddings = 64).
const MAX_TOKENS: usize = 64;

/// SigLIP pads with token id 1 (its tokenizer sets pad = eos = `</s>`).
const PAD_ID: u32 = 1;

/// HuggingFace repo for the SigLIP weights + tokenizer.
const MODEL_REPO: &str = "google/siglip-base-patch16-224";

/// Identifier persisted alongside the vector index so a model change can be
/// detected and trigger a re-index. Bump this whenever the model changes.
pub const MODEL_TAG: &str = "siglip-base-patch16-224";

/// Image+text embedding engine.
///
/// Despite the `clip` module name (kept to minimise churn), this now wraps
/// Google's **SigLIP** base model — a strict upgrade over OpenAI CLIP
/// ViT-B/32 for abstract and natural-language queries.
pub struct ClipEngine {
    model: siglip::Model,
    tokenizer: Tokenizer,
    device: Device,
    image_size: usize,
}

impl ClipEngine {
    /// Create a new engine, downloading SigLIP weights if needed.
    pub fn new(model_cache: &str) -> Result<Self> {
        std::fs::create_dir_all(model_cache)?;

        let device = Self::select_device();
        log::info!("SigLIP using device: {:?}", device);

        let api = hf_hub::api::sync::Api::new()?;
        let repo = api.model(MODEL_REPO.to_string());

        let model_file = repo
            .get("model.safetensors")
            .context("Failed to download SigLIP model weights")?;
        let tokenizer_file = repo
            .get("tokenizer.json")
            .context("Failed to download SigLIP tokenizer")?;

        let config = siglip::Config::base_patch16_224();
        let image_size = config.vision_config.image_size;

        let vb = unsafe {
            VarBuilder::from_mmaped_safetensors(&[model_file], DType::F32, &device)?
        };
        let model = siglip::Model::new(&config, vb)?;

        let tokenizer = Tokenizer::from_file(&tokenizer_file)
            .map_err(|e| anyhow::anyhow!("Failed to load tokenizer: {}", e))?;

        log::info!("SigLIP model loaded (image_size={image_size}, dim={EMBEDDING_DIM})");

        Ok(Self {
            model,
            tokenizer,
            device,
            image_size,
        })
    }

    /// Encode a text string into a normalized `EMBEDDING_DIM` embedding.
    pub fn encode_text(&self, text: &str) -> Result<Vec<f32>> {
        let encoding = self
            .tokenizer
            .encode(text, true)
            .map_err(|e| anyhow::anyhow!("Tokenization failed: {}", e))?;

        // SigLIP requires a fixed-length input: truncate then right-pad to 64.
        let mut ids = encoding.get_ids().to_vec();
        ids.truncate(MAX_TOKENS);
        ids.resize(MAX_TOKENS, PAD_ID);

        let input_ids = Tensor::new(vec![ids], &self.device)?;
        let features = self.model.get_text_features(&input_ids)?;
        let features = div_l2_norm(&features)?;
        let embedding = features.squeeze(0)?.to_vec1::<f32>()?;

        Ok(embedding)
    }

    /// Encode an image file into a normalized `EMBEDDING_DIM` embedding.
    pub fn encode_image(&self, path: &str) -> Result<Vec<f32>> {
        let tensor = self.load_image(path)?.unsqueeze(0)?;
        let features = self.model.get_image_features(&tensor)?;
        let features = div_l2_norm(&features)?;
        let embedding = features.squeeze(0)?.to_vec1::<f32>()?;

        Ok(embedding)
    }

    /// Load and preprocess an image: resize to image_size², RGB, normalize to [-1, 1].
    fn load_image(&self, path: &str) -> Result<Tensor> {
        let img = image_loader::load_image(path)?;

        let img = img.resize_to_fill(
            self.image_size as u32,
            self.image_size as u32,
            image::imageops::FilterType::Triangle,
        );

        let raw = img.to_rgb8().into_raw();

        let tensor = Tensor::from_vec(raw, (self.image_size, self.image_size, 3), &Device::Cpu)?
            .permute((2, 0, 1))?
            .to_dtype(DType::F32)?
            .affine(2.0 / 255.0, -1.0)?
            .to_device(&self.device)?;

        Ok(tensor)
    }

    pub fn device(&self) -> &Device {
        &self.device
    }

    fn select_device() -> Device {
        #[cfg(feature = "metal")]
        {
            if let Ok(device) = Device::new_metal(0) {
                return device;
            }
        }
        Device::Cpu
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore] // Requires model download
    fn test_text_encoding() {
        let engine = ClipEngine::new("/tmp/photosearch_test_models").unwrap();
        let embedding = engine.encode_text("a photo of a cat").unwrap();
        assert_eq!(embedding.len(), EMBEDDING_DIM);

        let norm: f32 = embedding.iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 0.01, "embedding should be L2-normalized");
    }

    #[test]
    #[ignore] // Requires model download
    fn test_text_similarity() {
        let engine = ClipEngine::new("/tmp/photosearch_test_models").unwrap();
        let emb1 = engine.encode_text("a photo of a cat").unwrap();
        let emb2 = engine.encode_text("a picture of a kitten").unwrap();
        let emb3 = engine.encode_text("a red sports car").unwrap();

        let sim_similar: f32 = emb1.iter().zip(&emb2).map(|(a, b)| a * b).sum();
        let sim_different: f32 = emb1.iter().zip(&emb3).map(|(a, b)| a * b).sum();

        assert!(sim_similar > sim_different);
    }
}
