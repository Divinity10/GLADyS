#!/usr/bin/env python3
"""Test Skill Registry - Phase 3 Phase validation.

Proves:
1. Skill manifests can be loaded from disk
2. Capabilities are indexed correctly
3. Query "what can check player status?" returns minecraft-skill.check_player
4. Skills can be synced to database

Run with:
    cd src/integration && uv run python test_skill_registry.py

Requires:
    - Local PostgreSQL with gladys database (for DB sync test)
"""

import os
import sys
import tempfile
from pathlib import Path

# Add orchestrator to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "orchestrator"))

from gladys_orchestrator.skill_registry import SkillRegistry, CapabilityMatch


# Use the actual plugins directory
PLUGINS_DIR = PROJECT_ROOT / "plugins" / "skills"


def test_load_minecraft_skill():
    """Test that minecraft-skill manifest loads correctly."""
    print("\n--- Test: Load minecraft-skill manifest ---")
    registry = SkillRegistry()
    loaded = registry.load_from_directory(PLUGINS_DIR)

    assert loaded >= 1, "Should load at least minecraft-skill"
    assert registry.skill_count >= 1

    skill = registry.get_skill("minecraft-skill")
    assert skill is not None, "minecraft-skill should exist"
    assert skill.name == "Minecraft Skill"
    assert skill.category == "capability"
    assert len(skill.methods) > 0

    print(f"  [OK] Loaded {loaded} skill(s)")
    print(f"  [OK] minecraft-skill: {skill.name} ({skill.category})")
    print(f"  [OK] Methods: {[m.name for m in skill.methods]}")


def test_capabilities_indexed():
    """Test that capabilities are indexed for discovery."""
    print("\n--- Test: Capabilities indexed ---")
    registry = SkillRegistry()
    registry.load_from_directory(PLUGINS_DIR)

    caps = registry.get_all_capabilities()
    print(f"  Indexed capabilities: {caps}")

    assert "check_player_status" in caps
    assert "query_player_location" in caps
    assert "query_inventory" in caps
    assert "send_chat_message" in caps

    print(f"  [OK] All expected capabilities indexed")


def test_query_capability_exact():
    """Test exact capability query returns correct skill and method."""
    print("\n--- Test: Query capability (exact) ---")
    registry = SkillRegistry()
    registry.load_from_directory(PLUGINS_DIR)

    # Query: "what can check player status?"
    matches = registry.query_capability("check_player_status")
    print(f"  Query: 'check_player_status'")
    print(f"  Matches: {[(m.skill_id, m.method_name) for m in matches]}")

    assert len(matches) >= 1
    match = matches[0]
    assert match.skill_id == "minecraft-skill"
    assert match.method_name == "check_player"
    assert match.capability == "check_player_status"

    # Verify method has expected parameters
    param_names = [p["name"] for p in match.parameters]
    assert "player_name" in param_names

    print(f"  [OK] Found: {match.skill_id}.{match.method_name}")
    print(f"  [OK] Parameters: {param_names}")


def test_query_capability_not_found():
    """Test that querying non-existent capability returns empty list."""
    print("\n--- Test: Query non-existent capability ---")
    registry = SkillRegistry()
    registry.load_from_directory(PLUGINS_DIR)

    matches = registry.query_capability("nonexistent_capability")
    assert matches == [], "Should return empty list for unknown capability"

    print(f"  [OK] Non-existent capability returns empty list")


def test_query_fuzzy():
    """Test fuzzy capability matching from natural language."""
    print("\n--- Test: Fuzzy query ---")
    registry = SkillRegistry()
    registry.load_from_directory(PLUGINS_DIR)

    # Natural language query
    query = "check player status"
    matches = registry.query_capabilities_fuzzy(query)
    print(f"  Query: '{query}'")
    print(f"  Matches: {[(m.skill_id, m.method_name, m.capability) for m in matches]}")

    assert len(matches) >= 1
    # Should find check_player_status capability
    assert any(m.capability == "check_player_status" for m in matches)

    print(f"  [OK] Fuzzy query found matching capability")


def test_db_sync():
    """Test syncing skills to database."""
    print("\n--- Test: Database sync ---")

    # Check for database connection
    db_host = os.environ.get("GLADYS_DB_HOST", "localhost")
    db_port = os.environ.get("GLADYS_DB_PORT", "5432")
    db_name = os.environ.get("GLADYS_DB_NAME", "gladys")
    db_user = os.environ.get("GLADYS_DB_USER", "gladys")
    db_pass = os.environ.get("GLADYS_DB_PASSWORD", "gladys_dev")

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_pass,
        )
    except ImportError:
        print("  [SKIP] psycopg2 not installed")
        return
    except Exception as e:
        print(f"  [SKIP] Database not available: {e}")
        return

    try:
        # Load from files
        registry = SkillRegistry()
        loaded = registry.load_from_directory(PLUGINS_DIR)
        print(f"  Loaded {loaded} skill(s) from files")

        # Sync to DB
        synced = registry.sync_to_db(conn)
        print(f"  Synced {synced} skill(s) to database")

        # Load from DB
        registry2 = SkillRegistry.load_from_db(conn)
        print(f"  Loaded {registry2.skill_count} skill(s) from database")

        # Verify capabilities match
        caps1 = set(registry.get_all_capabilities())
        caps2 = set(registry2.get_all_capabilities())
        assert caps1 == caps2, f"Capabilities mismatch: {caps1} vs {caps2}"

        # Verify query works from DB-loaded registry
        matches = registry2.query_capability("check_player_status")
        assert len(matches) >= 1
        assert matches[0].skill_id == "minecraft-skill"

        print(f"  [OK] Database sync works correctly")

    finally:
        conn.close()


def test_poc_success_criteria():
    """
    Phase 3 Success Criteria (from POC_ROADMAP.md):
    - Can query "what skill checks player online status?"
    - Returns correct skill with correct method
    """
    print("\n" + "=" * 70)
    print("POC PHASE 3 SUCCESS CRITERIA")
    print("=" * 70)

    registry = SkillRegistry()
    registry.load_from_directory(PLUGINS_DIR)

    # The exact query from roadmap
    matches = registry.query_capability("check_player_status")

    # Must return at least one match
    assert len(matches) >= 1, "Should find a skill for check_player_status"

    # Must be minecraft-skill with check_player method
    match = matches[0]
    assert match.skill_id == "minecraft-skill", "Should be minecraft-skill"
    assert match.method_name == "check_player", "Should be check_player method"

    # Method should accept player_name parameter
    param_names = [p["name"] for p in match.parameters]
    assert "player_name" in param_names, "Method should accept player_name"

    print(f"\n  Query: 'what skill checks player online status?'")
    print(f"  Result: {match.skill_id}.{match.method_name}(player_name=...)")
    print(f"\n  [OK] PHASE 3 SUCCESS CRITERIA MET!")
    print("=" * 70)


def main():
    """Run all tests."""
    print("=" * 70)
    print("SKILL REGISTRY TEST - Phase 3 Phase Validation")
    print("=" * 70)

    tests = [
        test_load_minecraft_skill,
        test_capabilities_indexed,
        test_query_capability_exact,
        test_query_capability_not_found,
        test_query_fuzzy,
        test_db_sync,
        test_poc_success_criteria,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


