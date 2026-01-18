# Open Design Questions

This file tracks active architectural discussions that haven't yet crystallized into ADRs. It's shared between collaborators.

**Last updated**: 2026-01-18

---

## 1. Actuator/Effector Subsystem Gap

**Status**: Identified, needs ADR
**Priority**: High
**Proposed**: ADR-0010

### Problem

The architecture shows sensors (input) flowing to Executive which produces speech (TTS output). But GLADyS should also control physical devices:
- Thermostats
- Fans / HVAC
- Humidifiers / dehumidifiers
- Smart lights
- Door locks (high security concern)

**Gap**: No actuator plugin type exists. Skills provide knowledge to Executive, not device control.

### Open Questions

- Should actuators be a new plugin type or an extension of skills?
- What's the command validation / safety bounds model?
- Rate limiting to prevent oscillation (don't toggle thermostat 100x/minute)?
- Confirmation requirements for high-impact actions (door locks)?
- How does the Executive "decide" to actuate vs. speak?

### Possible Approaches

1. **Actuators as new plugin type** - Parallel to sensors and skills, with own manifest schema
2. **Actuators as skill extension** - Skills gain "execute" capability alongside "query"
3. **Actuators via external integration** - Home Assistant / MQTT bridge, not native plugins

---

## 2. Continuous vs. Discrete Data

**Status**: Identified, needs resolution
**Priority**: Medium

### Problem

Salience gateway and memory are designed for **discrete events** ("player took damage"). Environmental sensors produce **continuous streams** (temperature every 5 seconds).

### Open Questions

- Does a temperature reading have "salience"?
- Should 72°F → 73°F enter salience evaluation at all?
- How does episodic memory model time-series data?
- Should continuous data be pre-filtered into discrete events at the sensor?

### Possible Approaches

1. **Sensor-side filtering** - Sensors emit events only on threshold crossings (sensor responsibility)
2. **New data type** - "Metric" type that bypasses salience, goes directly to memory/executive
3. **Salience learns** - Gateway learns to filter low-information continuous data (ML approach)
4. **Hybrid** - Continuous data stored separately, but threshold events enter salience pipeline

---

## 3. Tiered Actuator Security

**Status**: Identified, needs analysis
**Priority**: High (if actuators proceed)

### Problem

ADR-0008 security model is good for data privacy, but physical actuators have different risk profiles:

| Plugin Type | Risk if Compromised |
|-------------|---------------------|
| Game sensor | Annoyance |
| Screen capture | Privacy violation |
| Thermostat | Comfort / pipe freeze |
| Door lock | Physical security breach |

### Open Questions

- Should physical security actuators (locks, garage doors) require higher trust than entertainment plugins?
- Should there be an "actuator trust tier" separate from sensor trust?
- What confirmation UX for dangerous actions?

---

## 4. Latency Budget Diversity

**Status**: Identified, minor concern
**Priority**: Low

### Problem

ADR-0005 defines 1000ms end-to-end budget optimized for conversational gaming. IoT has different needs:
- Safety-critical (smoke alarm): <100ms
- Comfort (thermostat): Can be slow, SHOULD be slow to avoid oscillation

### Open Questions

- Should different event types have different latency budgets?
- How to express this in the architecture without over-engineering?

---

## Recently Resolved

*None yet*

---

## How to Use This File

1. Add new questions when architectural gaps are identified
2. Update status as discussions progress
3. Move to "Recently Resolved" when an ADR is created or decision is made
4. Reference ADR number when resolved
