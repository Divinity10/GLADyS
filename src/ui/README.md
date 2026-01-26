# GLADyS Evaluation Dashboard

A minimal Streamlit dashboard to visualize the GLADyS learning loop (System 2 → System 1 handoff).

## Features
- **Recent Events**: View incoming events and how they were processed (LLM vs Cache).
- **Prediction Visualization**: See the LLM's `predicted_success` and `prediction_confidence` for each decision.
- **Heuristics Monitor**: Track learned rules and their confidence scores.
- **System Stats**: Cache hit rates and processing metrics.

## Prerequisites
- Docker services must be running (`src/integration/run.py start all`).
- Python 3.11+.

## Setup

1. **Install Dependencies** (using `uv` is recommended):
   ```bash
   cd src/ui
   uv pip install -r pyproject.toml
   # OR directly via streamlit run if using uv run
   ```

## Running the Dashboard

Ensure the Docker services are up first:
```bash
cd src/integration
python run.py start all
```

Run the dashboard from the `src/ui` directory:
```bash
cd src/ui
uv run streamlit run dashboard.py
```

The dashboard will open in your browser at `http://localhost:8501`.

## Configuration
The dashboard connects to the PostgreSQL database running in Docker.
Default settings (configured in `dashboard.py` via env vars):
- Host: `localhost`
- Port: `5433` (Docker mapped port)
- DB/User/Pass: `gladys`
