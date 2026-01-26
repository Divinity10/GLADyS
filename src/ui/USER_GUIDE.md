# GLADyS Lab Bench: User Guide

Welcome to the **GLADyS Lab Bench**. This dashboard is designed for rapid evaluation and debugging of the GLADyS learning loop (System 2 → System 1 handoff).

---

## Quick Start

1. **Start Services**:
   ```bash
   python scripts/docker.py start all   # Docker
   # or
   python scripts/local.py start all    # Local
   ```
2. **Launch the Dashboard**:
   ```bash
   cd src/ui
   uv run streamlit run dashboard.py
   ```
3. **Access**: Open `http://localhost:8501` in your browser.

---

## Sidebar Controls

### Environment Switcher
Toggle between **Docker** and **Local** services. The dashboard auto-reconnects to the appropriate ports when you switch.

| Environment | Orchestrator | Memory (Py) | Memory (Rust) | Executive | DB Port |
|-------------|--------------|-------------|---------------|-----------|---------|
| Docker      | 50060        | 50061       | 50062         | 50063     | 5433    |
| Local       | 50050        | 50051       | 50052         | 50053     | 5432    |

### Service Health
Real-time gRPC health status for all services. Green = healthy, red = unreachable.

### Testing Tools
- **Refresh Dashboard**: Clears cache and reloads all data.
- **Auto-refresh**: Polls for new data every 2 seconds.
- **Clear Local History**: Wipes the response stream list (browser session only).
- **Flush Accumulator**: Manually triggers the Orchestrator to process buffered low-salience events.

### Service Controls
Expand to manage services directly from the UI:
- **Start/Restart**: No confirmation needed
- **Stop individual**: Executes immediately
- **Stop ALL**: Requires confirmation
- **Run Migrations**: Apply database schema updates
- **Clean Database**: Clear heuristics, events, or all data (requires confirmation)

---

## Tab 1: Laboratory

The Laboratory is divided into two columns.

### Left Column: Interaction Lab

**Event Simulator**
- **Presets**: Quick-load scenarios like "Oven Timer" or "Creeper Attack"
- **Source Mode**: Select a domain (`minecraft`, `smart_home`) or type custom
- **Salience Override**:
  - *Let system evaluate*: Normal flow through Salience Gateway
  - *Force HIGH*: Route directly to LLM (immediate response)
  - *Force LOW*: Put in accumulator buffer
- **Feedback Buttons**: After GLADyS responds, use **Good** / **Bad** to reinforce or penalize the matched heuristic

**Response History**
Shows the live stream of responses as they arrive, including latency tracking.

### Right Column: Memory Console

**Similarity Probe**
Type text to see which heuristics would match and their similarity scores *without* sending a real event. Useful for debugging over-generalization.

**Manual Inject**
Directly store a heuristic in the database with custom condition/action/confidence.

---

## Tab 2: Event Log

Shows recent system activity from the database. Verify that events are persisted correctly with their metadata (Response IDs, Predictions, Salience scores).

---

## Tab 3: Cache

**Cache Inspector** for the Rust salience gateway LRU cache.

- **Stats**: Hit/miss counts, hit rate, cache size
- **Cache Contents**: View cached heuristics with their scores
- **Management**: Flush entire cache or evict individual entries

---

## Tab 4: Flight Recorder

Debug view for heuristic fire/outcome tracking.

- **Heuristic Fires**: When heuristics triggered and what events caused them
- **Pending Outcomes**: Expectations waiting for implicit feedback
- **Recent Outcomes**: Resolved feedback events

---

## Learned Knowledge Base

The full-width table at the bottom shows all learned heuristics:
- **Confidence**: Color-coded (red < 0.3, orange < 0.7, green >= 0.7)
- **Fire/Success counts**: Usage statistics
- **Origin**: How the heuristic was created (llm, manual, etc.)
- **Frozen**: Whether the heuristic is locked from updates

---

## The Learning Loop Test

1. Send a novel event (e.g., `[work] Mike sent a funny GIF`)
2. See the LLM response and click **Good**
3. Observe the new rule appear in the **Knowledge Base**
4. Send the *exact same event* again
5. Watch the result show **Fast Path (Heuristic Match)** — nearly instant!
