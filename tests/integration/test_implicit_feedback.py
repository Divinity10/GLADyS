#!/usr/bin/env python3
"""Integration Test: Implicit Feedback via Outcome Observation (Phase 2).

Tests the OutcomeWatcher's ability to detect outcomes and trigger implicit feedback.

Flow:
1. Store a heuristic with condition_text matching an outcome pattern
2. Register a "fire" with the OutcomeWatcher
3. Send an event that matches the expected outcome
4. Verify confidence was updated via implicit feedback

Usage (via wrapper scripts - recommended):
    python scripts/local.py test test_implicit_feedback.py   # LOCAL
    python scripts/docker.py test test_implicit_feedback.py  # DOCKER
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import grpc

# Add paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "memory"))

try:
    from gladys_orchestrator.generated import memory_pb2, memory_pb2_grpc
    from gladys_orchestrator.outcome_watcher import OutcomeWatcher, OutcomePattern
    from gladys_orchestrator.clients.memory_client import MemoryStorageClient
except ImportError:
    print("ERROR: Proto stubs not found. Run 'make proto'")
    sys.exit(1)

# Configuration
LOG_LEVEL = logging.INFO

# Require explicit environment
MEMORY_ADDRESS = os.environ.get("PYTHON_ADDRESS")
if not MEMORY_ADDRESS:
    print("ERROR: PYTHON_ADDRESS environment variable required.")
    print("Use wrapper scripts to run tests:")
    print("  python scripts/local.py test test_implicit_feedback.py   # LOCAL")
    print("  python scripts/docker.py test test_implicit_feedback.py  # DOCKER")
    sys.exit(1)

# Setup logging
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_implicit_feedback")


class TestImplicitFeedback:
    """Test implicit feedback via OutcomeWatcher."""

    def __init__(self):
        self.memory_channel = None
        self.memory_stub = None
        self.memory_client = None
        self.test_heuristic_id = None
        self._last_condition_text = None  # For querying heuristic by text

    async def setup(self):
        """Connect to services."""
        logger.info(f"Connecting to Memory Storage at {MEMORY_ADDRESS}")
        self.memory_channel = grpc.aio.insecure_channel(MEMORY_ADDRESS)
        self.memory_stub = memory_pb2_grpc.MemoryStorageStub(self.memory_channel)

        # Create a MemoryStorageClient for the OutcomeWatcher
        self.memory_client = MemoryStorageClient(MEMORY_ADDRESS)
        await self.memory_client.connect()

        logger.info("Connected to services")

    async def cleanup(self):
        """Cleanup test data and connections."""
        # Note: No DeleteHeuristic RPC available, test heuristics will persist
        # This is fine for tests - they use unique IDs and won't interfere

        if self.memory_client:
            await self.memory_client.close()
        if self.memory_channel:
            await self.memory_channel.close()

        if self.test_heuristic_id:
            logger.info(f"Test heuristic {self.test_heuristic_id} left in DB (no delete RPC)")

    async def store_test_heuristic(self, condition_text: str, confidence: float = 0.6) -> str:
        """Store a test heuristic and return its ID."""
        heuristic_id = str(uuid.uuid4())
        self.test_heuristic_id = heuristic_id
        self._last_condition_text = condition_text  # Save for querying

        heuristic = memory_pb2.Heuristic(
            id=heuristic_id,
            name=f"test-{heuristic_id[:8]}",
            condition_text=condition_text,
            effects_json='{"action": "test_action"}',
            confidence=confidence,
            origin="test",
            origin_id="test_implicit_feedback",
            created_at_ms=int(time.time() * 1000),
        )

        response = await self.memory_stub.StoreHeuristic(
            memory_pb2.StoreHeuristicRequest(
                heuristic=heuristic,
                generate_embedding=True,
            )
        )

        if not response.success:
            raise RuntimeError(f"Failed to store heuristic: {response.error}")

        logger.info(f"Stored heuristic {heuristic_id}: {condition_text}")
        return heuristic_id

    async def get_heuristic_confidence(self, heuristic_id: str) -> float:
        """Get current confidence of a heuristic by querying with its condition text."""
        # Query for the heuristic by its known condition text
        # This is a workaround since there's no GetHeuristic RPC
        response = await self.memory_stub.QueryHeuristics(
            memory_pb2.QueryHeuristicsRequest(
                query_text=self._last_condition_text,  # Use the condition text we stored
                min_similarity=0.9,  # High similarity to find exact match
                limit=10,
            )
        )

        # Find our heuristic by ID
        for match in response.matches:
            if match.heuristic.id == heuristic_id:
                return match.heuristic.confidence

        raise RuntimeError(f"Heuristic {heuristic_id} not found in query results")

    async def run_test(self) -> bool:
        """Run the implicit feedback test.

        Scenario: Oven Alert
        1. Store heuristic: "When oven is left on, alert user"
        2. Configure OutcomeWatcher to expect "oven turned off"
        3. Simulate heuristic fire
        4. Send outcome event: "User turned off the oven"
        5. Verify confidence increased
        """
        logger.info("=" * 60)
        logger.info("TEST: Implicit Feedback via Outcome Observation")
        logger.info("=" * 60)

        try:
            # Step 1: Store test heuristic
            logger.info("\n[Step 1] Storing test heuristic...")
            condition_text = "When the oven is left on, alert the user"
            heuristic_id = await self.store_test_heuristic(condition_text, confidence=0.6)

            initial_confidence = await self.get_heuristic_confidence(heuristic_id)
            logger.info(f"Initial confidence: {initial_confidence:.3f}")

            # Step 2: Create OutcomeWatcher with test pattern
            logger.info("\n[Step 2] Creating OutcomeWatcher with outcome pattern...")
            patterns = [
                OutcomePattern(
                    trigger_pattern="oven",  # Matches "oven is left on"
                    outcome_pattern="oven turned off",  # Expected outcome
                    timeout_sec=60,
                    is_success=True,
                )
            ]
            watcher = OutcomeWatcher(patterns=patterns, memory_client=self.memory_client)
            logger.info(f"OutcomeWatcher created with pattern: trigger='oven', outcome='oven turned off'")

            # Step 3: Register heuristic fire
            logger.info("\n[Step 3] Registering heuristic fire...")
            registered = await watcher.register_fire(
                heuristic_id=heuristic_id,
                event_id="evt-oven-alert-001",
                predicted_success=0.7,
                condition_text=condition_text,  # Provide directly to avoid RPC
            )
            if not registered:
                logger.error("FAIL: Failed to register fire - pattern didn't match")
                return False
            logger.info(f"Fire registered. Pending outcomes: {watcher.pending_count}")

            # Step 4: Send outcome event
            logger.info("\n[Step 4] Sending outcome event...")

            # Create a simple event-like object
            class MockEvent:
                def __init__(self, raw_text):
                    self.raw_text = raw_text
                    self.id = f"evt-outcome-{uuid.uuid4().hex[:8]}"

            outcome_event = MockEvent("The oven turned off successfully after user action")
            resolved = await watcher.check_event(outcome_event)

            if not resolved:
                logger.error("FAIL: Outcome event did not resolve any pending expectations")
                return False

            logger.info(f"Outcome detected! Resolved heuristics: {resolved}")

            # Step 5: Verify confidence increased
            logger.info("\n[Step 5] Verifying confidence update...")
            await asyncio.sleep(0.5)  # Small delay for DB update
            final_confidence = await self.get_heuristic_confidence(heuristic_id)

            logger.info(f"Final confidence: {final_confidence:.3f}")
            logger.info(f"Delta: {final_confidence - initial_confidence:.3f}")

            if final_confidence > initial_confidence:
                logger.info("\n" + "=" * 60)
                logger.info("PASS: Implicit feedback increased confidence!")
                logger.info("=" * 60)
                return True
            else:
                logger.error("\n" + "=" * 60)
                logger.error("FAIL: Confidence did not increase")
                logger.error(f"  Initial: {initial_confidence:.3f}")
                logger.error(f"  Final:   {final_confidence:.3f}")
                logger.error("=" * 60)
                return False

        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Run the implicit feedback test."""
    test = TestImplicitFeedback()

    try:
        await test.setup()
        success = await test.run_test()
        return 0 if success else 1
    finally:
        await test.cleanup()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
