# VIATRA Live Scene Graph Stream Integration

## Overview

The CARLA + VIATRA pipeline generates **live scene graph updates** that conform to the `SceneGraph.ecore` metamodel. This guide shows how to consume them in VIATRA.

## Stream Structure

```
data/stream/
├── snapshots/                    # Individual XMI snapshots per tick
│   ├── snapshot_000001.xmi
│   ├── snapshot_000002.xmi
│   └── ... (numbering increments every ~1 second)
├── latest_snapshot.xmi           # Always points to most recent state
├── current_state.json            # JSON mirror of latest XMI (for programmatic access)
├── events.jsonl                  # Change event stream (1 JSON line per tick)
└── live_view.html                # Auto-refreshing visualization (open in browser)
```

## Quick Start: Manual Import in Eclipse

### Step 1: Download & Install Eclipse Modeling Tools

1. Go to https://www.eclipse.org/downloads/packages/
2. Download **Eclipse Modeling Tools** (latest version)
3. Extract and launch Eclipse

### Step 2: Install VIATRA

1. In Eclipse menu: `Help` → `Install New Software`
2. Work with: `http://download.eclipse.org/viatra/updates/release/latest`
3. Check **VIATRA Query Language** and **VIATRA Query Development Tools**
4. Click `Finish` and restart Eclipse

### Step 3: Import Metamodel

1. Create a new Ecore project:
   - `File` → `New` → `Project` → Search for "Ecore" → `Ecore Modeling Project`
   - Name: `SceneGraph`
   - Click `Finish`

2. Copy the metamodel file:
   ```bash
   cp model/SceneGraph.ecore YourEclipseWorkspace/SceneGraph/model/
   ```

3. In Eclipse Project Explorer, double-click `SceneGraph.ecore` to open it
4. The metamodel is now registered

### Step 4: Import & Query a Snapshot

1. **To load a single snapshot:**
   - Right-click project → `New` → `Other` → `EMF` → `XMI model resource`
   - Point to: `data/stream/latest_snapshot.xmi` (or any `snapshot_XXXXX.xmi`)
   - Eclipse loads the model instance

2. **To create VIATRA queries:**
   - Right-click project → `New` → `Other` → `VIATRA` → `Query Definition File`
   - Copy contents of `queries/scenegraph.vql`:
     ```vql
     package cas782.scenegraph

     import "http://cas782/scenegraph"

     pattern fastVehicle(v:Vehicle) {
       Vehicle.speed(v, s);
       s > 13.9;
     }

     pattern connected(src:Node, dst:Node) {
       Edge.source(e, src);
       Edge.target(e, dst);
     }

     pattern vehiclePedestrianSharedRoad(v:Vehicle, p:Pedestrian) {
       Edge.source(e, v);
       Edge.target(e, p);
     } or {
       Edge.source(e, p);
       Edge.target(e, v);
     }
     ```

3. **Run queries:**
   - Right-click the `.vql` file → `VIATRA Query` → `Query Explorer`
   - Select a pattern to run and see live results

## Programmatic Integration: Live Polling Loop

For real-time integration, create a Java/Xtend application that polls the stream:

```java
import java.nio.file.*;
import org.eclipse.emf.ecore.resource.Resource;

public class ViatraStreamConsumer {
    private Path latestSnapshot = Paths.get("data/stream/latest_snapshot.xmi");
    private long lastModified = 0;
    
    public void pollStream() throws Exception {
        while (true) {
            long fileModTime = Files.getLastModifiedTime(latestSnapshot).toMillis();
            
            if (fileModTime > lastModified) {
                // New snapshot available
                Resource resource = loadXMI(latestSnapshot);
                
                // Run VIATRA queries
                runQueries(resource);
                
                lastModified = fileModTime;
            }
            
            Thread.sleep(500); // Poll every 500ms
        }
    }
    
    private void runQueries(Resource resource) {
        // Engine setup and pattern matching here
        // See VIATRA documentation for engine initialization
    }
}
```

## Event Stream Format: `events.jsonl`

Each line is a JSON object with this structure:

```json
{
  "timestamp": "2026-03-09T02:33:12.935688+00:00",
  "tick": 1,
  "snapshot": "data/stream/snapshots/snapshot_000001.xmi",
  "node_count": 5,
  "edge_count": 2,
  "node_changes": {
    "added": [
      {
        "node_type": "Vehicle",
        "external_id": "27",
        "x": 109.7137,
        "y": 22.3545,
        "z": 0.0034,
        "speed": 9.2964
      }
    ],
    "removed": [],
    "updated": [
      {
        "before": { "node_type": "Vehicle", "external_id": "33", "x": -48.8, "y": -8.6, "z": 0.0, "speed": 0.5 },
        "after":  { "node_type": "Vehicle", "external_id": "33", "x": -48.9, "y": -8.7, "z": 0.0, "speed": 0.6 }
      }
    ]
  },
  "edge_changes": {
    "added": [
      { "type": "proximity", "source": "27", "target": "31" }
    ],
    "removed": []
  }
}
```

