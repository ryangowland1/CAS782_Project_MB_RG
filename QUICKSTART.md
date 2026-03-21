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

### Setup JDK + Eclipse + XTend + VIATRA

1. **Download JDK**
   - Go to https://www.oracle.com/ca-en/java/technologies/downloads
   - Download the latest version of JDK

2. **Download Eclipse Modeling Tools**
   - Go to https://www.eclipse.org/downloads/packages/release/2025-06/r
   - Download "Eclipse Modeling Tools"
   - Note that this is version 2025-06 rather than the latest version

3. **Install Xtend Plugin**
   - In Eclipse: `Help` → `Eclipse Marketplace`
   - Search for and install Xtend
   - Restart Eclipse

4. **Install VIATRA Plugin**
   - In Eclipse: `Help` → `Eclipse Marketplace`
   - Search for and install VIATRA
   - Restart Eclipse

### Import Scene Graph Metamodel

1. **Create Ecore Project**
   - `File` → `New` → `Project` → `Eclipse Modeling Framework` → `Ecore Modeling Project`
   - Name: `SceneGraphModel`

2. **Import Ecore**
   - Go to `model\SceneGraphModel.ecore`
   - Right click -> `Open With` → `Plain Text Editor`
   - Replace with the contents of `\CAS782_Project_MB_RG\model\SceneGraph.ecore`
   - Save the file

### Import Scene Graph Instance

1. **Import XMI File**
   - Right-click 'SceneGraphModel' → `Import` → `General` → `File System`
   - Browse to: `\CAS782_Project_MB_RG\data`
   - Select `demo_mock.xmi` (or `scene_live.xmi`)
   - Click `Finish`

2. **Generate Scene Graph Code**
   - In Eclipse, open up '\model\sceneGraphModel.genmodel'
   - Right-click 'SceneGraphModel' (in the sceneGraphModel.genmodel window, not in the Model Explorer window) → `Generate Model Code`

3. **Open in Sample Reflective Ecore Model Editor**
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
   - `File` → `New` → `Other` → `Java` → `Package`
   - Name: `queries` 
   - Place it in the `src` folder
   - Right-click `queries` package → `Import` → `General` → `File System`
   - Browse to: `CAS782_Project_MB_RG\queries`
   - Select `scenegraph.vql`
   - Click `Finish`
  
3. **Fix Manifest**
   - In the new project, open up `META-INF\MANIFEST.mf`
   - Create an Export-Package key and give it the value `queries`
   - In Require-Bundle, add `SceneGraphModel`
   - Delete javax.annotations from the manifest
  
4. **Review Available Patterns**
   - Open `scenegraph.vql`
   - You'll see one pattern:
     - `slowVehicle` - Finds vehicles moving slower than 50 km/h

### Execute Queries
   
1. **Create API Query Project**
   - `File` → `New` → `Project` → `VIATRA` → `VIATRA Query Project`
   - Name: `SceneGraphAPIQueries`

2. **Import Queries**
   - `File` → `New` → `Other` → `Java` → `Package`
   - Name: `apiqueries` 
   - Place it in the `src` folder
   - Right-click `queries` package → `Import` → `General` → `File System`
   - Browse to: `CAS782_Project_MB_RG\queries`
   - Select `apiscenegraph.java`
   - Click `Finish`

3. **Import XML**
   - Right-click `SceneGraphAPIQueries` package → `Import` → `General` → `File System`
   - Browse to: `CAS782_Project_MB_RG\queries`
   - Select `plugins.xml`
   - Click `Finish`
  
4. **Fix Manifest**
   - In the new project, open up `META-INF\MANIFEST.mf`
   - Create an Export-Package key and give it the value `queries`
   - In Require_Bundle, add `SceneGraphModel`, `SceneGraphQueries`, and 
   - Delete javax.annotations from the manifest

5. **Make SceneGraphQueries Accessible to SceneGraphAPIQueries**
   - Right-click `SceneGraphQueries`
   - Properties → Java Build Path → Plug-in Dependencies → Access rules: No rules defined
   - Add a rule with a Resolution of `Accessible` and a Rule Pattern of `queries/*`

6. **Review Available Patterns**
   - Open `apiscenegraph.java`
   - You'll see three patterns:
     - `slowVehicle` - Finds vehicles moving slower than 50 km/h
   - Go to line 48 and change the path so it uses your username
    
7. **Evaluate Available Patterns**
   - Right-click `SceneGraphModel`
   - Right-click `Eclipse Application`
   - Click `New configuration`
   - Program to Run → Run an application → SceneGraphAPIQueries.queryrunner
   - Click `Run`
   - Note that building the application took slightly over 2 minutes for me. Not sure why. Running the VIATRA query took 180 ms

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
