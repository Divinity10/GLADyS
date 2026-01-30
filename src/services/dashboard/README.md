# GLADyS Dashboard V2

This is the V2 Dashboard for GLADyS, built with FastAPI, htmx, and Alpine.js.
It replaces the previous Streamlit-based dashboard.

## Design

For full design details and features, see [DASHBOARD_V2.md](../../docs/design/DASHBOARD_V2.md).

## Running

The dashboard is managed via the `tools/dashboard/dashboard.py` script.

```bash
# Start
python tools/dashboard/dashboard.py start

# Stop
python tools/dashboard/dashboard.py stop

# Restart
python tools/dashboard/dashboard.py restart
```

It runs on port **8502**.

## Structure

- `backend/`: FastAPI application (Python)
- `frontend/`: Static HTML/JS/CSS (served by FastAPI)
