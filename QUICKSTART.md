# CARLA + VIATRA Quick Start Guide

## Prerequisites Check

- [x] Python 3.12 installed (see PREREQUISITES.md)
- [x] SETUP.ps1 has been run successfully
- [x] CARLA 0.9.16 downloaded by setup

### Recommended First Steps for New Users

**Option 1:** Start with live CARLA simulation (installed during setup)
**Option 2:** Use mock mode for quick testing without starting the CARLA server

## Part 1: CARLA Scene Graph Export

### Option A: Mock Mode (Quick Testing)

```powershell
# Generate a test scene graph
.\.venv\Scripts\python.exe .\src\carla_scenegraph_export.py --mock --output .\data\scene_mock.xmi
```

**Result:** Creates `data/scene_mock.xmi` with 3 nodes (2 vehicles, 1 pedestrian) and proximity edges.

### Option B: Live CARLA

#### Step 1: Start CARLA Server

Open a **new terminal** and run from the project root:

```powershell
.\CARLA_0.9.16\WindowsNoEditor\CarlaUE4.exe -quality-level=Low -windowed
```

Wait for CARLA window to fully load (you'll see the main menu or simulation view).

#### Step 2: Export Scene Graph from Live CARLA

```powershell
.\.venv\Scripts\python.exe .\src\carla_scenegraph_export.py --output .\data\scene_live.xmi
```

**Result:** Creates `data/scene_live.xmi` with actors from the live CARLA world.

### Option C: Continuous Streaming

Start the streaming bridge (updates scene graph every second):

```powershell
# Mock mode (no CARLA needed)
powershell -ExecutionPolicy Bypass -File .\scripts\run_scenegraph_stream.ps1 -Mock -Interval 1.0

# Live CARLA mode (requires server running)
powershell -ExecutionPolicy Bypass -File .\scripts\run_scenegraph_stream.ps1 -Interval 1.0
```

View live updates:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\open_live_view.ps1
```

Opens `data/stream/live_view.html` in your browser showing real-time graph updates.

## Part 2: VIATRA Query Analysis

### Setup Eclipse + VIATRA

1. **Download Eclipse Modeling Tools**
   - Go to https://www.eclipse.org/downloads/packages/
   - Download "Eclipse Modeling Tools"

2. **Install VIATRA Plugin**
   - In Eclipse: `Help` → `Install New Software`
   - Click `Add...`
   - Name: `VIATRA`
   - Location: `http://download.eclipse.org/viatra/updates/release/latest`
   - Select: `VIATRA Query and Transformation SDK`
   - Click `Next` and complete installation
   - Restart Eclipse

### Import Scene Graph Metamodel

1. **Create EMF Project**
   - `File` → `New` → `Project` → `Eclipse Modeling Framework` → `Empty EMF Project`
   - Name: `SceneGraphModel`

2. **Import Ecore**
   - Right-click project → `Import` → `General` → `File System`
   - Browse to: `CAS782_Project_MB_RG\model`
   - Select `SceneGraph.ecore`
   - Click `Finish`

3. **Register EPackage**
   - Right-click `SceneGraph.ecore` → `Register EPackages`
   - This makes the metamodel available to VIATRA

### Import Scene Graph Instance

1. **Import XMI File**
   - Right-click project → `Import` → `General` → `File System`
   - Browse to: `\CAS782_Project_MB_RG\data`
   - Select `scene_mock.xmi` (or `scene_live.xmi`)
   - Click `Finish`

2. **Open in Sample Reflective Ecore Model Editor**
   - Right-click the XMI file → `Open With` → `Sample Reflective Ecore Model Editor`
   - You should see the scene hierarchy:
     ```
     Scene
     ├─ nodes
     │  ├─ Vehicle (veh-ego)
     │  ├─ Vehicle (veh-1)
     │  └─ Pedestrian (ped-1)
     └─ edges
        ├─ proximity (veh-ego → veh-1)
        ├─ proximity (veh-ego → ped-1)
        └─ proximity (veh-1 → ped-1)
     ```

### Create VIATRA Queries

1. **Create Query Project**
   - `File` → `New` → `Project` → `VIATRA` → `VIATRA Query Project`
   - Name: `SceneGraphQueries`

2. **Import Queries**
   - Right-click `src` folder → `Import` → `General` → `File System`
   - Browse to: `CAS782_Project_MB_RG\queries`
   - Select `scenegraph.vql`
   - Click `Finish`

3. **Review Available Patterns**
   - Open `scenegraph.vql`
   - You'll see three patterns:
     - `fastVehicle` - Finds vehicles moving faster than 50 km/h
     - `connected` - Generic connectivity between nodes
     - `vehiclePedestrianSharedRoad` - Potential vehicle/pedestrian conflicts

### Execute Queries

1. **Load Model into Query Explorer**
   - Right-click the XMI file → `VIATRA` → `Load model to Query Explorer`
   
2. **Open Query Explorer**
   - `Window` → `Show View` → `Other` → `VIATRA` → `Query Explorer`

3. **Run Patterns**
   - In Query Explorer, you'll see your patterns listed
   - Check the checkboxes next to patterns you want to execute
   - View results in the `Query Explorer` view
   
4. **Example Results**
   For `scene_mock.xmi`:
   - `fastVehicle`: No matches (mock vehicles are < 50 km/h)
   - `connected`: 6 matches (3 edges × 2 directions)
   - `vehiclePedestrianSharedRoad`: 0 matches (no road segments in mock data)

## Example Workflow

### Complete Mock Example

```powershell
# 1. Generate mock scene graph
.\.venv\Scripts\python.exe .\src\carla_scenegraph_export.py --mock --output .\data\demo.xmi

# 2. View the XMI
Get-Content .\data\demo.xmi

# 3. Import into Eclipse + VIATRA and run queries
```

### Complete Live CARLA Example

```powershell
# Terminal 1: Start CARLA
.\CARLA_0.9.16\WindowsNoEditor\CarlaUE4.exe -quality-level=Low -windowed

# Terminal 2 (this project): Generate scene graph
.\.venv\Scripts\python.exe .\src\carla_scenegraph_export.py --output .\data\live.xmi

# 3. Import live.xmi into Eclipse + VIATRA
# 4. Run queries to analyze the current scene
```

### Streaming Example

```powershell
# Terminal 1: Start CARLA (if using real mode)
.\CARLA_0.9.16\WindowsNoEditor\CarlaUE4.exe -quality-level=Low -windowed

# Terminal 2: Start streaming bridge
powershell -ExecutionPolicy Bypass -File .\scripts\run_scenegraph_stream.ps1 -Interval 1.0

# Terminal 3: View live updates
powershell -ExecutionPolicy Bypass -File .\scripts\open_live_view.ps1

# For VIATRA: Configure incremental query engine to watch data/stream/*.xmi files
```

## Next Steps

1. **Add More Actors to CARLA**
   - Spawn vehicles and pedestrians in CARLA
   - Re-export scene graph
   - See updated query results

2. **Create Custom Queries**
   - Open `scenegraph.vql` in Eclipse
   - Add new patterns (e.g., "vehicles near pedestrians")
   - Test on your scene graphs

3. **Implement Transformations**
   - Use VIATRA Transformation API
   - Create model-to-model transformations
   - Example: Generate warning events for detected conflicts

## Troubleshooting

### CARLA Connection Issues
```powershell
# Test connection
.\.venv\Scripts\python.exe -c "import carla; c = carla.Client('127.0.0.1', 2000); c.set_timeout(2.0); print('Connected:', c.get_world().get_map().name)"
```

### VIATRA Query Not Finding Matches
- Ensure EPackage is registered correctly
- Check XMI file has correct namespace: `xmlns:scenegraph="http://cas782/scenegraph"`
- Verify metamodel and instance are compatible

### Empty Scene Graph
- CARLA world may have no actors
- In CARLA, use `examples/spawn_npc.py` to add actors:
```powershell
# From your project directory
.\.venv\Scripts\python.exe .\CARLA_0.9.16\PythonAPI\examples\spawn_npc.py -n 20 -w 10
```

## Documentation

- `docs/windows_setup_carla_viatra.md` - Detailed setup instructions
- `docs/architecture.md` - System architecture and data flow
- `docs/extractor_usage.md` - Scene graph export details
- `docs/viatra_stream_integration.md` - Streaming integration

## Verification Checklist

- [ ] CARLA Python module imports successfully
- [ ] Mock scene graph generates correctly
- [ ] CARLA server launches
- [ ] Live scene graph exports from CARLA
- [ ] Eclipse with VIATRA installed
- [ ] Metamodel imported and registered
- [ ] XMI instance opens in Eclipse
- [ ] VIATRA queries execute successfully
- [ ] Streaming mode works
- [ ] Live view HTML shows updates