**Use this for:**
- Streaming updates without re-parsing full XMI
- Tracking which nodes/edges changed per tick
- Building incremental query evaluation

## XMI Format Example

```xml
<?xml version='1.0' encoding='utf-8'?>
<scenegraph:Scene 
  xmlns:scenegraph="http://cas782/scenegraph" 
  xmlns:xmi="http://www.omg.org/XMI" 
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
  xmi:version="2.0" 
  name="CARLA_Stream">
  
  <nodes xsi:type="scenegraph:Vehicle" 
         id="27" 
         x="109.7137" y="22.3545" z="0.0034" 
         speed="9.2964" />
  
  <nodes xsi:type="scenegraph:Vehicle" 
         id="33" 
         x="-48.829250" y="-8.584871" z="-0.002295" 
         speed="0.000021" />
  
  <nodes xsi:type="scenegraph:Pedestrian" 
         id="50" 
         x="5.0" y="10.0" z="0.0" />
  
  <edges type="proximity" 
         source="//@nodes.0" 
         target="//@nodes.1" />
</scenegraph:Scene>
```

## Metamodel Details

**Classes:**
- `Scene` — Root container
- `Node` — Abstract base (Vehicle, Pedestrian, RoadSegment)
- `Vehicle` — x, y, z, speed (m/s)
- `Pedestrian` — x, y, z (no speed attribute)
- `Edge` — source, target, type (e.g., "proximity")

**Attributes:**
- `id` (String) — External actor ID from CARLA
- `x, y, z` (Double) — Coordinates in meters
- `speed` (Double) — Velocity magnitude (Vehicle only)
- `type` (String) — Edge classification

## Real-Time Visualization

Open a web browser to:
```
data/stream/live_view.html
```

This page:
- Auto-refreshes every 2 seconds
- Shows current tick count
- Displays all nodes and proximity edges
- Color-coded: Blue = Vehicle, Red = Pedestrian

## Performance Notes

- **Snapshot frequency:** ~1 per second (configurable via `--interval` in stream bridge)
- **File sizes:** ~2-5 KB per XMI (5 nodes avg); ~10 KB per events.jsonl line total
- **Storage:** 1000 snapshots = ~2-5 MB disk (auto-cleanup recommended)

## Advanced: Hook VIATRA Runtime to Stream

Create a VIATRA Transformation that reactively applies updates:

```xtend
import org.eclipse.viatra.transformation.evm.api.RuleEngine
import org.eclipse.viatra.transformation.evm.specific.TransformationEVMFactory

class StreamDrivenTransformation {
  def void setupReactiveRules(String snapshotPath) {
    val engine = TransformationEVMFactory.createEventDrivenVM(
      getRVT(), 
      modelRoot
    ).RuleEngine
    
    engine.startUnscheduledRuleScheduler()
    
    // Whenever fastVehicle pattern matches, rule fires
    // Each XMI reload triggers re-evaluation
  }
}
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Failed to register metamodel" | Ensure `SceneGraph.ecore` is in project; rebuild project |
| Snapshot not updating | Check that stream bridge is running: `python scenegraph_stream_bridge.py` still active |
| VIATRA queries show no matches | Verify XMI conforms to metamodel; check namespace `http://cas782/scenegraph` |
| Events.jsonl not growing | Stream bridge may be paused; restart: `python scenegraph_stream_bridge.py --ticks 0` |

## File Locations Summary

| File/Directory | Purpose | Location |
|---|---|---|
| Metamodel | XMI type definitions | `model/SceneGraph.ecore` |
| Live Snapshot | Most recent world state | `data/stream/latest_snapshot.xmi` |
| Snapshots Archive | Historical states (one per tick) | `data/stream/snapshots/` |
| Event Stream | Change deltas as JSONL | `data/stream/events.jsonl` |
| State Mirror | Latest as JSON | `data/stream/current_state.json` |
| Visualization | Real-time web view | `data/stream/live_view.html` |
| Queries | VQL pattern definitions | `queries/scenegraph.vql` |

## What's Next

1. **Run Streaming Producer:** Keep the CARLA scenario + stream bridge running
2. **Eclipse Project:** Set up metamodel + queries as described above
3. **Load Snapshot:** Point VIATRA to `latest_snapshot.xmi` to begin querying
4. **Observe Live Updates:** Reload snapshot every ~1s or implement event polling
5. **Execute Patterns:** Use VIATRA Query Explorer to run `fastVehicle`, `connected`, etc.

---

**Stream Last Updated:** Continuous (spawned vehicle scenario running)  
**Sample Size:** 1700+ ticks, 5 vehicles, ~4000 snapshots

