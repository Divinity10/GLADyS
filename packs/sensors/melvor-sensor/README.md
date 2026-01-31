# Melvor Idle Sensor

A GLADyS sensor for [Melvor Idle](https://melvoridle.com).

## Overview
Monitors game events (combat, skilling, drops) via a userscript driver and streams them to the GLADyS orchestrator.
- **Source ID**: `melvor-sensor`
- **Port**: `8702` (HTTP for driver), `50050` (gRPC to Orchestrator)

## Components
- `sensor.py`: Python process that receives HTTP POSTs from the driver and talks gRPC to GLADyS.
- `driver.js`: Tampermonkey userscript that hooks into the Melvor Idle game engine.

## Setup

1. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Driver**:
   - Install the [Tampermonkey](https://www.tampermonkey.net/) browser extension.
   - Create a new script and paste the content of `driver.js`.
   - Reload Melvor Idle.

## Usage

### Live Mode
Run the sensor and play Melvor Idle in the browser:
```bash
python sensor.py
```

### Mock Mode
Test without the browser driver using a recorded session:
```bash
python sensor.py --mock
```

### Dry Run
Print events to console without connecting to the Orchestrator:
```bash
python sensor.py --mock --dry-run
```
