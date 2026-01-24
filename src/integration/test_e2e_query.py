#!/usr/bin/env python3
"""Test E2E Query Flow - Phase 4 PoC validation.

This test proves the "Is Steve online?" scenario works end-to-end:
1. User query → Extract entity (Steve)
2. Query Memory → Expand context (Steve → Buggy → Minecraft)
3. Query SkillRegistry → Find capability (check_player_status)
4. Mock skill execution → Get result
5. Compose response → "Steve (Buggy) is online in Minecraft"

This is the north star scenario from POC_ROADMAP.md.

Usage:
    # Start Memory service first:
    python scripts/services.py start memory

    # Then run this test (from memory directory for dependencies):
    cd src/memory/python && uv run python ../../integration/test_e2e_query.py
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Any

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

import grpc

# Skill Registry (no gRPC needed - direct import)
from gladys_orchestrator.skill_registry import SkillRegistry

# Plugins directory
PLUGINS_DIR = Path(__file__).parent.parent.parent / "plugins" / "skills"


@dataclass
class SkillCallResult:
    """Result from calling a skill method."""
    success: bool
    data: dict[str, Any]
    error: str | None = None


class MockSkillExecutor:
    """
    Mock skill executor for PoC.

    In production, this would:
    - Load the actual skill module
    - Call the method with parameters
    - Return real results

    For PoC, we simulate the Minecraft skill responses.
    """

    def __init__(self):
        # Simulated game state
        self.online_players = {"Buggy": True, "OtherPlayer": False}
        self.player_locations = {"Buggy": {"x": 100, "y": 64, "z": -200, "dimension": "overworld"}}

    def execute(self, skill_id: str, method_name: str, params: dict[str, Any]) -> SkillCallResult:
        """Execute a skill method (mocked)."""
        if skill_id == "minecraft-skill":
            if method_name == "check_player":
                player_name = params.get("player_name", "")
                online = self.online_players.get(player_name, False)
                return SkillCallResult(
                    success=True,
                    data={
                        "online": online,
                        "last_seen": "2026-01-24T10:30:00Z" if online else "2026-01-23T22:00:00Z",
                        "location": self.player_locations.get(player_name) if online else None,
                    }
                )
            elif method_name == "get_player_location":
                player_name = params.get("player_name", "")
                if player_name in self.player_locations:
                    return SkillCallResult(success=True, data=self.player_locations[player_name])
                return SkillCallResult(success=False, data={}, error=f"Player {player_name} not found")

        return SkillCallResult(success=False, data={}, error=f"Unknown skill/method: {skill_id}.{method_name}")


async def setup_test_data(stub, memory_pb2):
    """Set up Steve -> Buggy -> Minecraft entity graph."""
    # Generate unique IDs
    steve_id = str(uuid.uuid4())
    buggy_id = str(uuid.uuid4())
    minecraft_id = str(uuid.uuid4())

    # Store Steve
    steve = memory_pb2.Entity(
        id=steve_id,
        canonical_name="Steve",
        aliases=["Steven"],
        entity_type="person",
        attributes_json='{"relationship": "friend"}',
        source="test",
    )
    await stub.StoreEntity(memory_pb2.StoreEntityRequest(entity=steve, generate_embedding=True))

    # Store Buggy (Steve's Minecraft character)
    buggy = memory_pb2.Entity(
        id=buggy_id,
        canonical_name="Buggy",
        entity_type="game_character",
        attributes_json='{"game": "minecraft"}',
        source="test",
    )
    await stub.StoreEntity(memory_pb2.StoreEntityRequest(entity=buggy, generate_embedding=True))

    # Store Minecraft
    minecraft = memory_pb2.Entity(
        id=minecraft_id,
        canonical_name="Minecraft",
        entity_type="game",
        attributes_json='{"status": "running"}',
        source="test",
    )
    await stub.StoreEntity(memory_pb2.StoreEntityRequest(entity=minecraft, generate_embedding=True))

    # Store relationships
    # Steve --[has_character]--> Buggy
    await stub.StoreRelationship(memory_pb2.StoreRelationshipRequest(
        relationship=memory_pb2.Relationship(
            subject_id=steve_id,
            predicate="has_character",
            object_id=buggy_id,
            confidence=1.0,
            source="user",
        )
    ))

    # Buggy --[plays_in]--> Minecraft
    await stub.StoreRelationship(memory_pb2.StoreRelationshipRequest(
        relationship=memory_pb2.Relationship(
            subject_id=buggy_id,
            predicate="plays_in",
            object_id=minecraft_id,
            confidence=1.0,
            source="user",
        )
    ))

    return {"steve_id": steve_id, "buggy_id": buggy_id, "minecraft_id": minecraft_id}


async def run_e2e_test():
    """Run the full E2E query flow test."""
    # Import proto stubs
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
    print("E2E QUERY FLOW TEST: 'Is Steve online?'")
    print("=" * 70)
    print("\nThis test proves the north star scenario from POC_ROADMAP.md")

    # Connect to Memory service
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

        # ============================================================
        # Setup: Create entity graph
        # ============================================================
        print("\n[Setup] Creating entity graph...")
        ids = await setup_test_data(stub, memory_pb2)
        print(f"  Steve -> Buggy -> Minecraft graph created")

        # ============================================================
        # Step 1: User query arrives
        # ============================================================
        user_query = "Is Steve online?"
        print(f"\n[Step 1] User query: \"{user_query}\"")

        # In production, NER/LLM would extract entities
        # For test, we know "Steve" is the entity
        extracted_entity = "Steve"
        print(f"  Extracted entity: {extracted_entity}")

        # ============================================================
        # Step 2: Query Memory for entity
        # ============================================================
        print(f"\n[Step 2] Query Memory: Find '{extracted_entity}'...")

        query_response = await stub.QueryEntities(memory_pb2.QueryEntitiesRequest(
            name_query=extracted_entity,
            limit=5,
        ))

        if not query_response.matches:
            print(f"  ERROR: Entity '{extracted_entity}' not found")
            return False

        steve_entity = query_response.matches[0].entity
        print(f"  Found: {steve_entity.canonical_name} (id={steve_entity.id[:8]}...)")

        # ============================================================
        # Step 3: Expand context (2-hop)
        # ============================================================
        print(f"\n[Step 3] Expand context for {steve_entity.canonical_name} (2-hop)...")

        expand_response = await stub.ExpandContext(memory_pb2.ExpandContextRequest(
            entity_ids=[steve_entity.id],
            max_hops=2,
            max_entities=10,
            min_confidence=0.5,
        ))

        # Build a map of entities
        entities_by_id = {e.id: e for e in expand_response.entities}
        entity_names = {e.canonical_name for e in expand_response.entities}

        print(f"  Context contains: {entity_names}")

        # Find the character and game
        character_entity = None
        game_entity = None

        for rel in expand_response.relationships:
            if rel.predicate == "has_character":
                character_entity = entities_by_id.get(rel.object_id)
            elif rel.predicate == "plays_in":
                game_entity = entities_by_id.get(rel.object_id)

        if not character_entity or not game_entity:
            print(f"  ERROR: Could not find character or game in context")
            return False

        print(f"  Steve's character: {character_entity.canonical_name}")
        print(f"  Game: {game_entity.canonical_name}")

        # ============================================================
        # Step 4: Query SkillRegistry for capability
        # ============================================================
        print(f"\n[Step 4] Query SkillRegistry: 'check_player_status'...")

        skill_registry = SkillRegistry()
        skill_registry.load_from_directory(PLUGINS_DIR)

        matches = skill_registry.query_capability("check_player_status")

        if not matches:
            print(f"  ERROR: No skill found for 'check_player_status'")
            return False

        skill_match = matches[0]
        print(f"  Found: {skill_match.skill_id}.{skill_match.method_name}")
        print(f"  Parameters: {[p['name'] for p in skill_match.parameters]}")

        # ============================================================
        # Step 5: Execute skill (mocked)
        # ============================================================
        print(f"\n[Step 5] Execute skill: {skill_match.skill_id}.{skill_match.method_name}...")

        executor = MockSkillExecutor()
        result = executor.execute(
            skill_id=skill_match.skill_id,
            method_name=skill_match.method_name,
            params={"player_name": character_entity.canonical_name}
        )

        if not result.success:
            print(f"  ERROR: Skill execution failed: {result.error}")
            return False

        print(f"  Result: {json.dumps(result.data, indent=4)}")

        # ============================================================
        # Step 6: Compose response
        # ============================================================
        print(f"\n[Step 6] Compose response...")

        is_online = result.data.get("online", False)

        if is_online:
            response = f"Yes, {steve_entity.canonical_name} ({character_entity.canonical_name}) is online in {game_entity.canonical_name}"
            location = result.data.get("location")
            if location:
                response += f" at ({location['x']}, {location['y']}, {location['z']}) in {location['dimension']}"
        else:
            response = f"No, {steve_entity.canonical_name} ({character_entity.canonical_name}) is not currently online in {game_entity.canonical_name}"
            last_seen = result.data.get("last_seen")
            if last_seen:
                response += f". Last seen: {last_seen}"

        print(f"\n  Final Response: \"{response}\"")

        # ============================================================
        # Results
        # ============================================================
        print("\n" + "=" * 70)
        print("E2E FLOW COMPLETE")
        print("=" * 70)
        print("\nWhat we proved:")
        print("  1. [OK] User query parsed, entity extracted")
        print("  2. [OK] Memory queried, entity found")
        print("  3. [OK] Context expanded (Steve -> Buggy -> Minecraft)")
        print("  4. [OK] SkillRegistry queried, capability found")
        print("  5. [OK] Skill executed (mocked), result returned")
        print("  6. [OK] Response composed from context + skill result")
        print("\nThis is the 'Is Steve online?' scenario from POC_ROADMAP.md!")
        print("=" * 70)

        return True


async def main():
    success = await run_e2e_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
