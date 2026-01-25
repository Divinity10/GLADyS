# UI Dashboard Fixes

The Lab Bench UI at `src/ui/dashboard.py` needs one change:
- Route events through Orchestrator instead of calling Executive directly

This enables heuristic matching AND fixes dashboard metrics (Orchestrator now handles event storage with full response data for fine-tuning).

## Route Through Orchestrator

The UI currently calls Executive directly, bypassing heuristic matching entirely. Fix this by routing through Orchestrator.

### Add Orchestrator Client

```python
ORCHESTRATOR_ADDR = os.environ.get("ORCHESTRATOR_ADDR", "localhost:50060")

def get_orchestrator_stub():
    channel = grpc.insecure_channel(ORCHESTRATOR_ADDR)
    return orchestrator_pb2_grpc.OrchestratorServiceStub(channel)
```

### Add Import

```python
from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc
```

### Replace Executive Call with Orchestrator

The Orchestrator uses a streaming RPC. Wrap single events like this:

```python
def send_event_to_orchestrator(event):
    """Send single event via streaming RPC, get response."""
    orch_stub = get_orchestrator_stub()

    def event_generator():
        yield event

    # Get first (only) response from stream
    for ack in orch_stub.PublishEvents(event_generator()):
        return ack
    return None
```

Then in `render_event_simulator()`, replace the Executive call:

```python
# OLD: Direct to Executive (bypasses heuristics)
# response = exec_stub.ProcessEvent(...)

# NEW: Through Orchestrator (enables heuristic matching + event storage)
with st.spinner("GLADyS is thinking..."):
    ack = send_event_to_orchestrator(event)

if ack and ack.accepted:
    st.session_state.last_event_id = event_id
    st.session_state.last_response_id = ack.response_id
    st.session_state.last_response_text = ack.response_text
    st.session_state.last_pred_success = ack.predicted_success
    st.session_state.last_pred_conf = ack.prediction_confidence
    st.success(f"**GLADyS**: {ack.response_text}")

    # Show routing info
    if ack.matched_heuristic_id:
        st.info(f"Fast path via heuristic: {ack.matched_heuristic_id}")
    elif ack.routed_to_llm:
        st.info("Routed to LLM (no heuristic match)")
else:
    error_msg = ack.error_message if ack else "No response from Orchestrator"
    st.error(f"Event rejected: {error_msg}")
```

### EventAck Fields Available

The Orchestrator's `EventAck` now includes all response data:

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string | The event ID |
| `accepted` | bool | Whether event was accepted |
| `error_message` | string | Error if not accepted |
| `response_id` | string | Executive's response ID |
| `response_text` | string | The actual response |
| `predicted_success` | float | LLM's prediction (0.0-1.0) |
| `prediction_confidence` | float | LLM's confidence (0.0-1.0) |
| `routed_to_llm` | bool | True if went to Executive |
| `matched_heuristic_id` | string | Heuristic ID if fast-path |

### Remove Event Storage Code

The Orchestrator now stores events automatically:
- HIGH salience events: stored immediately after Executive responds
- LOW salience events: batch-stored on moment tick

**Remove any existing event storage code from the UI** - it's now handled by Orchestrator.

The stored events include `response_text` for building fine-tuning datasets.

## Testing

After implementing:

1. Process an event through the UI
2. Check Orchestrator logs - should show event routing through Salience
3. Verify events are stored with response text:
   ```sql
   SELECT id, raw_text, response_text, predicted_success
   FROM episodic_events
   ORDER BY timestamp DESC LIMIT 5;
   ```
4. Confirm "Total Events" metric increments
5. If you have heuristics, test that matching works (Fast Path metric should reflect matches)

## What This Enables

With Orchestrator routing:
- Events go through Salience for scoring
- Heuristics can match incoming events
- "Fast Path" metric becomes meaningful
- We can evaluate if heuristics are firing correctly
- Events are automatically stored with full response data
- Fine-tuning datasets can be built from stored input/output pairs

## Notes

- Docker ports: Orchestrator=50060, Memory=50061, Executive=50063, DB=5433
- Heuristic storage via "Manual Inject" works correctly
- Feedback loop (thumbs up/down) works correctly
- Use `python scripts/docker.py psql` to access the database
