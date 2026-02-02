# Sensor Dashboard & Control Plane

**Created**: 2026-02-01
**Status**: Design needed
**Related**: Sensor architecture (packs/sensors/)

## Problem

No dashboard visibility into sensor state. As sensor count grows, need ability to observe and control sensors during development and testing.

## Needs Identified

- **Observe**: Connected sensors, status (live/mock/disconnected), event counts, last-seen timestamps
- **Control**: Load/unload/reload sensors for testing
- **Test modes**: Run sensor in mock or live mode for evaluating driver-sensor functionality
- **Tracing**: Some level of event tracing through the sensor → orchestrator path

## Questions to Resolve

- Does the dashboard actively manage sensors (control plane) or just observe them?
- How do sensors register themselves? (Push registration on connect, or dashboard polls a known set?)
- What changes to the sensor → orchestrator gRPC path are needed to support status reporting?
- New dashboard tab vs extension of existing Lab tab?

## Scope

Dedicated design session needed before implementation.
