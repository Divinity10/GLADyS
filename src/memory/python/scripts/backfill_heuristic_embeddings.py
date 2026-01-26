#!/usr/bin/env python3
"""Backfill embeddings for existing heuristics.

This script generates embeddings for heuristics that don't have them yet.
Run this after applying migration 008_heuristic_embeddings.sql.

Usage:
    python backfill_heuristic_embeddings.py

Environment variables:
    POSTGRES_HOST: PostgreSQL host (default: localhost)
    POSTGRES_PORT: PostgreSQL port (default: 5432)
    POSTGRES_DB: Database name (default: gladys)
    POSTGRES_USER: Database user (default: gladys)
    POSTGRES_PASSWORD: Database password (default: gladys)
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from pgvector.asyncpg import register_vector

from gladys_memory.embeddings import EmbeddingGenerator


async def backfill_embeddings():
    """Generate embeddings for heuristics missing them."""
    # Database connection
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    database = os.environ.get("POSTGRES_DB", "gladys")
    user = os.environ.get("POSTGRES_USER", "gladys")
    password = os.environ.get("POSTGRES_PASSWORD", "gladys")

    print(f"Connecting to PostgreSQL at {host}:{port}/{database}...")
    conn = await asyncpg.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )
    await register_vector(conn)

    # Initialize embedding generator
    print("Loading embedding model...")
    embeddings = EmbeddingGenerator()

    # Find heuristics without embeddings
    rows = await conn.fetch("""
        SELECT id, condition->>'text' as condition_text
        FROM heuristics
        WHERE condition_embedding IS NULL
          AND condition->>'text' IS NOT NULL
          AND condition->>'text' != ''
    """)

    if not rows:
        print("No heuristics need backfilling.")
        await conn.close()
        return

    print(f"Found {len(rows)} heuristics to backfill...")

    # Process in batches
    batch_size = 10
    updated = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        texts = [row["condition_text"] for row in batch]

        # Generate embeddings for batch
        batch_embeddings = embeddings.generate_batch(texts)

        # Update each heuristic
        for j, row in enumerate(batch):
            embedding = batch_embeddings[j]
            await conn.execute("""
                UPDATE heuristics
                SET condition_embedding = $2
                WHERE id = $1
            """, row["id"], embedding)
            updated += 1

        print(f"  Updated {updated}/{len(rows)} heuristics...")

    print(f"Done! Backfilled {updated} heuristics with embeddings.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(backfill_embeddings())
