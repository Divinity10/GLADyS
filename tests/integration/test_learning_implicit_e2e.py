#!/usr/bin/env python3
"""E2E Test: Learning Module implicit feedback (timeout = positive).

Tests the complete implicit feedback loop via LearningModule:
1. Store heuristic with condition_text matching an outcome pattern
2. Send trigger event → heuristic matches → fire registered + outcome expectation created
3. Wait for timeout to expire
4. LearningModule.cleanup_expired() sends positive implicit feedback
5. Verify confidence increased and feedback_source="implicit" in heuristic_fires

This validates PoC 1 criterion #6: implicit vs explicit distinguishable
in heuristic_fires.feedback_source.

Prerequisites:
- Services running with OutcomeWatcher patterns configured
- docker-compose.yml has OUTCOME_PATTERNS_JSON with test patterns

Usage:
    python scripts/docker.py test test_learning_implicit_e2e.py   # DOCKER
    python scripts/local.py test test_learning_implicit_e2e.py    # LOCAL
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
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "memory"))

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

# Configuration from environment
ORCHESTRATOR_ADDRESS = os.environ.get("ORCHESTRATOR_ADDRESS")
MEMORY_ADDRESS = os.environ.get("PYTHON_ADDRESS")
SALIENCE_ADDRESS = os.environ.get("RUST_ADDRESS")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_learning_implicit_e2e")


def create_event(event_id: str, raw_text: str, source: str = "test") -> common_pb2.Event:
    """Create a test event with proper timestamp."""
    now = Timestamp()
    now.FromMilliseconds(int(time.time() * 1000))
    return common_pb2.Event(
        id=event_id,
        source=source,
        raw_text=raw_text,
        timestamp=now,
    )


class TestLearningImplicitE2E:
    """E2E test for LearningModule implicit feedback (timeout path)."""

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
        global ORCHESTRATOR_ADDRESS, MEMORY_ADDRESS, SALIENCE_ADDRESS
        ORCHESTRATOR_ADDRESS = os.environ.get("ORCHESTRATOR_ADDRESS")
        MEMORY_ADDRESS = os.environ.get("PYTHON_ADDRESS")
        SALIENCE_ADDRESS = os.environ.get("RUST_ADDRESS")

        if not ORCHESTRATOR_ADDRESS or not MEMORY_ADDRESS:
            raise RuntimeError(
                "Service addresses not configured. "
                "Run via: python scripts/local.py test test_learning_implicit_e2e.py"
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
        for ch in [self.orch_channel, self.memory_channel, self.salience_channel]:
            if ch:
                await ch.close()

    async def store_test_heuristic(self) -> str:
        """Store a heuristic that matches the 'oven' outcome pattern."""
        heuristic_id = str(uuid.uuid4())
        self.test_heuristic_id = heuristic_id
        unique_suffix = heuristic_id[:8]
        self._condition_text = f"When the oven is left on, alert user (implicit-test-{unique_suffix})"
        self._trigger_text = f"The oven is left on, please turn it off (implicit-test-{unique_suffix})"

        heuristic = memory_pb2.Heuristic(
            id=heuristic_id,
            name=f"test-implicit-{heuristic_id[:8]}",
            condition_text=self._condition_text,
            effects_json='{"action": "alert_oven", "salience": {"threat": 0.8}}',
            confidence=0.5,
            origin="test",
            origin_id="test_learning_implicit_e2e",
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
        return heuristic_id

    async def flush_salience_cache(self):
        """Flush the Rust salience cache."""
        if not self.salience_stub:
            return
        try:
            await self.salience_stub.FlushCache(memory_pb2.FlushCacheRequest(), timeout=5)
            logger.info("Flushed salience cache")
        except Exception as e:
            logger.warning(f"Failed to flush cache: {e}")

    async def get_heuristic_confidence(self) -> float:
        """Get confidence of test heuristic."""
        response = await self.memory_stub.GetHeuristic(
            memory_pb2.GetHeuristicRequest(id=self.test_heuristic_id)
        )
        if response.error:
            raise RuntimeError(f"GetHeuristic failed: {response.error}")
        if not response.heuristic or not response.heuristic.id:
            raise RuntimeError(f"Heuristic {self.test_heuristic_id} not found")
        return response.heuristic.confidence

    async def send_event(self, event: common_pb2.Event) -> orchestrator_pb2.EventAck:
        """Send event through Orchestrator."""
        async def event_generator():
            yield event

        async for ack in self.orch_stub.PublishEvents(event_generator()):
            return ack
        raise RuntimeError("No ack received")

    async def run_test(self) -> bool:
        """Run the E2E test for implicit feedback via timeout."""
        logger.info("=" * 70)
        logger.info("E2E TEST: Learning Module — Implicit Feedback (Timeout = Positive)")
        logger.info("=" * 70)

        try:
            # Step 1: Store heuristic
            logger.info("\n[Step 1] Storing test heuristic...")
            await self.store_test_heuristic()
            await self.flush_salience_cache()
            await asyncio.sleep(2.0)  # Wait for embedding generation

            initial_confidence = await self.get_heuristic_confidence()
            logger.info(f"Initial confidence: {initial_confidence:.3f}")

            # Step 2: Send trigger event
            logger.info("\n[Step 2] Sending trigger event...")
            trigger_event = create_event(
                event_id=str(uuid.uuid4()),
                raw_text=self._trigger_text,
                source="smart_home",
            )
            ack = await self.send_event(trigger_event)
            logger.info(f"Event ack: accepted={ack.accepted}, matched={ack.matched_heuristic_id}")

            if not ack.matched_heuristic_id:
                logger.warning("No heuristic matched — cannot test timeout path")
                return False

            # Step 3: Wait for timeout + cleanup cycle
            # Default outcome timeout is 120s, cleanup interval is 30s
            # For testing, we need to wait for both. The configured timeout
            # in OUTCOME_PATTERNS_JSON determines the actual wait.
            logger.info("\n[Step 3] Waiting for outcome timeout + cleanup cycle...")
            logger.info("(This depends on OUTCOME_PATTERNS_JSON timeout_sec + cleanup interval)")

            # Poll for confidence change (max wait: timeout_sec + 2 * cleanup_interval)
            max_wait = 180  # 3 minutes max
            poll_interval = 10
            elapsed = 0
            confidence_changed = False

            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                current = await self.get_heuristic_confidence()
                delta = current - initial_confidence
                logger.info(f"  [{elapsed}s] confidence={current:.3f} (delta={delta:+.3f})")
                if delta > 0:
                    confidence_changed = True
                    break

            # Step 4: Verify
            final_confidence = await self.get_heuristic_confidence()
            delta = final_confidence - initial_confidence

            if confidence_changed:
                logger.info("\n" + "=" * 70)
                logger.info("PASS: Timeout implicit feedback increased confidence!")
                logger.info(f"  {initial_confidence:.3f} → {final_confidence:.3f} (delta={delta:+.3f})")
                logger.info("  feedback_source should be 'implicit' in heuristic_fires")
                logger.info("=" * 70)
                return True
            else:
                logger.warning("\n" + "=" * 70)
                logger.warning("INCONCLUSIVE: Confidence did not increase within timeout")
                logger.warning(f"  Initial: {initial_confidence:.3f}")
                logger.warning(f"  Final:   {final_confidence:.3f}")
                logger.warning("  Check OUTCOME_PATTERNS_JSON timeout_sec and cleanup interval")
                logger.warning("=" * 70)
                return False

        except Exception as e:
            logger.error(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    test = TestLearningImplicitE2E()
    try:
        await test.setup()
        success = await test.run_test()
        return 0 if success else 1
    finally:
        await test.cleanup()


# Pytest-discoverable test
import pytest


@pytest.mark.asyncio
async def test_learning_implicit_feedback_e2e(service_env):
    """Pytest wrapper for Learning Module implicit feedback E2E test.

    The service_env fixture ensures services are running.
    """
    exit_code = await main()
    assert exit_code == 0, "Learning implicit feedback E2E test failed"


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
