"""Embedding generation for GLADyS Memory."""

from typing import Optional

import numpy as np


class EmbeddingGenerator:
    """Generate embeddings using sentence-transformers.

    Uses all-MiniLM-L6-v2 by default (384 dimensions).
    """

    # Default model as specified in ADR-0004
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None

    def _load_model(self):
        """Lazy-load the embedding model."""
        if self._model is None:
            # Import here to avoid slow startup
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)

    def generate(self, text: str) -> np.ndarray:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            384-dimensional numpy array
        """
        self._load_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def generate_batch(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            Array of shape (len(texts), 384)
        """
        self._load_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.astype(np.float32)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))
