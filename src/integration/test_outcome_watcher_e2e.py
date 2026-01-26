#!/usr/bin/env python3
"""E2E Test: OutcomeWatcher implicit feedback through Orchestrator.

Tests the complete implicit feedback loop:
1. Store heuristic with condition_text matching an outcome pattern
2. Send trigger event through Orchestrator → heuristic matches → fire registered
3. Send outcome event through Orchestrator → OutcomeWatcher detects → confidence updated

Prerequisites:
- Services running with OutcomeWatcher patterns configured
- docker-compose.yml has OUTCOME_PATTERNS_JSON with test patterns

Usage:
    python scripts/docker.py test test_outcome_watcher_e2e.py   # DOCKER
    python scripts/local.py test test_outcome_watcher_e2e.py    # LOCAL
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

# Add paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "memory" / "python"))

try:
    from gladys_orchestrator.generated import (
        common_pb2,
        memory_pb2,
        memory_pb2_grpc,
        orchestrator_pb2,
        orchestrator_pb2_grpc,
        types_pb2,
    )
except ImportError:
    print("ERROR: Proto stubs not found. Run 'python scripts/proto_gen.py'")
    sys.exit(1)

# Configuration from environment (set by conftest.py or wrapper scripts)
# These will be populated by conftest.py's pytest_configure hook if running via pytest
ORCHESTRATOR_ADDRESS = os.environ.get("ORCHESTRATOR_ADDRESS")
MEMORY_ADDRESS = os.environ.get("PYTHON_ADDRESS")
SALIENCE_ADDRESS = os.environ.get("RUST_ADDRESS")  # Rust salience gateway for cache management

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_outcome_watcher_e2e")


def create_event(event_id: str, raw_text: str, source: str = "test") -> common_pb2.Event:
    """Create a test event with proper timestamp.

    NOTE: We do NOT set explicit salience here. This allows the event to flow
    through EvaluateSalience which queries for matching heuristics and populates
    matched_heuristic_id. If we set explicit salience, we bypass that query.
    """
    now = Timestamp()
    now.FromMilliseconds(int(time.time() * 1000))

    return common_pb2.Event(
        id=event_id,
        source=source,
        raw_text=raw_text,
        timestamp=now,
        # Don't set salience - let EvaluateSalience find matching heuristics
    )


class TestOutcomeWatcherE2E:
    """E2E test for OutcomeWatcher through Orchestrator."""

    def __init__(self):
        self.orch_channel = None
        self.orch_stub = None
        self.memory_channel = None
        self.memory_stub = None
        self.salience_channel = None
        self.salience_stub = None
        self.test_heuristic_id = None
        self._condition_text = None
        self._trigger_text = None

    async def setup(self):
        """Connect to services."""
        # Re-read env vars (conftest.py may have set them after module load)
        global ORCHESTRATOR_ADDRESS, MEMORY_ADDRESS, SALIENCE_ADDRESS
        ORCHESTRATOR_ADDRESS = os.environ.get("ORCHESTRATOR_ADDRESS")
        MEMORY_ADDRESS = os.environ.get("PYTHON_ADDRESS")
        SALIENCE_ADDRESS = os.environ.get("RUST_ADDRESS")

        if not ORCHESTRATOR_ADDRESS or not MEMORY_ADDRESS:
            raise RuntimeError(
                "Service addresses not configured. "
                "Run via: python scripts/local.py test test_outcome_watcher_e2e.py"
            )

        logger.info(f"Connecting to Orchestrator at {ORCHESTRATOR_ADDRESS}")
        self.orch_channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDRESS)
        self.orch_stub = orchestrator_pb2_grpc.OrchestratorServiceStub(self.orch_channel)

        logger.info(f"Connecting to Memory at {MEMORY_ADDRESS}")
        self.memory_channel = grpc.aio.insecure_channel(MEMORY_ADDRESS)
        self.memory_stub = memory_pb2_grpc.MemoryStorageStub(self.memory_channel)

        if SALIENCE_ADDRESS:
            logger.info(f"Connecting to Salience Gateway at {SALIENCE_ADDRESS}")
            self.salience_channel = grpc.aio.insecure_channel(SALIENCE_ADDRESS)
            self.salience_stub = memory_pb2_grpc.SalienceGatewayStub(self.salience_channel)

        # Verify connections
        try:
            health = await self.orch_stub.GetHealth(types_pb2.GetHealthRequest(), timeout=5)
            logger.info(f"Orchestrator health: {types_pb2.HealthStatus.Name(health.status)}")
        except Exception as e:
            raise RuntimeError(f"Cannot connect to Orchestrator: {e}")

        try:
            health = await self.memory_stub.GetHealth(types_pb2.GetHealthRequest(), timeout=5)
            logger.info(f"Memory health: {types_pb2.HealthStatus.Name(health.status)}")
        except Exception as e:
            raise RuntimeError(f"Cannot connect to Memory: {e}")

        if self.salience_stub:
            try:
                health = await self.salience_stub.GetHealth(types_pb2.GetHealthRequest(), timeout=5)
                logger.info(f"Salience health: {types_pb2.HealthStatus.Name(health.status)}")
            except Exception as e:
                logger.warning(f"Cannot connect to Salience Gateway: {e}")
                self.salience_stub = None

    async def cleanup(self):
        """Close connections."""
        if self.orch_channel:
            await self.orch_channel.close()
        if self.memory_channel:
            await self.memory_channel.close()
        if self.salience_channel:
            await self.salience_channel.close()

    async def cleanup_old_test_heuristics(self):
        """Remove any old test heuristics with similar conditions.

        This prevents stale heuristics from previous test runs from interfering
        with the current test by matching before the newly created heuristic.
        """
        # Query for heuristics with test-outcome prefix
        try:
            response = await self.memory_stub.QueryMatchingHeuristics(
                memory_pb2.QueryMatchingHeuristicsRequest(
                    event_text="oven",  # Our test pattern
                    similarity_threshold=0.5,  # Low threshold to catch all
                    limit=20,
                )
            )

            for match in response.matches:
                if match.heuristic and match.heuristic.name.startswith("test-outcome-"):
                    logger.info(f"Cleaning up old test heuristic: {match.heuristic.id}")
                    # Note: There's no DeleteHeuristic RPC, so we'll just note it
                    # The test works by comparing specific heuristic IDs
        except Exception as e:
            logger.debug(f"Could not query old heuristics: {e}")

    async def store_test_heuristic(self) -> str:
        """Store a heuristic that matches the 'oven' outcome pattern."""
        # Clean up old test heuristics first to avoid interference
        await self.cleanup_old_test_heuristics()

        heuristic_id = str(uuid.uuid4())
        self.test_heuristic_id = heuristic_id
        # Condition must contain "oven" to match OUTCOME_PATTERNS_JSON trigger
        # Use unique suffix to ensure this heuristic matches over any stale ones
        unique_suffix = heuristic_id[:8]
        self._condition_text = f"When the oven is left on too long, alert user to turn it off (test-{unique_suffix})"
        # Event text also needs unique suffix to guarantee high similarity match
        self._trigger_text = f"The oven is left on, please turn it off (test-{unique_suffix})"

        heuristic = memory_pb2.Heuristic(
            id=heuristic_id,
            name=f"test-outcome-{heuristic_id[:8]}",
            condition_text=self._condition_text,
            effects_json='{"action": "alert_oven", "salience": {"threat": 0.8}}',
            confidence=0.5,  # Start at 0.5 so we can detect increase
            origin="test",
            origin_id="test_outcome_watcher_e2e",
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

        logger.info(f"Stored heuristic: {heuristic_id}")
        logger.info(f"  condition: {self._condition_text}")
        return heuristic_id

    async def flush_salience_cache(self):
        """Flush the Rust salience cache to ensure fresh heuristic lookups."""
        if not self.salience_stub:
            logger.warning("No salience stub - cannot flush cache")
            return

        try:
            await self.salience_stub.FlushCache(memory_pb2.FlushCacheRequest(), timeout=5)
            logger.info("Flushed salience cache")
        except Exception as e:
            logger.warning(f"Failed to flush cache: {e}")

    async def get_heuristic_confidence(self) -> float:
        """Get confidence of test heuristic by ID."""
        response = await self.memory_stub.GetHeuristic(
            memory_pb2.GetHeuristicRequest(id=self.test_heuristic_id)
        )

        if response.error:
            raise RuntimeError(f"GetHeuristic failed: {response.error}")

        if not response.heuristic or not response.heuristic.id:
            raise RuntimeError(f"Heuristic {self.test_heuristic_id} not found")

        return response.heuristic.confidence

    async def send_event(self, event: common_pb2.Event) -> orchestrator_pb2.EventAck:
        """Send event through Orchestrator and get response."""
        async def event_generator():
            yield event

        async for ack in self.orch_stub.PublishEvents(event_generator()):
            return ack

        raise RuntimeError("No ack received from Orchestrator")

    async def run_test(self) -> bool:
        """Run the E2E test."""
        logger.info("=" * 70)
        logger.info("E2E TEST: OutcomeWatcher Implicit Feedback via Orchestrator")
        logger.info("=" * 70)

        try:
            # Step 1: Store test heuristic
            logger.info("\n[Step 1] Storing test heuristic (contains 'oven')...")
            await self.store_test_heuristic()

            # Flush salience cache so Rust will query fresh heuristics
            logger.info("Flushing salience cache to ensure fresh lookup...")
            await self.flush_salience_cache()

            # Brief delay for embedding generation to complete
            logger.info("Waiting for embedding generation to complete...")
            await asyncio.sleep(2.0)

            initial_confidence = await self.get_heuristic_confidence()
            logger.info(f"Initial confidence: {initial_confidence:.3f}")

            # Step 2: Send trigger event that should match the heuristic
            # NOTE: Text must achieve >= 0.7 cosine similarity with heuristic condition
            # Using unique suffix guarantees our new heuristic matches over any stale ones
            logger.info("\n[Step 2] Sending trigger event through Orchestrator...")
            trigger_event = create_event(
                event_id=str(uuid.uuid4()),
                raw_text=self._trigger_text,
                source="smart_home",
            )

            ack = await self.send_event(trigger_event)
            logger.info(f"Event ack: accepted={ack.accepted}, matched_heuristic={ack.matched_heuristic_id}")

            if not ack.matched_heuristic_id:
                logger.warning("WARNING: No heuristic matched. This may be expected if similarity threshold isn't met.")
                logger.warning("Continuing test - OutcomeWatcher may still work via direct pattern matching.")
            elif ack.matched_heuristic_id != self.test_heuristic_id:
                logger.warning(f"WARNING: Different heuristic matched: {ack.matched_heuristic_id}")
            else:
                logger.info(f"SUCCESS: Our test heuristic matched!")

            # Brief pause to let fire registration complete
            await asyncio.sleep(0.5)

            # Step 3: Send outcome event containing "oven off"
            logger.info("\n[Step 3] Sending outcome event ('oven off')...")
            outcome_event = create_event(
                event_id=str(uuid.uuid4()),
                raw_text="User turned the oven off after receiving the alert",
                source="smart_home",
            )

            ack2 = await self.send_event(outcome_event)
            logger.info(f"Outcome event ack: accepted={ack2.accepted}")

            # Wait for implicit feedback to be processed
            logger.info("\n[Step 4] Waiting for implicit feedback processing...")
            await asyncio.sleep(1.0)

            # Step 5: Verify confidence increased
            logger.info("\n[Step 5] Verifying confidence update...")
            final_confidence = await self.get_heuristic_confidence()

            delta = final_confidence - initial_confidence
            logger.info(f"Final confidence: {final_confidence:.3f}")
            logger.info(f"Delta: {delta:+.3f}")

            # Check if confidence increased
            if delta > 0:
                logger.info("\n" + "=" * 70)
                logger.info("PASS: Implicit feedback increased heuristic confidence!")
                logger.info("  OutcomeWatcher successfully detected outcome and sent feedback")
                logger.info("=" * 70)
                return True
            else:
                logger.warning("\n" + "=" * 70)
                logger.warning("INCONCLUSIVE: Confidence did not increase")
                logger.warning(f"  Initial: {initial_confidence:.3f}")
                logger.warning(f"  Final:   {final_confidence:.3f}")
                logger.warning("")
                logger.warning("Possible causes:")
                logger.warning("  - Orchestrator not configured with OUTCOME_PATTERNS_JSON")
                logger.warning("  - Trigger event didn't match heuristic (low similarity)")
                logger.warning("  - Pattern matching not working as expected")
                logger.warning("=" * 70)

                # Check if OutcomeWatcher is enabled by looking at health details
                try:
                    details = await self.orch_stub.GetHealthDetails(
                        types_pb2.GetHealthDetailsRequest(), timeout=5
                    )
                    logger.info(f"Orchestrator details: {dict(details.details)}")
                except Exception as e:
                    logger.warning(f"Could not get health details: {e}")

                return False

        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Run the E2E test."""
    test = TestOutcomeWatcherE2E()

    try:
        await test.setup()
        success = await test.run_test()
        return 0 if success else 1
    finally:
        await test.cleanup()


# Pytest-discoverable test function
import pytest

@pytest.mark.asyncio
async def test_outcome_watcher_e2e(service_env):
    """Pytest wrapper for OutcomeWatcher E2E test.

    The service_env fixture (from conftest.py) ensures services are running
    and environment variables are set before the test runs.
    """
    exit_code = await main()
    assert exit_code == 0, "OutcomeWatcher E2E test failed"


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
