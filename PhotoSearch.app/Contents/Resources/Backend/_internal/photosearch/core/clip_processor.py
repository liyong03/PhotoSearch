"""CLIP model processor for generating image and text embeddings."""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor as HFCLIPProcessor

from photosearch.utils.image import load_image

logger = logging.getLogger(__name__)


class CLIPProcessor:
    """CLIP model wrapper for generating image and text embeddings."""

    def __init__(
        self,
        model_name: str = "openai/clip-vit-base-patch32",
        device: Optional[str] = None,
        local_files_only: bool = False,
    ):
        """Initialize CLIP processor.

        Args:
            model_name: HuggingFace model name for CLIP.
            device: Device to run model on ("cpu", "cuda", "mps").
                   If None, automatically selects best available device.
            local_files_only: If True, only use cached models (no network).
        """
        self.model_name = model_name
        self.device = self._select_device(device)

        logger.info(f"Loading CLIP model: {model_name}")
        logger.info(f"Using device: {self.device}")

        self.model = CLIPModel.from_pretrained(model_name, local_files_only=local_files_only)
        self.processor = HFCLIPProcessor.from_pretrained(model_name, local_files_only=local_files_only)

        # Move model to device
        self.model = self.model.to(self.device)
        self.model.eval()

        # Get embedding dimension
        self.embedding_dim = self.model.config.projection_dim

        logger.info(f"CLIP model loaded. Embedding dimension: {self.embedding_dim}")

    def _select_device(self, device: Optional[str]) -> str:
        """Select the best available device.

        Args:
            device: Requested device or None for auto-selection.

        Returns:
            Device string ("cpu", "cuda", or "mps").
        """
        if device is not None:
            return device

        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"

    def get_image_embedding(self, image: Image.Image) -> np.ndarray:
        """Generate embedding for a single image.

        Args:
            image: PIL Image to encode.

        Returns:
            Normalized embedding as numpy array of shape (embedding_dim,).
        """
        # Ensure RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Process image
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Generate embedding using vision model + projection
        with torch.no_grad():
            vision_outputs = self.model.vision_model(**inputs)
            image_embeds = self.model.visual_projection(vision_outputs.pooler_output)

        # Normalize and convert to numpy
        embedding = image_embeds.cpu().numpy()[0]
        embedding = embedding / np.linalg.norm(embedding)

        return embedding

    def get_image_embedding_from_path(self, image_path: Path | str) -> Optional[np.ndarray]:
        """Generate embedding for an image file.

        Args:
            image_path: Path to the image file.

        Returns:
            Normalized embedding, or None if image cannot be loaded.
        """
        try:
            image = load_image(image_path)
            if image is None:
                return None
            return self.get_image_embedding(image)
        except Exception as e:
            logger.warning(f"Failed to process image {image_path}: {e}")
            return None

    def get_text_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Text to encode.

        Returns:
            Normalized embedding as numpy array of shape (embedding_dim,).
        """
        # Process text
        inputs = self.processor(text=[text], return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Generate embedding using text model + projection
        with torch.no_grad():
            text_outputs = self.model.text_model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs.get("attention_mask"),
            )
            text_embeds = self.model.text_projection(text_outputs.pooler_output)

        # Normalize and convert to numpy
        embedding = text_embeds.cpu().numpy()[0]
        embedding = embedding / np.linalg.norm(embedding)

        return embedding

    def get_image_embeddings_batch(
        self,
        images: list[Image.Image],
        batch_size: int = 8,
    ) -> np.ndarray:
        """Generate embeddings for multiple images.

        Args:
            images: List of PIL Images to encode.
            batch_size: Number of images to process at once.

        Returns:
            Normalized embeddings as numpy array of shape (n_images, embedding_dim).
        """
        all_embeddings = []

        # Ensure all images are RGB
        images = [img.convert("RGB") if img.mode != "RGB" else img for img in images]

        # Process in batches
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]

            inputs = self.processor(images=batch, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                vision_outputs = self.model.vision_model(**inputs)
                image_embeds = self.model.visual_projection(vision_outputs.pooler_output)

            embeddings = image_embeds.cpu().numpy()
            all_embeddings.append(embeddings)

        # Concatenate all batches
        all_embeddings = np.vstack(all_embeddings)

        # Normalize
        norms = np.linalg.norm(all_embeddings, axis=1, keepdims=True)
        all_embeddings = all_embeddings / norms

        return all_embeddings

    def get_text_embeddings_batch(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for multiple text queries.

        Args:
            texts: List of text strings to encode.

        Returns:
            Normalized embeddings as numpy array of shape (n_texts, embedding_dim).
        """
        inputs = self.processor(text=texts, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            text_outputs = self.model.text_model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs.get("attention_mask"),
            )
            text_embeds = self.model.text_projection(text_outputs.pooler_output)

        embeddings = text_embeds.cpu().numpy()

        # Normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms

        return embeddings

    @staticmethod
    def cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding (normalized).
            embedding2: Second embedding (normalized).

        Returns:
            Cosine similarity score between -1 and 1.
        """
        return float(np.dot(embedding1, embedding2))

    @staticmethod
    def batch_cosine_similarity(
        query_embedding: np.ndarray,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        """Compute cosine similarity between query and multiple embeddings.

        Args:
            query_embedding: Query embedding of shape (embedding_dim,).
            embeddings: Matrix of embeddings of shape (n, embedding_dim).

        Returns:
            Similarity scores of shape (n,).
        """
        return np.dot(embeddings, query_embedding)
