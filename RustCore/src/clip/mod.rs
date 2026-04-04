pub mod blip;

use anyhow::{Context, Result};
use candle::{DType, Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::clip;
use std::path::Path;
use tokenizers::Tokenizer;

pub struct ClipEngine {
    model: clip::ClipModel,
    tokenizer: Tokenizer,
    device: Device,
    image_size: usize,
}

impl ClipEngine {
    /// Create a new CLIP engine, downloading model weights if needed.
    /// model_cache: directory to cache downloaded model files.
    pub fn new(model_cache: &str) -> Result<Self> {
        std::fs::create_dir_all(model_cache)?;

        let device = Self::select_device();
        log::info!("CLIP using device: {:?}", device);

        // Download or load model from HuggingFace Hub
        let api = hf_hub::api::sync::Api::new()?;
        let repo = api.repo(hf_hub::Repo::with_revision(
            "openai/clip-vit-base-patch32".to_string(),
            hf_hub::RepoType::Model,
            "refs/pr/15".to_string(),
        ));

        let model_file = repo.get("model.safetensors")
            .context("Failed to download CLIP model weights")?;
        let tokenizer_file = repo.get("tokenizer.json")
            .context("Failed to download CLIP tokenizer")?;

        let config = clip::ClipConfig::vit_base_patch32();
        let image_size = config.vision_config.image_size;

        let vb = unsafe {
            VarBuilder::from_mmaped_safetensors(
                &[model_file],
                DType::F32,
                &device,
            )?
        };

        let model = clip::ClipModel::new(vb, &config)?;
        let tokenizer = Tokenizer::from_file(&tokenizer_file)
            .map_err(|e| anyhow::anyhow!("Failed to load tokenizer: {}", e))?;

        log::info!("CLIP model loaded successfully (image_size={})", image_size);

        Ok(Self {
            model,
            tokenizer,
            device,
            image_size,
        })
    }

    /// Encode a text string into a normalized 512-dim embedding.
    pub fn encode_text(&self, text: &str) -> Result<Vec<f32>> {
        let encoding = self.tokenizer.encode(text, true)
            .map_err(|e| anyhow::anyhow!("Tokenization failed: {}", e))?;

        let ids = encoding.get_ids().to_vec();
        let input_ids = Tensor::new(vec![ids], &self.device)?;

        let features = self.model.get_text_features(&input_ids)?;
        let features = clip::div_l2_norm(&features)?;
        let embedding = features.squeeze(0)?.to_vec1::<f32>()?;

        Ok(embedding)
    }

    /// Encode an image file into a normalized 512-dim embedding.
    pub fn encode_image(&self, path: &str) -> Result<Vec<f32>> {
        let tensor = self.load_image(path)?;
        let tensor = tensor.unsqueeze(0)?; // Add batch dimension

        let features = self.model.get_image_features(&tensor)?;
        let features = clip::div_l2_norm(&features)?;
        let embedding = features.squeeze(0)?.to_vec1::<f32>()?;

        Ok(embedding)
    }

    /// Load and preprocess an image for CLIP.
    /// Resizes to image_size x image_size, converts to RGB, normalizes to [-1, 1].
    fn load_image(&self, path: &str) -> Result<Tensor> {
        let img = image::ImageReader::open(Path::new(path))
            .context("Failed to open image")?
            .decode()
            .context("Failed to decode image")?;

        let img = img.resize_to_fill(
            self.image_size as u32,
            self.image_size as u32,
            image::imageops::FilterType::Triangle,
        );

        let img = img.to_rgb8();
        let raw = img.into_raw();

        let tensor = Tensor::from_vec(raw, (self.image_size, self.image_size, 3), &Device::Cpu)?
            .permute((2, 0, 1))?
            .to_dtype(DType::F32)?
            .affine(2.0 / 255.0, -1.0)?
            .to_device(&self.device)?;

        Ok(tensor)
    }

    /// Get a reference to the device used by this engine.
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
        assert_eq!(embedding.len(), 512);

        // Check normalization (L2 norm should be ~1.0)
        let norm: f32 = embedding.iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 0.01);
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

        // Similar texts should have higher cosine similarity
        assert!(sim_similar > sim_different);
    }
}
