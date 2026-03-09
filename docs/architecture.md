# Architecture

## Goal

Maintain one canonical scene graph metamodel and instance model derived from CARLA, then continuously update it from CARLA data streams and evaluate incremental graph patterns using VIATRA.

## Pipeline

1. CARLA runtime produces world snapshots and event streams.
2. Scene graph generator maps CARLA entities to EMF model instances.
3. Stream updater applies incremental model transformations.
4. VIATRA Query engine maintains incremental pattern matches.
5. Transformation layer produces derived views, warnings, and control signals.

## Core Components

- `carla_adapter`:
  - Reads CARLA Python API snapshots/events.
  - Maps CARLA IDs to stable EMF element IDs.
- `scenegraph_model`:
  - One metamodel (`SceneGraph.ecore`).
  - Runtime model instances (`.xmi`) synchronized with CARLA.
- `stream_transformations`:
  - Update rules for create/update/delete of nodes and edges.
- `query_layer`:
  - VIATRA patterns for hazard, proximity, and topology conditions.
- `integration_api`:
  - Exposes query match deltas to downstream analytics/control modules.
  - Uses `events.jsonl` from stream bridge as incremental update contract.

## Data Contracts

- Input event schema (example):
  - `timestamp`
  - `entityId`
  - `entityType`
  - `pose` (`x`, `y`, `z`, `yaw`, `pitch`, `roll`)
  - `velocity`
  - `acceleration`
  - `laneId` (optional)
- Model update granularity:
  - Prefer per-event updates to keep query engine incremental.

## Initial Query Use Cases

- Vehicle-vehicle distance below threshold.
- Ego vehicle close to pedestrian crossing.
- Static obstacle on current lane ahead.
- Disconnected road topology fragments in loaded map.

## Tooling Split

- CARLA build/run and extraction: Windows command line + Python.
- Modeling and query runtime: Eclipse + VIATRA.
- Exchange format: EMF XMI or in-memory EMF model via JVM/Python bridge.
- Runtime stream artifacts: `data/stream/latest_snapshot.xmi`, `data/stream/events.jsonl`, `data/stream/live_view.html`.
