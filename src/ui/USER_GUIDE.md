# GLADyS Lab Bench: User Guide

Welcome to the **GLADyS Lab Bench**. This dashboard is designed for rapid evaluation and setup of the GLADyS learning loop (System 2 → System 1 handoff).

---

## 🚀 Quick Start

1. **Ensure Services are Running**:
   ```bash
   python scripts/docker.py start all
   ```
2. **Launch the Dashboard**:
   ```bash
   cd src/ui
   uv run streamlit run dashboard.py
   ```
3. **Access**: Open `http://localhost:8501` in your browser.

---

## 🔬 Tab 1: Laboratory

The Laboratory is divided into two columns: **Interaction Lab** (Stimulus) and **Memory Console** (State Control).

### 1. Interaction Lab (Event Simulator)
Use this to simulate real-world events and observe the system's reaction.

- **Presets**: Quick-load common scenarios like "Oven Timer" or "Creeper Attack."
- **Source Mode**: 
    - **Preset**: Select from known domains (`minecraft`, `smart_home`, etc.).
    - **Custom**: Type a new source (e.g., `email`, `security_cam`).
- **Salience Override**:
    - **Let system evaluate**: Naturally triggers Salience Gateway scoring.
    - **Force HIGH (Immediate)**: Skips scoring; routes directly to LLM for immediate response.
    - **Force LOW (Accumulated)**: Skips scoring; puts event into the moment buffer (Accumulator).
- **Feedback Loop**: Once GLADyS responds, use the **👍 Good** / **👎 Bad** buttons.
    - **👍 Good**: Creates a new heuristic or boosts confidence of the matched one.
    - **👎 Bad**: Decreases confidence of the matched heuristic.

### 2. Memory Console
Use this to setup or debug the system's knowledge state.

- **Similarity Probe**: Type text to see which heuristics match and their scores *without* triggering a real event. Perfect for debugging "over-generalization."
- **Manual Inject**: Directly store a heuristic in the database.
    - **Tip**: Use domain prefixes in the condition (e.g., `work: email from Mike`) to ensure semantic separation.

---

## 📜 Tab 2: Event Log

This tab shows the **Recent System Activity** as stored in the database. It is useful for verifying that events are being persisted correctly with their metadata (Response IDs and Predictions).

---

## 📊 System Metrics & Knowledge Base

- **System Performance**: Real-time stats showing Total Events, Active Heuristics, and the Estimated Cache Hit Rate.
- **Live Response Stream**: Displays asynchronous responses (e.g., from the Accumulator) as they arrive via gRPC stream. Includes latency tracking.
- **Learned Knowledge Base**: A full-width table at the bottom showing all learned rules, their confidence (color-coded), and usage stats.

---

## 🚽 Management Tools (Sidebar)

- **🔄 Refresh Dashboard**: Clears cache and reloads all data.
- **Auto-refresh**: Polls for new data every 2 seconds.
- **🚽 Flush Accumulator**: Manually triggers the Orchestrator to process all events currently waiting in the moment buffer.
- **🗑️ Clear Local History**: Wipes the "Live Response Stream" list (browser session only).

---

## 💡 Pro-Tip: The "Learning Loop" Test
1. Send a novel event (e.g., `[work] Mike sent a funny GIF`).
2. See the LLM response and click **👍 Good**.
3. Observe the new rule appear in the **Knowledge Base** at the bottom.
4. Send the *exact same event* again.
5. Watch the **Latest Result** area: It should show **⚡ Fast Path (Heuristic Match)** and be nearly instant!
