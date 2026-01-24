#!/usr/bin/env python3
"""Test semantic memory: entities and relationships.

This test proves that:
1. Entities can be stored and queried by name
2. Relationships can be stored between entities
3. Context expansion retrieves related entities (1-2 hops)
4. The "Is Steve online?" scenario works

Usage:
    # Start Memory service first:
    cd src/memory/python && uv run python -m gladys_memory.grpc_server

    # Then run this test:
    cd src/integration && uv run python test_semantic_memory.py
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

# Add paths for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

import grpc


async def run_test():
    """Run the semantic memory test."""
    try:
        from gladys_memory import memory_pb2, memory_pb2_grpc
    except ImportError:
        try:
            from gladys_memory.generated import memory_pb2, memory_pb2_grpc
        except ImportError:
            print("ERROR: Memory proto stubs not available")
            print("Run: make proto")
            return False

    print("=" * 70)
    print("SEMANTIC MEMORY TEST: Entities & Relationships")
    print("=" * 70)

    try:
        channel = grpc.aio.insecure_channel("localhost:50051")
        await asyncio.wait_for(channel.channel_ready(), timeout=3.0)
    except Exception as e:
        print(f"\nERROR: Cannot connect to Memory service at localhost:50051")
        print(f"  {e}")
        print("\nStart the Memory service first:")
        print("  cd src/memory/python && uv run python -m gladys_memory.grpc_server")
        return False

    async with channel:
        stub = memory_pb2_grpc.MemoryStorageStub(channel)

        # Generate unique IDs for this test run
        steve_id = str(uuid.uuid4())
        buggy_id = str(uuid.uuid4())
        minecraft_id = str(uuid.uuid4())

        # ============================================================
        # Step 1: Store entities
        # ============================================================
        print("\n[Step 1] Storing entities...")

        # Store Steve (person)
        steve = memory_pb2.Entity(
            id=steve_id,
            canonical_name="Steve",
            aliases=["Steven", "Steve M."],
            entity_type="person",
            attributes_json='{"notes": "Friend of Mike", "email": "steve@example.com"}',
            source="test",
        )
        response = await stub.StoreEntity(memory_pb2.StoreEntityRequest(
            entity=steve,
            generate_embedding=True,
        ))
        if not response.success:
            print(f"  ERROR storing Steve: {response.error}")
            return False
        print(f"  Stored: Steve (id={steve_id[:8]}...)")

        # Store Buggy (game character)
        buggy = memory_pb2.Entity(
            id=buggy_id,
            canonical_name="Buggy",
            entity_type="game_character",
            attributes_json='{"game": "minecraft", "skin": "default"}',
            source="test",
        )
        response = await stub.StoreEntity(memory_pb2.StoreEntityRequest(
            entity=buggy,
            generate_embedding=True,
        ))
        if not response.success:
            print(f"  ERROR storing Buggy: {response.error}")
            return False
        print(f"  Stored: Buggy (id={buggy_id[:8]}...)")

        # Store Minecraft (game)
        minecraft = memory_pb2.Entity(
            id=minecraft_id,
            canonical_name="Minecraft",
            entity_type="game",
            attributes_json='{"platform": "pc", "version": "1.20"}',
            source="test",
        )
        response = await stub.StoreEntity(memory_pb2.StoreEntityRequest(
            entity=minecraft,
            generate_embedding=True,
        ))
        if not response.success:
            print(f"  ERROR storing Minecraft: {response.error}")
            return False
        print(f"  Stored: Minecraft (id={minecraft_id[:8]}...)")

        # ============================================================
        # Step 2: Store relationships
        # ============================================================
        print("\n[Step 2] Storing relationships...")

        # Steve --[has_character]--> Buggy
        rel1 = memory_pb2.Relationship(
            subject_id=steve_id,
            predicate="has_character",
            object_id=buggy_id,
            confidence=1.0,
            source="user",
        )
        response = await stub.StoreRelationship(memory_pb2.StoreRelationshipRequest(
            relationship=rel1,
        ))
        if not response.success:
            print(f"  ERROR storing relationship: {response.error}")
            return False
        print(f"  Stored: Steve --[has_character]--> Buggy")

        # Buggy --[plays_in]--> Minecraft
        rel2 = memory_pb2.Relationship(
            subject_id=buggy_id,
            predicate="plays_in",
            object_id=minecraft_id,
            confidence=1.0,
            source="user",
        )
        response = await stub.StoreRelationship(memory_pb2.StoreRelationshipRequest(
            relationship=rel2,
        ))
        if not response.success:
            print(f"  ERROR storing relationship: {response.error}")
            return False
        print(f"  Stored: Buggy --[plays_in]--> Minecraft")

        # ============================================================
        # Step 3: Query entities by name
        # ============================================================
        print("\n[Step 3] Query entities by name 'Steve'...")

        query_response = await stub.QueryEntities(memory_pb2.QueryEntitiesRequest(
            name_query="Steve",
            limit=5,
        ))
        if query_response.error:
            print(f"  ERROR: {query_response.error}")
            return False

        print(f"  Found {len(query_response.matches)} match(es)")
        for match in query_response.matches:
            e = match.entity
            print(f"    - {e.canonical_name} (type={e.entity_type}, id={e.id[:8]}...)")

        if not any(m.entity.id == steve_id for m in query_response.matches):
            print("  ERROR: Steve not found in query results")
            return False

        # ============================================================
        # Step 4: Get relationships for Steve (1-hop)
        # ============================================================
        print("\n[Step 4] Get relationships for Steve (1-hop)...")

        rel_response = await stub.GetRelationships(memory_pb2.GetRelationshipsRequest(
            entity_id=steve_id,
            include_outgoing=True,
            include_incoming=True,
        ))
        if rel_response.error:
            print(f"  ERROR: {rel_response.error}")
            return False

        print(f"  Found {len(rel_response.relationships)} relationship(s)")
        for rel_with_entity in rel_response.relationships:
            r = rel_with_entity.relationship
            related = rel_with_entity.related_entity
            print(f"    - --[{r.predicate}]--> {related.canonical_name} ({related.entity_type})")

        # ============================================================
        # Step 5: Expand context (THE KEY TEST)
        # ============================================================
        print("\n[Step 5] Expand context for Steve (2-hop)...")
        print("  This is what we'd use for LLM prompt assembly")

        expand_response = await stub.ExpandContext(memory_pb2.ExpandContextRequest(
            entity_ids=[steve_id],
            max_hops=2,
            max_entities=10,
            min_confidence=0.5,
        ))
        if expand_response.error:
            print(f"  ERROR: {expand_response.error}")
            return False

        print(f"\n  Entities in context: {len(expand_response.entities)}")
        for e in expand_response.entities:
            print(f"    - {e.canonical_name} ({e.entity_type})")

        print(f"\n  Relationships in context: {len(expand_response.relationships)}")
        for r in expand_response.relationships:
            print(f"    - {r.subject_id[:8]}... --[{r.predicate}]--> {r.object_id[:8]}...")

        # Verify we got all 3 entities (Steve, Buggy, Minecraft)
        entity_names = {e.canonical_name for e in expand_response.entities}

        # ============================================================
        # Results
        # ============================================================
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)

        steve_found = "Steve" in entity_names
        buggy_found = "Buggy" in entity_names
        minecraft_found = "Minecraft" in entity_names

        print(f"\n  Steve in context:     {'YES' if steve_found else 'NO'}")
        print(f"  Buggy in context:     {'YES' if buggy_found else 'NO'} (1-hop)")
        print(f"  Minecraft in context: {'YES' if minecraft_found else 'NO'} (2-hop)")

        print("\n" + "=" * 70)

        if steve_found and buggy_found and minecraft_found:
            print("SUCCESS: Semantic memory works!")
            print("  - Entities stored and queried")
            print("  - Relationships connect entities")
            print("  - Context expansion retrieves 2-hop graph")
            print("\n  Ready for 'Is Steve online?' scenario:")
            print("    1. Extract 'Steve' from query")
            print("    2. ExpandContext(Steve) -> Steve, Buggy, Minecraft")
            print("    3. LLM sees Buggy plays Minecraft")
            print("    4. LLM creates plan: check_player(Buggy) in Minecraft")
            print("=" * 70)
            return True
        else:
            print("FAILED: Context expansion incomplete")
            print("  Expected all 3 entities in 2-hop context")
            print("=" * 70)
            return False


async def main():
    success = await run_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
