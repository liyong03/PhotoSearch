"""Configuration management for PhotoSearch backend."""

from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = ConfigDict(
        env_prefix="PHOTOSEARCH_",
        env_file=".env",
    )

    # API Settings
    api_version: str = "v1"
    api_prefix: str = "/api/v1"
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False

    # Data Paths
    data_dir: Path = Path.home() / "Library" / "Application Support" / "PhotoSearch"
    db_path: Path | None = None  # Set in model_post_init
    faiss_index_path: Path | None = None  # Set in model_post_init

    # ML Model Settings
    clip_model_name: str = "openai/clip-vit-base-patch32"
    blip_model_name: str = "Salesforce/blip-image-captioning-base"
    device: str = "cpu"  # "cpu", "cuda", or "mps"

    # Search Settings
    default_top_k: int = 20
    max_top_k: int = 100

    # Indexing Settings
    batch_size: int = 10
    supported_extensions: list[str] = [".jpg", ".jpeg", ".png", ".heic", ".heif"]

    # Geocoding Settings
    geocoding_cache_size: int = 1000
    geocoding_user_agent: str = "PhotoSearch/0.1.0"

    def model_post_init(self, __context) -> None:
        """Initialize derived paths after model creation."""
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Set default paths if not provided
        if self.db_path is None:
            self.db_path = self.data_dir / "photos.db"
        if self.faiss_index_path is None:
            self.faiss_index_path = self.data_dir / "faiss.index"


# Global settings instance
settings = Settings()
