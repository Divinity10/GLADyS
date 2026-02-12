# Data Types Questions

Handling continuous vs discrete data, streaming sensors, and time-series data.

**Last updated**: 2026-01-25

---

## Open Questions

### Q: Continuous vs Discrete Data (§2)

**Status**: Open
**Priority**: Medium

#### Problem

Salience gateway and memory are designed for **discrete events** ("player took damage"). Environmental sensors produce **continuous streams** (temperature every 5 seconds).

#### Key Questions

- Does a temperature reading have "salience"?
- Should 72°F → 73°F enter salience evaluation at all?
- How does episodic memory model time-series data?
- Should continuous data be pre-filtered into discrete events at the sensor?

#### Possible Approaches

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **Sensor-side filtering** | Sensors emit events only on threshold crossings | Simplest; sensor responsibility | Loses granular data |
| **New data type** | "Metric" type that bypasses salience, goes directly to memory/executive | Clean separation | Two code paths |
| **Salience learns** | Gateway learns to filter low-information continuous data | Adaptive | Complex ML |
| **Hybrid** | Continuous data stored separately, threshold events enter salience | Best of both | More complexity |

#### Discussion

**Temperature example**:
- Raw: 72°F, 72°F, 72°F, 73°F, 73°F, 73°F, 74°F...
- Threshold event: "Temperature crossed 74°F threshold"

The threshold event has clear salience. The raw readings are just noise for most purposes.

**However**, some use cases need the raw data:
- "What was the temperature trend over the last hour?" (needs history)
- "Is the AC cycling too frequently?" (needs fine-grained data)

#### Data Structure Readiness

**Question**: Do we have the right data structures? When is the right time to define them?

The current schema (`episodic_events`, `heuristics`, `heuristic_fires`) emerged from Phase needs. As sensors, actuators, and multi-user support arrive, the schema will need to evolve. Key tensions:
- Define early → risk premature abstraction
- Define late → risk expensive migrations
- Current pragmatic approach: add columns as needed, defer new tables until a concrete use case requires them

#### Related ADRs

- **ADR-0009**: Compaction policy - continuous data might compact differently
- **ADR-0013**: Salience - how does novelty detection work for metrics?

#### Potential Resolution

Consider a two-path model:
1. **Events** → Salience → Episodic Memory (standard path)
2. **Metrics** → Time-Series Storage → Query on demand (new path)

Sensors declare their output type in manifest:
```yaml
outputs:
  - name: temperature
    type: metric
    unit: fahrenheit
    sample_rate: 5s
  - name: temperature_alert
    type: event
    triggers:
      - threshold_crossing
      - rate_of_change
```

This is architectural - needs ADR if we proceed.

---

## Reference: Related Use Cases

### UC5: Continuous Monitoring

```
[Temp Sensor every 5s] → ??? → Memory (time-series) → Executive (on query)
```

**Problem**: Does every reading go through salience? (No)

**Solution options**:
1. Sensor emits only on threshold crossing
2. Separate "metric" path that bypasses salience
3. Preprocessor filters to significant changes

