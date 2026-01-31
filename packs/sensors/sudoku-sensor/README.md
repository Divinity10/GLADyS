# Sudoku Sensor

A GLADyS sensor for [WebSudoku](https://www.websudoku.com).

## Overview
Captures game state from the browser via a userscript driver and streams events to the GLADyS orchestrator.
- **Source ID**: `sudoku-sensor`
- **Port**: `8701` (HTTP for driver), `50050` (gRPC to Orchestrator)

## Components
- `sensor.py`: Python process that receives HTTP POSTs from the driver and talks gRPC to GLADyS.
- `driver.js`: Tampermonkey userscript that scrapes the WebSudoku page.

## Setup

1. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Driver**:
   - Install the [Tampermonkey](https://www.tampermonkey.net/) browser extension.
   - Create a new script and paste the content of `driver.js`.
   - Reload WebSudoku.

## Usage

### Live Mode
Run the sensor and play WebSudoku:
```bash
python sensor.py
```

### Mock Mode
Test without the browser driver using a recorded game sequence:
```bash
python sensor.py --mock
```

### Dry Run
Print events to console without connecting to the Orchestrator:
```bash
python sensor.py --mock --dry-run
```
