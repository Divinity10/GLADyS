# GLADyS Evaluation Dashboard

A Streamlit dashboard to visualize and control the GLADyS learning loop.

## Features

### Monitoring
- **Service Health Panel**: Real-time gRPC health status of all services
- **Recent Events**: View incoming events and how they were processed (LLM vs Cache)
- **Prediction Visualization**: See the LLM's `predicted_success` and `prediction_confidence`
- **Heuristics Monitor**: Track learned rules and their confidence scores
- **Cache Inspector**: View Rust salience gateway cache stats and contents
- **Flight Recorder**: Track heuristic fires and outcomes for debugging

### Service Controls
- **Start/Stop/Restart**: Manage individual services or all at once
- **Run Migrations**: Apply database schema updates
- **Clean Database**: Clear heuristics, events, or all data (with confirmation)
- Supports both Docker and Local environments

## Prerequisites
- Python 3.11+
- Services running (Docker or Local)

## Setup

1. **Install Dependencies** (using `uv` is recommended):
   ```bash
   cd src/ui
   uv pip install -r pyproject.toml
   ```

## Running the Dashboard

Start services first (from project root):
```bash
# Docker
python scripts/docker.py start

# Or Local
python scripts/local.py start
```

Run the dashboard:
```bash
cd src/ui
uv run streamlit run dashboard.py
```

The dashboard opens at `http://localhost:8501`.

## Environment Switching

Use the **Environment** radio button in the sidebar to switch between Docker and Local services. The dashboard auto-reconnects to the appropriate ports.

| Environment | Orchestrator | Memory Python | Memory Rust | Executive | DB Port |
|-------------|--------------|---------------|-------------|-----------|---------|
| Docker      | 50060        | 50061         | 50062       | 50063     | 5433    |
| Local       | 50050        | 50051         | 50052       | 50053     | 5432    |

## Service Controls

Expand the **Service Controls** section in the sidebar to:

- **Restart/Start**: No confirmation needed
- **Stop individual**: Executes immediately
- **Stop all**: Requires confirmation
- **Run Migrations**: Applies pending database migrations
- **Clean Database**: Requires confirmation (destructive)

The last command output is shown in a collapsible section for debugging.
