"""GLADyS Memory Subsystem - Storage Path

This package implements the Python storage path for the Memory subsystem.
It handles:
- PostgreSQL + pgvector persistent storage
- Embedding generation (sentence-transformers)
- gRPC server for Rust fast path to call
"""

__version__ = "0.1.0"

from .storage import MemoryStorage
from .embeddings import EmbeddingGenerator

__all__ = ["MemoryStorage", "EmbeddingGenerator"]
