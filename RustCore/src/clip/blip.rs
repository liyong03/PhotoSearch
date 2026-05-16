use anyhow::{Context, Result};
use candle::{DType, Device, IndexOp, Module, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::blip;
use tokenizers::Tokenizer;

use crate::services::image_loader;

const SEP_TOKEN_ID: u32 = 102;
const START_TOKEN_ID: u32 = 30522;
const MAX_CAPTION_LENGTH: usize = 100;

pub struct BlipEngine {
    model: blip::BlipForConditionalGeneration,
    tokenizer: Tokenizer,
    device: Device,
    image_size: usize,
}

impl BlipEngine {
    /// Create a new BLIP captioning engine, downloading model weights if needed.
    pub fn new(model_cache: &str, device: &Device) -> Result<Self> {
        std::fs::create_dir_all(model_cache)?;

        let api = hf_hub::api::sync::Api::new()?;
        let repo = api.repo(hf_hub::Repo::model(
            "Salesforce/blip-image-captioning-large".to_string(),
        ));

        let model_file = repo
            .get("model.safetensors")
            .context("Failed to download BLIP model weights")?;
        let tokenizer_file = repo
            .get("tokenizer.json")
            .context("Failed to download BLIP tokenizer")?;

        let config = blip::Config::image_captioning_large();
        let image_size = config.vision_config.image_size;

        let vb = unsafe {
            VarBuilder::from_mmaped_safetensors(&[model_file], DType::F32, device)?
        };

        let model = blip::BlipForConditionalGeneration::new(&config, vb)?;
        let tokenizer = Tokenizer::from_file(&tokenizer_file)
            .map_err(|e| anyhow::anyhow!("Failed to load BLIP tokenizer: {}", e))?;

        log::info!(
            "BLIP model loaded successfully (image_size={})",
            image_size
        );

        Ok(Self {
            model,
            tokenizer,
            device: device.clone(),
            image_size,
        })
    }

    /// Generate a caption for an image file.
    pub fn generate_caption(&mut self, path: &str) -> Result<String> {
        let image_tensor = self.load_image(path)?.unsqueeze(0)?;

        // Reset KV cache from any previous caption generation
        self.model.reset_kv_cache();

        // Vision encoding
        let image_embeddings = self.model.vision_model().forward(&image_tensor)?;

        // Greedy text generation with KV cache:
        // First pass: feed the start token to prime the cache.
        // Subsequent passes: feed only the last generated token.
        let mut token_ids: Vec<u32> = vec![START_TOKEN_ID];

        for i in 0..MAX_CAPTION_LENGTH {
            let input_tokens = if i == 0 {
                // First iteration: feed the full sequence (just the start token)
                &token_ids[..]
            } else {
                // Subsequent iterations: feed only the newly generated token
                &token_ids[token_ids.len() - 1..]
            };

            let input = Tensor::new(input_tokens, &self.device)?.unsqueeze(0)?;
            let logits = self
                .model
                .text_decoder()
                .forward(&input, &image_embeddings)?;

            // Get logits for the last position in the output
            let last_pos = input_tokens.len() - 1;
            let last_logits = logits.i((0, last_pos))?;

            // Greedy: pick token with highest logit
            let next_token = last_logits
                .argmax(0)?
                .to_scalar::<u32>()?;

            if next_token == SEP_TOKEN_ID {
                break;
            }

            token_ids.push(next_token);
        }

        // Decode tokens (skip start token)
        let caption = self
            .tokenizer
            .decode(&token_ids[1..], true)
            .map_err(|e| anyhow::anyhow!("Failed to decode caption: {}", e))?;

        Ok(caption.trim().to_string())
    }

    /// Extract tags from a generated caption.
    pub fn extract_tags(caption: &str) -> Vec<String> {
        let stop_words: &[&str] = &[
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "shall", "can", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "into", "through", "during",
            "before", "after", "above", "below", "between", "and", "but", "or",
            "not", "no", "it", "its", "this", "that", "these", "those", "there",
            "their", "they", "he", "she", "his", "her", "him", "we", "our", "you",
            "your", "my", "i", "me", "some", "any", "very", "so", "too", "also",
        ];

        caption
            .to_lowercase()
            .split_whitespace()
            .filter(|w| {
                let word = w.trim_matches(|c: char| !c.is_alphanumeric());
                !word.is_empty() && word.len() > 1 && !stop_words.contains(&word)
            })
            .map(|w| w.trim_matches(|c: char| !c.is_alphanumeric()).to_string())
            .collect::<Vec<_>>()
            .into_iter()
            .collect::<std::collections::HashSet<_>>()
            .into_iter()
            .collect()
    }

    /// Load and preprocess an image for BLIP.
    /// Resizes, converts to RGB, normalizes with ImageNet mean/std.
    fn load_image(&self, path: &str) -> Result<Tensor> {
        let img = image_loader::load_image(path)?;

        let img = img.resize_to_fill(
            self.image_size as u32,
            self.image_size as u32,
            image::imageops::FilterType::Triangle,
        );

        let img = img.to_rgb8();
        let raw = img.into_raw();

        // Normalize: (pixel / 255.0 - mean) / std
        let mean = [0.48145466f32, 0.4578275, 0.40821073];
        let std = [0.26862954f32, 0.26130258, 0.27577711];

        let mut normalized = vec![0.0f32; 3 * self.image_size * self.image_size];
        for y in 0..self.image_size {
            for x in 0..self.image_size {
                let idx = (y * self.image_size + x) * 3;
                for c in 0..3 {
                    let pixel = raw[idx + c] as f32 / 255.0;
                    let out_idx = c * self.image_size * self.image_size + y * self.image_size + x;
                    normalized[out_idx] = (pixel - mean[c]) / std[c];
                }
            }
        }

        let tensor =
            Tensor::from_vec(normalized, (3, self.image_size, self.image_size), &self.device)?;

        Ok(tensor)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_tags() {
        let caption = "a woman standing in front of a large painting";
        let tags = BlipEngine::extract_tags(caption);
        assert!(tags.contains(&"woman".to_string()));
        assert!(tags.contains(&"standing".to_string()));
        assert!(tags.contains(&"painting".to_string()));
        assert!(!tags.contains(&"a".to_string()));
        assert!(!tags.contains(&"in".to_string()));
    }

    #[test]
    fn test_extract_tags_empty() {
        let tags = BlipEngine::extract_tags("");
        assert!(tags.is_empty());
    }

    #[test]
    #[ignore] // Requires model download
    fn test_caption_generation() {
        // Create a simple test image programmatically
        let img = image::RgbImage::from_fn(256, 256, |x, y| {
            image::Rgb([(x % 256) as u8, (y % 256) as u8, 128])
        });
        let test_path = "/tmp/photosearch_test_caption.jpg";
        img.save(test_path).unwrap();

        let mut engine = BlipEngine::new("/tmp/photosearch_test_models", &Device::Cpu).unwrap();
        let caption = engine.generate_caption(test_path).unwrap();
        assert!(!caption.is_empty());

        std::fs::remove_file(test_path).ok();
    }
}
