#!/usr/bin/env python3
"""Integration Test: Heuristic Flight Recorder (Phase 3).

Validates that heuristic fires are persisted and outcomes are updated:
1. Store a heuristic.
2. Trigger it via Orchestrator (Fast Path).
3. Verify record exists in heuristic_fires table with outcome='unknown'.
4. Send feedback via UpdateHeuristicConfidence.
5. Verify record outcome is updated to 'success'.

Usage:
    python scripts/docker.py test test_flight_recorder.py  # DOCKER
"""

import asyncio
import os
import sys
import uuid
import time
from pathlib import Path

import grpc

# Add paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "orchestrator"))
# Force local memory package to be first in path
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "memory"))

try:
    # Try importing directly from source location
    from gladys_memory import memory_pb2, memory_pb2_grpc
except ImportError:
    try:
        from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc
        from gladys_orchestrator.generated import memory_pb2, memory_pb2_grpc
        from gladys_orchestrator.generated import common_pb2
    except ImportError:
        print("ERROR: Proto stubs not found. Run 'python scripts/proto_sync.py'")
        sys.exit(1)

# Configuration
ORCHESTRATOR_ADDR = os.environ.get("ORCHESTRATOR_ADDRESS", "localhost:50060")
PYTHON_ADDR = os.environ.get("PYTHON_ADDRESS", "localhost:50061")

async def run_test():
    print("=" * 70)
    print("FLIGHT RECORDER TEST: Heuristic fire tracking and outcome linkage")
    print("=" * 70)

    # 1. Connect to services
    try:
        orch_channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDR)
        mem_channel = grpc.aio.insecure_channel(PYTHON_ADDR)
        
        orch_stub = orchestrator_pb2_grpc.OrchestratorServiceStub(orch_channel)
        mem_stub = memory_pb2_grpc.MemoryStorageStub(mem_channel)
        
        await asyncio.wait_for(orch_channel.channel_ready(), timeout=3.0)
        await asyncio.wait_for(mem_channel.channel_ready(), timeout=3.0)
    except Exception as e:
        print(f"ERROR: Connection failed: {e}")
        return False

    async with orch_channel, mem_channel:
        # 2. Store Heuristic
        print("\n[Step 1] Storing test heuristic...")
        h_id = str(uuid.uuid4())
        h_name = f"Flight Recorder Test {h_id[:8]}"
        
        await mem_stub.StoreHeuristic(memory_pb2.StoreHeuristicRequest(
            heuristic=memory_pb2.Heuristic(
                id=h_id,
                name=h_name,
                condition_text="flight recorder test trigger",
                effects_json='{"action": "test"}',
                confidence=0.9,
                origin="test"
            ),
            generate_embedding=True
        ))
        
        # 3. Trigger Fire via Orchestrator
        print("\n[Step 2] Triggering heuristic fire via Orchestrator...")
        event_id = str(uuid.uuid4())  # Must be valid UUID for memory service
        
        event = common_pb2.Event(
            id=event_id,
            source="test",
            raw_text="flight recorder test trigger"
        )
        response = await orch_stub.PublishEvent(orchestrator_pb2.PublishEventRequest(event=event))
        ack = response.ack
            
        if not ack or ack.matched_heuristic_id != h_id:
            print(f"FAILED: Heuristic did not match. Matched: {ack.matched_heuristic_id if ack else 'None'}")
            return False
            
        print(f"  Match confirmed: {ack.matched_heuristic_id}")
        
        # 4. Verify record creation
        print("\n[Step 3] Verifying fire record creation...")
        # Give it a moment for async recording task to finish
        await asyncio.sleep(1.0)
        
        resp = await mem_stub.GetPendingFires(memory_pb2.GetPendingFiresRequest(
            heuristic_id=h_id
        ))
        
        fire_record = None
        for f in resp.fires:
            if f.event_id == event_id:
                fire_record = f
                break
                
        if not fire_record:
            print("FAILED: No fire record found for this event")
            return False
            
        print(f"  Fire record found: {fire_record.id}")
        print(f"  Outcome: {fire_record.outcome}")
        
        if fire_record.outcome != "unknown":
            print(f"FAILED: Expected outcome 'unknown', got '{fire_record.outcome}'")
            return False
            
        # 5. Send feedback and verify update
        print("\n[Step 4] Sending positive feedback...")
        conf_resp = await mem_stub.UpdateHeuristicConfidence(memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=h_id,
            positive=True
        ))
        
        if not conf_resp.success:
            print("FAILED: UpdateHeuristicConfidence failed")
            return False
            
        print("\n[Step 5] Verifying outcome update...")
        # Get fires again (should no longer be pending if outcome changed)
        # We query by heuristic ID and age to find it
        all_fires_resp = await mem_stub.GetPendingFires(memory_pb2.GetPendingFiresRequest(
            heuristic_id=h_id,
            max_age_seconds=60
        ))
        
        # If it's not in pending, it means outcome changed. 
        # For full verification we'd need a GetFire RPC, but we can verify it's NOT in pending anymore
        # and then do a direct SQL check if we really wanted to.
        # But we can also check if any fires exist for this H but with outcome 'success'
        # Wait, I didn't add a 'GetAllFires' RPC. I'll add a SQL check via subprocess.
        
        # Robust verification: It should be removed from 'unknown' list
        still_pending = any(f.event_id == event_id for f in all_fires_resp.fires)
        if still_pending:
            print("FAILED: Record still marked as 'unknown' after feedback")
            return False
            
        # SQL Check for the win
        from subprocess import run
        sql = f"SELECT outcome, feedback_source FROM heuristic_fires WHERE event_id = '{event_id}'"
        docker_script = str(PROJECT_ROOT / "scripts" / "docker.py")
        db_check = run(["python", docker_script, "query", sql], capture_output=True, text=True)
        print(f"  DB Check:\n{db_check.stdout}")
        
        if "success" in db_check.stdout and "explicit" in db_check.stdout:
            print("  Verified: Outcome is 'success', Source is 'explicit'")
        else:
            print("FAILED: DB state mismatch")
            return False

    print("\n" + "=" * 70)
    print("SUCCESS: Flight Recorder works!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
