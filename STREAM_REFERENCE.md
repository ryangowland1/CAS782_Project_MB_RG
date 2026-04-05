# Live Scene Graph Stream Reference (QUICK START)

## 🔴 Stream Status: ACTIVE ✅

**Last Updated:** 3/8/2026 11:04 PM (continuously updating)

**Current Metrics:**
- **Events Generated:** 1790 (growing every ~1 second)
- **Snapshots Archived:** 1771
- **Active Vehicles:** 5 (IDs: 26, 31, 32, 33, 34)
- **Server:** CARLA 0.9.16 running on `127.0.0.1:2000`

---

## 📁 Files You Need for VIATRA

### Immediate (Load These Into Eclipse)

1. **Metamodel Definition:**
   ```
   queries/SceneGraph.ecore
   ```
   - Namespace: `http://cas782/scenegraph`
   - Classes: Scene, Vehicle, Pedestrian, Node, Edge
   - Status: ✅ Ready to import into Eclipse

2. **Query Patterns:**
   ```
   queries/scenegraph.vql
   ```
   - Pattern 1: `fastVehicle` — vehicles with speed > 13.9 m/s
   - Pattern 2: `connected` — edges linking two nodes
   - Pattern 3: `vehiclePedestrianSharedRoad` — pedestrians on vehicle paths
   - Status: ✅ Copy-paste ready into VIATRA Query Explorer

3. **Live Model Instance (Latest):**
   ```
   data/stream/latest_snapshot.xmi
   ```
   - Format: EMF XMI (auto-synced every tick)
   - Content: 5 vehicles with positions (x, y, z) and speeds
   - Last Synced: 3/8/2026 11:04 PM (5 seconds ago)
   - Example:
     ```xml
     <scenegraph:Scene xmlns:scenegraph="http://cas782/scenegraph" ...>
       <nodes xsi:type="scenegraph:Vehicle" id="32" x="120.27" y="28.58" z="0.13" speed="0.0036" />
       <nodes xsi:type="scenegraph:Vehicle" id="33" x="-48.83" y="-8.58" z="-0.00" speed="0.00" />
       <!-- ... 3 more vehicles -->
     </scenegraph:Scene>
     ```
   - Status: ✅ Ready to load as model instance

### Advanced (Incremental Updates)

4. **Event Stream (JSONL):**
   ```
   data/stream/events.jsonl
   ```
   - 1790 lines (1 per tick)
   - Format: JSON Lines (newline-delimited JSON)
   - Usage: Programmatic consumption for real-time delta updates
   - Example line:
     ```json
     {"timestamp": "2026-03-09T02:33:12.935688+00:00", "tick": 1, "snapshot": "data/stream/snapshots/snapshot_000001.xmi", "node_count": 9, "edge_count": 0, "node_changes": {"added": [{"node_type": "Vehicle", "external_id": "26", "x": -64.6446, "y": 24.471, "z": -0.0075, "speed": 0.0}], "removed": [], "updated": []}, "edge_changes": {"added": [], "removed": []}}
     ```

5. **Snapshot Archive:**
   ```
   data/stream/snapshots/snapshot_000001.xmi ... snapshot_001771.xmi
   ```
   - 1771 historical snapshots (~29 minutes of continuous operation)
   - Each ~3-5 KB
   - For batch analysis or time-series queries
   - Status: ✅ Ready for batch loading

6. **JSON State Mirror:**
   ```
   data/stream/current_state.json
   ```
   - Same data as `latest_snapshot.xmi` but in JSON format
   - Useful for programmatic consumption in Java/Python
   - Status: ✅ Available

---

## ⚡ Getting Started (3 Steps)

### Step 1: Install Eclipse + VIATRA
Follow the detailed steps in `VIATRA_STREAM_GUIDE.md` section "Eclipse + VIATRA Setup"

### Step 2: Import Metamodel
1. Open Eclipse
2. File → New → EMF Project
3. Import → File System → Browse to `queries/SceneGraph.ecore`
4. Validate namespace: `http://cas782/scenegraph` ✓

### Step 3: Load Model + Run Queries
1. Right-click ecore file → **Run As → VIATRA Query Tooling**
2. Load instance: `data/stream/latest_snapshot.xmi`
3. Paste patterns from `queries/scenegraph.vql`
4. Execute in VIATRA Query Explorer
5. See live results!

---

## 🔄 Real-Time Streaming (Optional)

The stream is **continuously running** in the background. 

- **New snapshots** written every ~1 second
- **Events logged** to `events.jsonl` with deltas
- **latest_snapshot.xmi** auto-updated

**To see live updates in Eclipse:**
- Periodically reload `latest_snapshot.xmi` in your model
- Or write a Java/Xtend program that polls `events.jsonl` every 1 second
- See `VIATRA_STREAM_GUIDE.md` section "Real-Time Polling Loop (Pseudocode)" for Java example

---

## 📊 Example: Load and Query

### In VIATRA Query Explorer:

**Load your model:**
```
File → Open Model Instance
Path: data/stream/latest_snapshot.xmi
```

**Execute pattern (paste into VQL editor):**
```vql
pattern fastVehicle(vehicle : Vehicle) {
    Vehicle.speed(vehicle, speed);
    check(speed > 13.9);
}
```

**Expected Output:**
```
Results (0 found in current snapshot)
-- All vehicles currently stationary or slow-moving
```

---

## 🎯 What You Have

| Item | Location | Status | Size |
|------|----------|--------|------|
| **Metamodel** | `queries/SceneGraph.ecore` | ✅ Ready | ~2 KB |
| **Queries** | `queries/scenegraph.vql` | ✅ Ready | ~1 KB |
| **Latest State** | `data/stream/latest_snapshot.xmi` | ✅ Live | ~1 KB |
| **Event Stream** | `data/stream/events.jsonl` | ✅ Live | ~1.8 MB |
| **Snapshots** | `data/stream/snapshots/` | ✅ Live | ~5-10 MB |
| **Docs** | `VIATRA_STREAM_GUIDE.md` | ✅ Ready | ~12 KB |

---

## 🔧 Troubleshooting Quick Links

- **"Cannot import metamodel"** → See VIATRA_STREAM_GUIDE.md § "Step 4: Register Metamodel"
- **"No results for query"** → All vehicles are stationary now; try loading an older snapshot or wait for traffic
- **"XMI parsing error"** → Ensure you're loading from `data/stream/latest_snapshot.xmi` (not symlink)
- **"VIATRA not installed"** → Follow Eclipse Marketplace steps in VIATRA_STREAM_GUIDE.md § "Installation"

---

## ℹ️ System Info

- **CARLA Version:** 0.9.16
- **Python:** 3.12.10
- **Metamodel Namespace:** `http://cas782/scenegraph`
- **XMI Version:** 2.0
- **Server:** 127.0.0.1:2000
- **Uptime:** 29+ minutes (continuous)

---

**📖 For detailed setup & integration, see:** [`VIATRA_STREAM_GUIDE.md`](VIATRA_STREAM_GUIDE.md)

**🚀 Next:** Follow Step 1 above to install Eclipse + VIATRA, then load the metamodel and model instance!
