# RSS Safety Check — VIATRA Integration Guide

This document provides step-by-step instructions for building and running the
RSS (Responsibility-Sensitive Safety) violation checks through the VIATRA
scene graph analysis pipeline.

---

## Overview: What Are We Doing?

We have **two parallel implementations** of the same RSS safety checks:

1. **Python-side** (`rss_safety_check.py`) — standalone, already tested with
   24 unit tests and two CARLA scenarios. Works right now, no Eclipse needed.
2. **VIATRA-side** (VQL patterns + Java) — runs inside Eclipse as a model
   transformation on the scene graph XMI. This is what the steps below set up.

The VIATRA pipeline works like this:

```
CARLA server ──► scenario script ──► scenegraph_stream_bridge.py
                                          │
                                          ▼
                                  latest_snapshot.xmi  ◄──► QueryRunner (Eclipse)
                                          │                      │
                                          │              detects RSS violations,
                                          │              writes edges back to XMI
                                          ▼
                                    live_view.html (browser)
```

---

## Part A: Python-Only Testing (No Eclipse Needed)

If you just want to verify the RSS math and CARLA scenarios work, do this
first. You can skip to Part B if you want the full VIATRA integration.

### A1. Run the unit tests

```powershell
cd "C:\Users\Ryan\Documents\McMaster MASc\2025-26\Classes\CAS782\Final Project\CAS782_Project_MB_RG"
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_rss_safety.py -v
```

You should see **24 passed** — these test the RSS formulas from
*AV_Safety_Frameworks.pdf* Equations 1 and 3.

### A2. Run a CARLA scenario (server must be running)

**Terminal 1** — start CARLA:
```powershell
.\CarlaUE4\Binaries\Win64\CarlaUE4-Win64-Shipping.exe
```
Wait for the 3D window to fully load.

**Terminal 2** — run the longitudinal RSS scenario:
```powershell
.\.venv\Scripts\Activate.ps1
python src\scenario_rss_longitudinal.py
```

This spawns an ego following a lead vehicle at ~5 m gap. The script prints RSS
violations each tick — you should see ~89% of ticks flagged as violations
(gap < RSS safe distance at 30 km/h ≈ 13 m).

---

## Part B: VIATRA Eclipse Setup (Step by Step)

These steps set up the VIATRA model transformation so that `QueryRunner`
automatically detects RSS violations in the live XMI stream.

---

### B1. Open Eclipse and install required extensions

Launch your Eclipse installation. If it asks for a workspace location, any
folder is fine (it does not need to be the repo root).

**Install the required Eclipse features** (only needed once):

1. Go to **Help** → **Install New Software…**

2. **EMF SDK** (needed for the `.genmodel` editor and code generation):
   - In the **Work with** dropdown, select your Eclipse release site
     (e.g., `2024-12 - https://download.eclipse.org/releases/2024-12`).
     If you don't see it, paste the URL and press Enter.
   - In the search/filter box, type `EMF`
   - Check **EMF - Eclipse Modeling Framework SDK**
   - Click **Next** → **Next** → accept the license → **Finish**
   - Restart Eclipse when prompted

3. **VIATRA** (needed for `.vql` editor and pattern compilation):
   - **Install Xtext first** (step 4 below), then come back here
   - Go to **Help** → **Install New Software…** again
   - In **Work with**, paste:
     ```
     https://download.eclipse.org/viatra/updates/release/latest
     ```
   - **Uncheck** "Group items by category" at the bottom of the dialog
     (this makes individual features visible)
   - Select **only** these three features:
     - ☑ **VIATRA Query Runtime**
     - ☑ **VIATRA Query IDE Feature**
     - ☑ **VIATRA Transformation Engine**
   - **Leave everything else unchecked.** Specifically do NOT install:
     - ~~VIATRA Query and Transformation SDK~~ (pulls in testing deps that fail)
     - ~~Anything with "Graphiti"~~ (broken `org.eclipse.collections` dep)
     - ~~Anything with "Testing"~~ (requires old `xtext.junit4`)
     - ~~Anything with "Source"~~ (not needed, may pull in broken deps)
   - **Important:** Use the `latest` update site, NOT `2.8.0`. The 2.8.0
     version is incompatible with current Xtext and the VQL editor won't work.
   - Click **Next** → **Next** → accept the license → **Finish**
   - Restart Eclipse when prompted

