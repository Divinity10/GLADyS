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

## Known Limitations

### Driver Coverage

The current driver implementation has varying levels of support for game events:

- **Fully Supported (Live)**:
  - `combat_started`: Correctly detects and reports when a new fight begins.
  - `combat_died`: Correctly detects and reports player death.

- **Partially Supported (Live)**:
  - `combat_killed`: Detects when an enemy dies, but loot data is currently a placeholder (empty list) as loot extraction requires more complex hooking of the drop system.

- **Mock Only (Not yet implemented in driver)**:
  - `level_up`
  - `skill_started`
  - `skill_milestone`
  - `shop_purchase`
  - `item_equipped`

### Reliability

- The driver relies on polling `window.game` state every 1s. Rapid events occurring between polls may be missed.
- Requires the Melvor Idle browser tab to be active for the userscript to process updates reliably.
