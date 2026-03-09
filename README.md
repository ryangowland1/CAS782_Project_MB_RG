# CAS782 Project: CARLA Scene Graph + VIATRA

Final project repository for CAS782 (Digital Twins), focused on a CARLA-driven scene graph pipeline with incremental graph query matching and model transformation using VIATRA.

---

## Quick Start

### Step 1: Read Prerequisites
Before starting, review all system requirements:

📄 **[PREREQUISITES.md](PREREQUISITES.md)** (5-10 minutes to read)
- System requirements (Windows 10/11, disk space, GPU)
- Required software (Git, Python 3.8+, Visual C++ Build Tools)
- One-time setup checklist
- Troubleshooting

### Step 2: Run One Setup Script
Once prerequisites are met, run the automated setup:

```powershell
.\SETUP.ps1
```


### Step 3: Follow Printed Instructions
The script will output detailed next steps, including:
- How to activate the virtual environment
- How to start the CARLA server
- How to run demos
- How to start the live scene graph stream
---

## Documentation Guide

Once setup is complete, explore these guides:

| Document | Purpose | When to Read |
|----------|---------|--------------|
| **[QUICKSTART.md](QUICKSTART.md)** | First-time usage workflows | After SETUP.ps1 completes |
| **[STREAM_REFERENCE.md](STREAM_REFERENCE.md)** | Live stream files & formats | Before loading into VIATRA |
| **[VIATRA_STREAM_GUIDE.md](VIATRA_STREAM_GUIDE.md)** | Eclipse + VIATRA integration | When setting up Eclipse |
| **[docs/architecture.md](docs/architecture.md)** | System design & data flow | For understanding architecture |
| **[docs/extractor_usage.md](docs/extractor_usage.md)** | Scene graph export details | For custom extraction |
| **[docs/viatra_stream_integration.md](docs/viatra_stream_integration.md)** | VIATRA consumption patterns | For advanced VIATRA usage |

---

## Repository Structure

**Setup & Documentation:**
- `PREREQUISITES.md` — System requirements & one-time setup
- `SETUP.ps1` — Automated environment setup (run once after clone)
- `QUICKSTART.md` — First-time usage guide
- `STREAM_REFERENCE.md` — Location of all stream outputs
- `VIATRA_STREAM_GUIDE.md` — Eclipse & VIATRA integration

**Source Code:**
- `src/carla_scenegraph_export.py` — Export CARLA state as XMI scene graphs
- `src/scenegraph_stream_bridge.py` — Continuous stream producer (XMI + JSONL)
- `src/scenario_live_moving.py` — Demo: vehicles with autopilot
- `src/demo_carla_client.py` — Demo: basic CARLA API usage
- `src/viatra_dummy_live_consumer.py` — Demo: consume live event stream

**Metamodel & Queries:**
- `queries/SceneGraph.ecore` — EMF metamodel (Vehicle, Pedestrian, Node, Edge)
- `queries/scenegraph.vql` — VIATRA query patterns (fastVehicle, connected, etc.)

**Scale Simulation & Utilities:**
- `scripts/bootstrap_windows.ps1` — Legacy prerequisite checker
- `scripts/start_carla_server.ps1` — Helper to launch CARLA
- `scripts/run_scenegraph_stream.ps1` — Start scene graph stream
- `scripts/dev_up.ps1` — One-command dev startup
- `scripts/open_live_view.ps1` — Open live graph visualization

**Data & Outputs:**
- `data/stream/snapshots/` — XMI scene graph snapshots (1700+ files per session)
- `data/stream/latest_snapshot.xmi` — Most recent snapshot (auto-synced)
- `data/stream/events.jsonl` — Incremental change events (JSONL format)
- `data/stream/live_view.html` — Auto-refresh browser visualization

---

## System Architecture

**Data Flow:**
```
CARLA Simulator → Scene Graph Export → XMI Snapshots + JSONL Events
                                              ↓
                                    VIATRA Query Engine
                                              ↓
                                      Query Results
```

