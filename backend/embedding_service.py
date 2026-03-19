"""
Embedding Service using Doubao (ByteDance) API.

This module provides text embedding functionality using the Doubao embedding API,
replacing the local sentence-transformers model for better performance and
reduced resource usage.
"""

import os
import time
from typing import List, Optional
from dataclasses import dataclass
import numpy as np
import httpx
from openai import OpenAI


@dataclass
class EmbeddingConfig:
    """Configuration for embedding service."""
    api_key: str = ""
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    model: str = "doubao-embedding"
    embedding_dim: int = 1024  # Doubao embedding dimension
    max_batch_size: int = 10  # API batch limit
    retry_count: int = 3
    retry_delay: float = 1.0


class EmbeddingService:
    """
    Embedding service using Doubao API.

    This service provides text embedding functionality through the Doubao API,
    which can replace local sentence-transformers models.
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        """Initialize the embedding service."""
        if config is None:
            config = self._load_config_from_env()

        self.config = config
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
        self.is_available = self._check_api_key()

    def _load_config_from_env(self) -> EmbeddingConfig:
        """Load configuration from environment variables."""
        return EmbeddingConfig(
            api_key=os.getenv("ARK_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            model=os.getenv("ARK_EMBEDDING_MODEL", "doubao-embedding"),
            embedding_dim=int(os.getenv("EMBEDDING_DIM", "1024")),
            max_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "10"))
        )

    def _check_api_key(self) -> bool:
        """Check if API key is configured."""
        return bool(self.config.api_key)

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Retry API calls with exponential backoff."""
        for attempt in range(self.config.retry_count):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.config.retry_count - 1:
                    raise e
                wait_time = self.config.retry_delay * (2 ** attempt)
                print(f"[Embedding] API call failed, retrying in {wait_time}s...")
                time.sleep(wait_time)

    def embed_single(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            numpy array of embedding vector
        """
        if not self.is_available:
            raise RuntimeError("Embedding service not available. Check API key.")

        def _call_api():
            response = self.client.embeddings.create(
                model=self.config.model,
                input=[text]
            )
            return response

        response = self._retry_with_backoff(_call_api)
        embedding = response.data[0].embedding
        return np.array(embedding, dtype=np.float32)

    def embed_batch(self, texts: List[str], show_progress: bool = True) -> np.ndarray:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of input texts to embed
            show_progress: Whether to show progress bar

        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        if not self.is_available:
            raise RuntimeError("Embedding service not available. Check API key.")

        if not texts:
            return np.array([], dtype=np.float32)

        embeddings = []
        total = len(texts)
        batch_size = self.config.max_batch_size

        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]

            def _call_api():
                response = self.client.embeddings.create(
                    model=self.config.model,
                    input=batch
                )
                return response

            response = self._retry_with_backoff(_call_api)

            # Extract embeddings in order
            batch_embeddings = [
                item.embedding for item in sorted(response.data, key=lambda x: x.index)
            ]
            embeddings.extend(batch_embeddings)

            if show_progress:
                progress = min(100, (i + len(batch)) * 100 // total)
                print(f"[Embedding] Progress: {progress}%")

        return np.array(embeddings, dtype=np.float32)

    def normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Normalize embeddings to unit vectors for cosine similarity."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        return embeddings / norms

    def get_stats(self) -> dict:
        """Get service statistics."""
        return {
            "available": self.is_available,
            "model": self.config.model,
            "embedding_dim": self.config.embedding_dim,
            "base_url": self.config.base_url
        }
