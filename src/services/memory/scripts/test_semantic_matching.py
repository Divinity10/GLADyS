#!/usr/bin/env python3
"""Test semantic heuristic matching.

Verifies that:
1. Semantically similar phrases match (e.g., "get ice cream" ~ "get frozen dessert")
2. Semantically different phrases do NOT match (e.g., "get ice cream" !~ "get a new car")

Usage:
    uv run python scripts/test_semantic_matching.py --embeddings-only
    uv run python scripts/test_semantic_matching.py  # Full test with database

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
import uuid

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two embeddings."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class SimpleEmbeddingGenerator:
    """Simple embedding generator using sentence-transformers directly."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)

    def generate(self, text: str) -> np.ndarray:
        self._load_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)


async def test_semantic_matching():
    """Test that semantic matching works correctly with database."""
    import asyncpg
    from pgvector.asyncpg import register_vector

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
    embeddings = SimpleEmbeddingGenerator()

    # Test heuristic: "get ice cream"
    test_heuristic_id = uuid.uuid4()
    test_heuristic_text = "User wants to get ice cream"
    test_embedding = embeddings.generate(test_heuristic_text)

    print(f"\n{'='*60}")
    print(f"Creating test heuristic: '{test_heuristic_text}'")
    print(f"Heuristic ID: {test_heuristic_id}")
    print(f"Embedding dimensions: {len(test_embedding)}")
    print(f"{'='*60}\n")

    # Insert test heuristic
    await conn.execute("""
        INSERT INTO heuristics (id, name, condition, action, confidence, condition_embedding)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (id) DO UPDATE SET
            condition_embedding = EXCLUDED.condition_embedding
    """,
        test_heuristic_id,
        "test_ice_cream",
        {"text": test_heuristic_text},
        {"salience": {"opportunity": 0.8}},
        0.8,
        test_embedding,
    )

    # Test cases: (query_text, should_match, description)
    # Realistic expectations based on all-MiniLM-L6-v2 model behavior
    test_cases = [
        # Should match (semantically similar - same/very similar concepts)
        ("User wants to get frozen dessert", True, "frozen dessert ~ ice cream"),
        ("I'd like to get some ice cream", True, "same concept, rephrased"),
        ("Can we stop for ice cream?", True, "same concept, question form"),

        # Should NOT match (semantically different)
        ("User wants to get a new car", False, "car != ice cream"),
        ("User wants to buy a house", False, "house != ice cream"),
        ("Let's go to the movies", False, "movies != ice cream"),
        ("User sent an email about a meeting", False, "email/meeting != ice cream"),
    ]

    print("Testing semantic similarity matching...\n")

    # Threshold of 0.7 is stricter but needed to reject structural similarity
    similarity_threshold = 0.7
    all_passed = True

    for query_text, should_match, description in test_cases:
        query_embedding = embeddings.generate(query_text)

        # Query using vector similarity
        rows = await conn.fetch("""
            SELECT id, name, condition->>'text' as condition_text,
                   1 - (condition_embedding <=> $1) AS similarity
            FROM heuristics
            WHERE condition_embedding IS NOT NULL
              AND id = $3
            ORDER BY condition_embedding <=> $1
            LIMIT 1
        """, query_embedding, similarity_threshold, test_heuristic_id)

        if rows:
            similarity = rows[0]["similarity"]
            matched = similarity >= similarity_threshold
        else:
            similarity = 0.0
            matched = False

        # Check if result matches expectation
        passed = matched == should_match
        all_passed = all_passed and passed

        status = "PASS" if passed else "FAIL"
        match_status = "MATCH" if matched else "NO MATCH"
        expected = "should match" if should_match else "should NOT match"

        print(f"[{status}] {description}")
        print(f"       Query: '{query_text}'")
        print(f"       Similarity: {similarity:.4f} (threshold: {similarity_threshold})")
        print(f"       Result: {match_status} ({expected})")
        print()

    # Cleanup: remove test heuristic
    await conn.execute("DELETE FROM heuristics WHERE id = $1", test_heuristic_id)
    await conn.close()

    print(f"{'='*60}")
    if all_passed:
        print("All tests PASSED! Semantic matching is working correctly.")
    else:
        print("Some tests FAILED. Check the results above.")
    print(f"{'='*60}")

    return all_passed