**Components:**
- **Scene Source:** CARLA 0.9.16 simulation (vehicles, pedestrians, environment)
- **Extraction:** Python bridge collects positions, speeds, relationships
- **Format:** EMF XMI (W3C standard) + JSONL event stream (incremental updates)
- **Querying:** VIATRA incremental pattern matching on live XMI models
- **Metamodel:** Single unified `SceneGraph.ecore` (Vehicle, Pedestrian, Node, Edge, Scene)
---

## 💾 Stream Output Format

All outputs are written to `data/stream/` directory:

| File | Format | Purpose |
|------|--------|---------|
| `latest_snapshot.xmi` | XMI | Current world state (load into VIATRA) |
| `snapshots/snapshot_XXXXXX.xmi` | XMI | Historical snapshots (1700+ per session) |
| `events.jsonl` | JSONL | Incremental changes per tick (node/edge deltas) |
| `current_state.json` | JSON | Same as latest_snapshot.xmi but in JSON |
| `live_view.html` | HTML | Auto-refresh browser visualization |

**Example XMI Snapshot:**
```xml
<scenegraph:Scene xmlns:scenegraph="http://cas782/scenegraph" name="CARLA_Stream">
  <nodes xsi:type="scenegraph:Vehicle" id="26" x="-64.6" y="24.5" z="-0.01" speed="0.0" />
  <nodes xsi:type="scenegraph:Vehicle" id="32" x="120.3" y="28.6" z="0.13" speed="0.004" />
</scenegraph:Scene>
```

**Example JSONL Event:**
```json
{"timestamp": "2026-03-09T02:33:12.935688+00:00", "tick": 1, "snapshot": "data/stream/snapshots/snapshot_000001.xmi", "node_changes": {"added": [{"node_type": "Vehicle", "external_id": "26", "x": -64.6446, "y": 24.471, "z": -0.0075, "speed": 0.0}], "removed": [], "updated": []}}
```

---

## References & Links

**Project Documentation:**
- [PREREQUISITES.md](PREREQUISITES.md) — System setup requirements
- [SETUP.ps1](SETUP.ps1) — Automated installation script
- [QUICKSTART.md](QUICKSTART.md) — First-time usage guide
- [STREAM_REFERENCE.md](STREAM_REFERENCE.md) — Live stream files reference
- [VIATRA_STREAM_GUIDE.md](VIATRA_STREAM_GUIDE.md) — Eclipse integration walkthrough

**Detailed Technical Docs:**
- [docs/architecture.md](docs/architecture.md) — Full system architecture
- [docs/extractor_usage.md](docs/extractor_usage.md) — Scene extraction API
- [docs/viatra_stream_integration.md](docs/viatra_stream_integration.md) — VIATRA patterns & queries

**External Resources:**
- [CARLA 0.9.16 Docs](https://carla.readthedocs.io/en/0.9.16/) — Simulator reference
- [CARLA Windows Build](https://carla.readthedocs.io/en/0.9.16/build_windows/) — Build instructions
- [VIATRA Homepage](https://eclipse.dev/viatra/) — Query & transformation tool
- [Eclipse Modeling Tools](https://www.eclipse.org/downloads/packages/) — EMF & VIATRA IDE
- [EMF/XMI Standard](https://www.omg.org/spec/XMI/) — Data format specification

---

**For Setup Issues:**
- See [PREREQUISITES.md](PREREQUISITES.md) troubleshooting section
- Check Windows firewall (CARLA uses ports 2000-2001)

**For Usage Questions:**
- See [QUICKSTART.md](QUICKSTART.md) for common workflows
- See [STREAM_REFERENCE.md](STREAM_REFERENCE.md) for file locations

**For VIATRA Integration:**
- See [VIATRA_STREAM_GUIDE.md](VIATRA_STREAM_GUIDE.md) for step-by-step Eclipse setup
- See [docs/viatra_stream_integration.md](docs/viatra_stream_integration.md) for advanced patterns

---

## License

See [LICENSE](LICENSE) file.

---
