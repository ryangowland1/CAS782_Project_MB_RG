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

**Result:** Creates `data/scene_mock.xmi` with 3 nodes (2 vehicles, 1 pedestrian).

### Option B: Live CARLA

#### Step 1: Start CARLA Server

Open a **new terminal** and run from the project root:

```powershell
.\CARLA_0.9.16\CarlaUE4.exe -quality-level=Low -windowed -dx11
```

Wait for CARLA window to fully load (you'll see the main menu or simulation view).

#### Step 2: Export Scene Graph from Live CARLA

```powershell
.\.venv\Scripts\python.exe .\src\carla_scenegraph_export.py --output .\data\scene_live.xmi
```

**Result:** Creates `data/scene_live.xmi` with actors from the live CARLA world.

### Option C: Continuous Streaming

Start a scenario. There are other scenario options in the src folder.

```powershell
.\.venv\Scripts\python.exe .\src\scenario_ego_follow.py
```

Start the streaming bridge (updates `latest_snapshot.xmi` every second):

```powershell
# Mock mode (no CARLA needed)
powershell -ExecutionPolicy Bypass -File .\scripts\run_scenegraph_stream.ps1 -Mock -Interval 0.2

# Live CARLA mode (requires server running)
powershell -ExecutionPolicy Bypass -File .\scripts\run_scenegraph_stream.ps1 -Interval 0.2
```

View live updates:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\open_live_view.ps1
```

Opens `data/stream/live_view.html` in your browser showing real-time graph updates.

## Part 2: VIATRA Query Analysis

### Setup Dependencies

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

### Setup Queries

1. **Change Workspace**
   - `File` → `Switch Workspace` → `Other`
   - Navigate to and select `CAS782_Project_MB_RG`

2. **Import Projects**
   - `File` → `Open Projects from File System` → `Directory`
   - Select `CAS782_Project_MB_RG`
   - A list with `CAS782_Project_MB_RG` and the 3 projects should pop up. Unselect `CAS782_Project_MB_RG`, leave the 3 projects selected

3. **Generate Folders**
   - `File` → `New` → `Folder` → `Java` → `Package`
   - Name: `src` 
   - Place it in the `SceneGraphModel` project
   - `File` → `New` → `Folder` → `Java` → `Package`
   - Name: `src-gen` 
   - Place it in the `SceneGraphAPIQueries` project
   - This project requires empty folders but empty folders cannot be pushed to git

4. **Generate Scene Graph Code**
   - In Eclipse, open up 'SceneGraphModel\model\sceneGraphModel.genmodel'
   - Right-click 'SceneGraphModel' (in the sceneGraphModel.genmodel window, not in the Model Explorer window) → `Generate Model Code`
  
5. **Clean Projects**
   - `Project` → `Clean`
   - Clean `SceneGraphModel`, `SceneGraphQueries`, and `SceneGraphAPIQueries`, in that order

### Execute Queries

1. **Review Available Query Patterns**
   - Open `SceneGraphAPIQueries\src\apiqueries\QueryRunner.java`
    - You'll see the currently registered query patterns in this runner.
   - Go to line 48 and change the path so it is correct for your system

2. **Open up a Console**
   - `Window` → `Show View` → `Other` → `General` → `Console`
    
3. **Evaluate Available Patterns**
   - Right-click `SceneGraphAPIQueries`
   - Right-click `Eclipse Application`
   - Click `New configuration`
   - Program to Run → Run an application → SceneGraphAPIQueries.queryrunner
   - Click `Run`
   - Note that building the application took slightly over 2 minutes for me. Not sure why. Running the VIATRA queries takes around 50 ms

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
