"""Tests for embedding generation."""

import numpy as np
import pytest

from gladys_memory.embeddings import EmbeddingGenerator


class TestEmbeddingGenerator:
    """Tests for EmbeddingGenerator."""

    def test_generate_returns_correct_shape(self):
        """Embedding should be 384 dimensions."""
        gen = EmbeddingGenerator()
        embedding = gen.generate("Hello world")
        assert embedding.shape == (384,)
        assert embedding.dtype == np.float32

    def test_generate_batch_returns_correct_shape(self):
        """Batch embeddings should have correct shape."""
        gen = EmbeddingGenerator()
        texts = ["Hello", "World", "Test"]
        embeddings = gen.generate_batch(texts)
        assert embeddings.shape == (3, 384)
        assert embeddings.dtype == np.float32

    def test_similar_texts_have_high_similarity(self):
        """Similar texts should have high cosine similarity."""
        gen = EmbeddingGenerator()
        e1 = gen.generate("The cat sat on the mat")
        e2 = gen.generate("A cat was sitting on a mat")
        similarity = gen.cosine_similarity(e1, e2)
        assert similarity > 0.8

    def test_different_texts_have_lower_similarity(self):
        """Unrelated texts should have lower similarity."""
        gen = EmbeddingGenerator()
        e1 = gen.generate("The cat sat on the mat")
        e2 = gen.generate("Quantum physics explains subatomic particles")
        similarity = gen.cosine_similarity(e1, e2)
        assert similarity < 0.5

    def test_cosine_similarity_identical_vectors(self):
        """Identical vectors should have similarity of 1.0."""
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert abs(EmbeddingGenerator.cosine_similarity(a, b) - 1.0) < 0.0001

    def test_cosine_similarity_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity of 0.0."""
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        assert abs(EmbeddingGenerator.cosine_similarity(a, b)) < 0.0001