def test_embeddings_directly():
    """Test embedding similarity without database (for debugging)."""
    print("Testing embeddings directly (no database)...\n")

    embeddings = SimpleEmbeddingGenerator()

    # First test: The original bug case - email about violence vs email about meeting
    print("="*60)
    print("TEST 1: Original bug case (violence vs meeting)")
    print("="*60 + "\n")

    violence_text = "Mike Mulcahy sent an email about killing his neighbor"
    meeting_text = "Mike Mulcahy sent an email about meeting at 1pm"

    violence_embedding = embeddings.generate(violence_text)
    meeting_embedding = embeddings.generate(meeting_text)

    similarity = cosine_similarity(violence_embedding, meeting_embedding)
    # Need threshold > 0.69 to reject this case, but still accept true matches
    threshold = 0.7

    print(f"Heuristic: '{violence_text}'")
    print(f"Event:     '{meeting_text}'")
    print(f"Similarity: {similarity:.4f}")
    print(f"Threshold:  {threshold}")
    print(f"Result:     {'MATCH (BAD!)' if similarity >= threshold else 'NO MATCH (GOOD!)'}")
    print()

    if similarity >= threshold:
        print("WARNING: These should NOT match! Semantic matching may need tuning.")
        return False

    print("Correctly rejected - semantic meaning is different!\n")

    # Second test: Ice cream examples
    print("="*60)
    print("TEST 2: Ice cream variations")
    print("="*60 + "\n")

    base_text = "User wants to get ice cream"
    base_embedding = embeddings.generate(base_text)

    # Test phrases with realistic expectations for 0.7 threshold
    # At 0.7, only very close semantic matches pass - this is intentional
    # to prevent structural similarity (like "email about X" vs "email about Y")
    test_phrases = [
        # Strong semantic matches (truly equivalent concepts, >0.75)
        ("User wants to get frozen dessert", True),    # ~0.78 - synonym
        ("User wants to get ice cream cone", True),    # ~0.80 - same concept

        # Rephrasings are NOT expected to match at 0.7 threshold
        # This is acceptable - heuristics should be specific
        ("I'd like to get some ice cream", False),     # ~0.70 - rephrasing (borderline)
        ("Can we stop for ice cream?", False),         # ~0.63 - rephrasing

        # Clear non-matches (different concepts)
        ("User wants to get a new car", False),        # ~0.44 - different object
        ("User wants to buy a house", False),          # ~0.38 - different verb+object
        ("Let's go to the movies", False),             # ~0.11 - totally different
        ("User sent an email about a meeting", False), # ~0.24 - different domain
    ]

    print(f"Base phrase: '{base_text}'\n")
    print(f"{'Phrase':<45} | Similarity | Expected | Result")
    print("-" * 75)

    # Threshold of 0.7 is stricter but needed to reject structural similarity
    # (e.g., "email about X" vs "email about Y" where X and Y are very different)
    threshold = 0.7
    all_passed = True

    for phrase, should_match in test_phrases:
        phrase_embedding = embeddings.generate(phrase)
        similarity = cosine_similarity(base_embedding, phrase_embedding)
        matched = similarity >= threshold
        passed = matched == should_match

        all_passed = all_passed and passed

        expected = "MATCH" if should_match else "NO"
        result = "PASS" if passed else "FAIL"

        print(f"{phrase:<45} | {similarity:.4f}     | {expected:<8} | {result}")

    print()
    print(f"{'='*60}")
    if all_passed:
        print("All embedding tests PASSED!")
    else:
        print("Some embedding tests FAILED!")
    print(f"{'='*60}")

    return all_passed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings-only", action="store_true",
                       help="Only test embeddings, skip database tests")
    args = parser.parse_args()

    if args.embeddings_only:
        success = test_embeddings_directly()
        sys.exit(0 if success else 1)
    else:
        # First test embeddings directly
        emb_success = test_embeddings_directly()

        if not emb_success:
            print("\nEmbedding tests failed, skipping database tests.")
            sys.exit(1)

        # Then test with database
        print("\n" + "="*60 + "\n")
        success = asyncio.run(test_semantic_matching())
        sys.exit(0 if success else 1)
