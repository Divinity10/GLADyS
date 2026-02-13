# Sensor Exploration: Runescape

**Status**: Not started
**Owner**: Mike
**Purpose**: Phase 1 W1 — build one real sensor that produces events without human intervention
**Reference**: [ITERATIVE_DESIGN.md](../design/ITERATIVE_DESIGN.md) (Phase 1, W1)

---

## Goal

Build a working Runescape sensor that emits real game events into the GLADyS pipeline. This is exploratory — discover what's possible, what's hard, and what event variety Runescape provides.

## Architecture: Sensor + Driver

Follows the printer model:

- **Driver**: Knows Runescape. Connects to the game, reads state, produces raw domain events. Reusable outside GLADyS.
- **Sensor**: Knows GLADyS. Bridges the driver to the Orchestrator — translates driver output into standard event format, handles gRPC delivery. Reusable across drivers.

Don't formalize the sensor/driver interface boundary yet. Build them together and let the natural seam emerge.

## Constraints

These are non-negotiable for Phase 1 integration:

1. **Events go through gRPC**: Call `PublishEvents` on the Orchestrator. No direct database writes.
2. **Event format**: Each event needs `source` (domain identifier, e.g. "runescape"), `event_type`, `payload`, `timestamp`
3. **Autonomous**: Must produce events without human triggering. Polling, log tailing, or event subscription — your call.
4. **Pack structure**: Lives in `packs/runescape/sensors/` with a `manifest.yaml` (see [INTERFACES.md](../design/INTERFACES.md) for manifest format)

## Open — Mike's Call

- How to connect to Runescape (API, log files, screen reading, memory reading, RuneLite plugin)
- What events are interesting (combat, leveling, trade, chat, location changes, deaths, loot)
- Polling interval / event granularity
- Whether the driver does preprocessing or emits raw state
- Language choice for the driver (Python is easiest for gRPC integration, but whatever works)

## Document As You Go

These questions help inform the sensor abstraction and Phase 1 planning:

- What events does Runescape actually expose? What's easy vs hard to get?
- How much event variety do you get from normal gameplay?
- What's the natural event rate? (Bursty during combat? Sparse while skilling?)
- What surprised you about the integration?

## Done When

- Sensor runs alongside a Runescape session and emits events to the Orchestrator
- Events appear in the dashboard event table
- At least 3 distinct event types are emitted
- Notes on what worked, what was hard, and what events are available
