"""Integration test for LLM response flow.

Tests the full path: UI -> Orchestrator -> Executive -> Ollama -> back
This validates that response_text makes it all the way through.
"""

import os
import sys
from pathlib import Path

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "executive"))

import grpc

try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    # Mock pytest.fixture for standalone mode
    class pytest:
        @staticmethod
        def fixture(func):
            return func

from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc
from gladys_orchestrator.generated import executive_pb2, executive_pb2_grpc
from gladys_orchestrator.generated import common_pb2


@pytest.fixture
def orchestrator_stub():
    """Connect to local orchestrator."""
    channel = grpc.insecure_channel("localhost:50050")
    return orchestrator_pb2_grpc.OrchestratorServiceStub(channel)


@pytest.fixture
def executive_stub():
    """Connect to local executive."""
    channel = grpc.insecure_channel("localhost:50053")
    return executive_pb2_grpc.ExecutiveServiceStub(channel)


class TestExecutiveDirect:
    """Test Executive service directly (bypass Orchestrator)."""

    def test_executive_returns_response_text(self, executive_stub):
        """Executive should return non-empty response_text when Ollama is configured."""
        event = common_pb2.Event(
            id="test-direct-001",
                        source="test",
            raw_text="Meeting with Bob in 15 minutes",
        )
        request = executive_pb2.ProcessEventRequest(
            event=event,
            immediate=True,
        )

        response = executive_stub.ProcessEvent(request, timeout=30)

        print(f"\n=== Executive Direct Response ===")
        print(f"accepted: {response.accepted}")
        print(f"error_message: {response.error_message!r}")
        print(f"response_id: {response.response_id!r}")
        print(f"response_text: {response.response_text!r}")
        print(f"routed_to_llm: {response.routed_to_llm}")

        # This is the critical assertion
        assert response.response_text, "Executive should return non-empty response_text"
        assert response.accepted, "Executive should accept the event"


class TestOrchestratorFlow:
    """Test full flow through Orchestrator."""

    def test_orchestrator_returns_response_text(self, orchestrator_stub):
        """Orchestrator should pass through response_text from Executive."""
        event = common_pb2.Event(
            id="test-orch-001",
            source="test",
            raw_text="Meeting with Bob in 15 minutes",
        )
        # Force high salience to skip accumulator
        event.salience.novelty = 0.9

        def event_generator():
            yield event

        # Get the acknowledgment
        acks = list(orchestrator_stub.PublishEvents(event_generator(), timeout=30))

        assert len(acks) == 1, "Should get exactly one acknowledgment"
        ack = acks[0]

        print(f"\n=== Orchestrator Response ===")
        print(f"event_id: {ack.event_id!r}")
        print(f"response_id: {ack.response_id!r}")
        print(f"response_text: {ack.response_text!r}")
        print(f"matched_heuristic_id: {ack.matched_heuristic_id!r}")
        print(f"routed_to_llm: {ack.routed_to_llm}")

        # The key test - response_text should not be empty
        if ack.matched_heuristic_id:
            print("Note: Event matched a heuristic, response_text may be empty")
        elif ack.routed_to_llm:
            assert ack.response_text, "When routed_to_llm=True, response_text should not be empty"
        else:
            print("Warning: Event was neither matched nor routed to LLM")


if __name__ == "__main__":
    # Test 1: Executive directly
    print("=" * 60)
    print("Test 1: Executive directly")
    print("=" * 60)
    exec_channel = grpc.insecure_channel("localhost:50053")
    exec_stub = executive_pb2_grpc.ExecutiveServiceStub(exec_channel)

    event = common_pb2.Event(
        id="test-direct-001",
        source="test",
        raw_text="Meeting with Bob in 15 minutes",
    )
    request = executive_pb2.ProcessEventRequest(
        event=event,
        immediate=True,
    )

    try:
        response = exec_stub.ProcessEvent(request, timeout=30)
        print(f"accepted: {response.accepted}")
        print(f"error_message: {response.error_message!r}")
        print(f"response_id: {response.response_id!r}")
        print(f"response_text: {response.response_text!r}")
        print(f"routed_to_llm: {response.routed_to_llm}")

        if not response.response_text:
            print("\n*** PROBLEM: Executive returned empty response_text ***")
        else:
            print("\n*** SUCCESS: Executive returned response_text ***")
    except Exception as e:
        print(f"Error calling Executive: {e}")

    # Test 2: Through Orchestrator
    print("\n" + "=" * 60)
    print("Test 2: Through Orchestrator")
    print("=" * 60)
    orch_channel = grpc.insecure_channel("localhost:50050")
    orch_stub = orchestrator_pb2_grpc.OrchestratorServiceStub(orch_channel)

    event = common_pb2.Event(
        id="test-orch-001",
        source="test",
        raw_text="Meeting with Bob in 15 minutes",
    )
    # Force high salience to skip accumulator
    event.salience.novelty = 0.9

    def event_generator():
        yield event

    try:
        acks = list(orch_stub.PublishEvents(event_generator(), timeout=30))
        if not acks:
            print("*** PROBLEM: No acks returned from Orchestrator ***")
        else:
            ack = acks[0]
            print(f"event_id: {ack.event_id!r}")
            print(f"response_id: {ack.response_id!r}")
            print(f"response_text: {ack.response_text!r}")
            print(f"matched_heuristic_id: {ack.matched_heuristic_id!r}")
            print(f"routed_to_llm: {ack.routed_to_llm}")

            if not ack.response_text and ack.routed_to_llm:
                print("\n*** PROBLEM: Orchestrator returned empty response_text despite routed_to_llm=True ***")
            elif ack.response_text:
                print("\n*** SUCCESS: Orchestrator returned response_text ***")
            else:
                print("\n*** INFO: No response_text (may have matched heuristic or accumulated) ***")
    except Exception as e:
        print(f"Error calling Orchestrator: {e}")