4. **Xtext** (required by VIATRA's VQL editor — install this BEFORE VIATRA IDE):
   - Go to **Help** → **Install New Software…**
   - In **Work with**, select your Eclipse release site
     (e.g., `2024-12 - https://download.eclipse.org/releases/2024-12`)
   - In the filter box, type `Xtext`
   - Check **Xtext Complete SDK**
   - Install and restart Eclipse
   - **Then** install the VIATRA features (step 3 above). The VQL editor
     will not appear without Xtext installed first.

**How to verify the extensions are installed:**
- Go to **Help** → **About Eclipse IDE** → **Installation Details**
- On the **Installed Software** tab, you should see entries for:
  - `EMF - Eclipse Modeling Framework SDK`
  - `VIATRA Query and Transformation SDK`
- Alternatively: try **File** → **New** → **Other…** and search for
  `EMF Generator Model` — if it appears, EMF is installed correctly

---

### B2. Import the three projects into Eclipse

1. Go to **File** → **Import…**
2. In the dialog, expand **General** → select **Existing Projects into Workspace** → click **Next**
3. Click **Browse…** next to "Select root directory"
4. Navigate to:
   ```
   C:\Users\Ryan\Documents\McMaster MASc\2025-26\Classes\CAS782\Final Project\CAS782_Project_MB_RG
   ```
5. Eclipse will discover three projects. Make sure all three are checked:
   - ☑ **SceneGraphModel**
   - ☑ **SceneGraphQueries**
   - ☑ **SceneGraphAPIQueries**
6. Click **Finish**
7. Wait for Eclipse to finish building (watch the progress bar at bottom-right)

**What you should see:** Three projects appear in the Project Explorer (left panel). There may be red error markers — that's expected until we do the next steps.

---

### B3. Regenerate EMF model code (creates the `vx`/`vy` Java getters/setters)

The metamodel (`.ecore`) has been updated with `vx` and `vy` attributes on
`Vehicle`, but the Java code hasn't been generated yet. You need to do this:

1. In **Project Explorer**, expand **SceneGraphModel** → **model**
2. **Double-click** `sceneGraphModel.genmodel` — it opens in the editor
3. In the editor, you'll see a tree. The root node says something like **SceneGraph**
4. **Right-click** the root **SceneGraph** node
5. Click **Generate Model Code**
6. Wait — Eclipse will generate Java files in `SceneGraphModel/src-gen/`

**How to verify it worked:**
- Expand **SceneGraphModel** → **src-gen** → **scenegraph** in Project Explorer
- You should see files like `Vehicle.java`, `Scene.java`, etc.
- Open `Vehicle.java` and search for `getVx` — it should exist

**If you get errors:**
- If Eclipse complains about Java version, right-click **SceneGraphModel** →
  **Properties** → **Java Compiler** → set compliance to **21**
- If `src-gen` doesn't appear, press **F5** on the SceneGraphModel project to refresh

---

### B4. Build the VQL patterns (generates RSS pattern matchers)

1. In **Project Explorer**, expand **SceneGraphQueries** → **src** → **queries**
2. **Double-click** `scenegraph.vql` to open it
3. Check that the file has **syntax highlighting** (keywords like `pattern`,
   `check`, `find` should be colored). If it opens as plain text, that's OK —
   the VQL editor may not work with newer Xtext versions, but the **builder**
   still generates code correctly. You can edit VQL as plain text.
4. Trigger compilation:
   - First, ensure auto-build is enabled: **Project** menu → check that
     **Build Automatically** has a ✓ next to it (click it if not)
   - Then force a clean rebuild: **Project** → **Clean…** → select
     **SceneGraphQueries** → click **Clean**
   - Eclipse will rebuild the project and the VIATRA/Xtext builders will
     generate pattern matcher classes
5. When done, check that **SceneGraphQueries** → **src-gen** → **queries**
   now contains these files (among others):
   - `RssLongitudinalViolation.java`
   - `RemoveRssLongitudinalViolation.java`
   - `RssLateralViolation.java`
   - `RemoveRssLateralViolation.java`

**If auto-build didn't trigger:**
- Go to **Project** menu → make sure **Build Automatically** is checked (✓)
- Then do **Project** → **Clean…** → select **SceneGraphQueries** → **OK**
- Or manually: **Project** → **Build All** (Ctrl+B)

**If VQL shows red errors about `Vehicle.vx` or `Vehicle.vy`:**
- Step B3 didn't complete. Go back and regenerate.
- Try: right-click **SceneGraphModel** → **Refresh** (F5), then
  right-click **SceneGraphQueries** → **Refresh** (F5), then **Build All**

**If VQL shows errors about missing imports or packages:**
- Right-click **SceneGraphQueries** → **Properties** → **Project References**
- Make sure **SceneGraphModel** is checked

---

### B5. Check that SceneGraphAPIQueries builds cleanly

1. Expand **SceneGraphAPIQueries** → **src** → **apiqueries**
2. Open `QueryRunner.java`
3. It should have **no red underlines**. If it does:
   - Check imports at the top — it imports `queries.RssLongitudinalViolation` etc.
   - These come from `SceneGraphQueries/src-gen/` (Step B4)
   - If missing: make sure B4 completed, then **Build All** again

4. **Check the MODEL_PATH** on line ~48. It should read:
   ```java
   private static final String MODEL_PATH =
       "C:\\Users\\Ryan\\Documents\\McMaster MASc\\2025-26\\Classes\\CAS782\\Final Project\\CAS782_Project_MB_RG\\data\\stream\\latest_snapshot.xmi";
   ```

---

### B6. Start CARLA + stream bridge + scenario

You need **three things running simultaneously** in separate PowerShell
windows. Open three terminals and `cd` to the project root in each.

**Terminal 1 — CARLA server:**
```powershell
.\CarlaUE4\Binaries\Win64\CarlaUE4-Win64-Shipping.exe
```
Wait for the 3D window to fully load (~30 seconds).

**Terminal 2 — Stream bridge** (reads CARLA, writes `latest_snapshot.xmi`):
```powershell
.\.venv\Scripts\Activate.ps1
python src\scenegraph_stream_bridge.py
```
You should see output like `Tick 1: 5 nodes, 2 edges` repeating every second.

**Terminal 3 — RSS scenario** (drives vehicles in CARLA):
```powershell
.\.venv\Scripts\Activate.ps1
python src\scenario_rss_longitudinal.py
```

At this point, `data\stream\latest_snapshot.xmi` is being updated every
~1 second with vehicle positions, speeds, and velocity components (`vx`, `vy`).

---

### B7. Create and run the QueryRunner launch configuration

Back in Eclipse:

1. Go to **Run** → **Run Configurations…**
2. In the left panel, find **Eclipse Application**
3. **Right-click** "Eclipse Application" → **New Configuration**
4. Set the following fields:

   **Name:** `QueryRunner`

   **Main tab:**
   - Uncheck **Run a product** (if checked)
   - In the **Run an application** dropdown, select: `apiqueries.QueryRunner`
   - If you don't see it in the dropdown, click **Browse…** and type `QueryRunner`

   **Plug-ins tab:**
   - Click **Deselect All** first
   - Then check these three:
     - ☑ **SceneGraphModel**
     - ☑ **SceneGraphQueries**
     - ☑ **SceneGraphAPIQueries**
   - Click **Add Required Plug-ins** button — this auto-selects all
     dependencies (EMF, VIATRA runtime, etc.)

   **Arguments tab:**
   - In **VM arguments**, add (if not already there):
     ```
     -Dosgi.framework.extensions=org.eclipse.osgi.compatibility.state
     ```

5. Click **Apply**, then **Run**

**What you should see in the Eclipse Console:**
```
--- Executing Batch Transformation ---
[RSS] Created rss_longitudinal violation edge: vehicle_XX -> vehicle_YY
VIATRA took: 42 ms
--- Executing Batch Transformation ---
[RSS] Removed rss_longitudinal violation edge: vehicle_XX -> vehicle_YY
VIATRA took: 38 ms
```

The QueryRunner loops forever, reading `latest_snapshot.xmi` every ~500ms,
running all VIATRA patterns (distance, spatial, lane, following, AND the new
RSS checks), and writing the results back.

**If nothing prints:**
- Check that the stream bridge (Terminal 2) is running and updating
  `latest_snapshot.xmi`
- Check that `MODEL_PATH` in `QueryRunner.java` matches the actual file path

**If it crashes immediately:**
- Check the Eclipse Console/Error Log for stack traces
- Common cause: missing plug-in dependencies — go back to Plug-ins tab and
  click **Add Required Plug-ins** again

---

### B8. See the results

While everything is running, you can see RSS violation edges in three ways:

**Option 1 — Browser live view:**
- Open `data\stream\live_view.html` in any browser
- It auto-refreshes and shows the scene graph with edges

**Option 2 — Check the XMI directly:**
```powershell
Get-Content "data\stream\latest_snapshot.xmi" | Select-String "rss_"
```
You should see lines like:
```xml
<edges type="rss_longitudinal" source="//@nodes.0" target="//@nodes.1"/>
```

**Option 3 — Watch the Eclipse Console output**
- The `[RSS]` prefixed lines show when violations are created/removed in real time

---

## Stopping Everything

1. **QueryRunner** — click the red square (Stop) in the Eclipse Console toolbar
2. **Scenario script** — it finishes on its own after ~300 ticks, or press Ctrl+C
3. **Stream bridge** — press Ctrl+C in Terminal 2
4. **CARLA** — close the 3D window or press Alt+F4

---

## Offline Testing (No CARLA)

You can test the VIATRA pipeline without a running CARLA server by creating a
mock XMI file:

```powershell
.\.venv\Scripts\Activate.ps1
python -c "
from src.carla_scenegraph_export import Node, build_xmi
nodes = [
    Node('Vehicle', 'ego', x=0, y=0, z=0, heading=0, speed=10, length=4.5, width=2.0, vx=10, vy=0),
    Node('Vehicle', 'lead', x=12, y=0, z=0, heading=0, speed=8, length=4.5, width=2.0, vx=8, vy=0),
    Node('Vehicle', 'adj', x=1, y=3, z=0, heading=0, speed=10, length=4.5, width=2.0, vx=9.8, vy=0.5),
]
xmi = build_xmi(nodes, [])
with open('data/stream/latest_snapshot.xmi', 'w') as f:
    f.write(xmi)
print('Mock snapshot written')
"
```

Then run QueryRunner in Eclipse (Step B7). It will detect:
- **Longitudinal violation:** ego → lead (gap=12m, RSS d_min≈13.6m at 10/8 m/s)

---

## What Was Changed (Reference)

| File | Change |
|------|--------|
| `SceneGraphModel/model/sceneGraphModel.ecore` | Added `vx`, `vy` (EDouble) to Vehicle |
| `SceneGraphModel/model/sceneGraphModel.genmodel` | Added genFeatures for `vx`, `vy` |
| `SceneGraphQueries/src/queries/scenegraphhelper.java` | Added 6 RSS helper methods |
| `SceneGraphQueries/src/queries/scenegraph.vql` | Added 4 RSS patterns |
| `SceneGraphQueries/plugin.xml` | Registered RSS + EgoFollowing query specs |
| `SceneGraphAPIQueries/src/apiqueries/QueryRunner.java` | Added RSS rules, fixed MODEL_PATH |
| `src/carla_scenegraph_export.py` | Exports `vx`, `vy` on Vehicle nodes |
| `src/rss_safety_check.py` | Python-side RSS checker (standalone) |

## RSS Parameters

| Parameter | Symbol | Value | Description |
|-----------|--------|-------|-------------|
| Reaction time | ρ | 0.5 s | Driver/system reaction delay |
| Max lon. accel | a_lon_max | 3.5 m/s² | Worst-case acceleration during ρ |
| Min lon. braking | b_lon_min | 4.0 m/s² | Ego's comfortable braking |
| Max lon. braking | b_lon_max | 8.0 m/s² | Lead's emergency braking |
| Max lat. accel | a_lat_max | 0.2 m/s² | Lateral drift during ρ |
| Min lat. braking | b_lat_min | 0.8 m/s² | Lateral correction braking |
| Lateral margin | μ | 0.1 m | Fluctuation margin |
