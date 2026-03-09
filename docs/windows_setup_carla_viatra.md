# Windows Setup: CARLA 0.9.16 + VIATRA

This guide bootstraps a Windows development environment for a CARLA-driven scene graph pipeline with VIATRA incremental queries and transformations.

## 1. System Requirements

- 64-bit Windows machine
- Recommended: dedicated GPU with >= 8 GB VRAM
- Free disk space: about 165 GB for CARLA + Unreal toolchain
- Open ports: `2000`, `2001` (default CARLA server ports)

## 2. Install Prerequisites

Install and add to PATH:

- Git
- CMake (3.15+)
- GNU Make 3.81 (important for CARLA Windows build compatibility)
- 7-Zip
- Python 3 (x64)
- Visual Studio 2022 (Desktop development with C++)

Then validate in a new terminal:

```powershell
git --version
cmake --version
make --version
python --version
```

## 3. Build Unreal Engine (CARLA fork)

Reference: CARLA Windows build docs

1. Clone Unreal Engine CARLA fork near drive root (short path helps avoid Windows path length issues):

```powershell
cd C:\
mkdir carla-src -ErrorAction SilentlyContinue
cd carla-src
git clone --depth 1 -b carla https://github.com/CarlaUnreal/UnrealEngine.git
```

2. Build Unreal fork:

```powershell
cd C:\carla-src\UnrealEngine
.\Setup.bat
.\GenerateProjectFiles.bat
```

3. Open `UE4.sln` in Visual Studio 2022 and build target `UE4` with:

- Configuration: `Development Editor`
- Platform: `Win64`

4. Set system environment variable `UE4_ROOT` to your Unreal Engine folder path.

## 4. Build CARLA

1. Clone CARLA source branch and fetch assets:

```powershell
cd C:\carla-src
git clone -b ue4-dev https://github.com/carla-simulator/carla.git
cd carla
.\Update.bat
```

2. Use `x64 Native Tools Command Prompt for VS 2022` and run:

```bat
make PythonAPI
make launch
```

3. In another terminal, verify examples:

```powershell
cd C:\carla-src\carla\PythonAPI\examples
python -m pip install -r requirements.txt
python generate_traffic.py
```

## 5. Install Eclipse + VIATRA

1. Install Eclipse Modeling Tools (recommended).
2. In Eclipse: `Help -> Install New Software...`
3. Add update site:

- `http://download.eclipse.org/viatra/updates/release/latest`

4. Install feature:

- `VIATRA Query and Transformation SDK`

5. Restart Eclipse.

Notes:

- For older release compatibility, use versioned update sites from VIATRA downloads.
- If installing from zipped offline update sites, ensure matching Xtext version.

## 6. Repository Bootstrap

From this repository root:

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows.ps1
```

The script checks local prerequisites and prints actionable next steps.

## 7. First Integration Target

After CARLA and VIATRA are installed:

1. Generate initial scene graph model from CARLA world snapshot.
2. Keep model synchronized using stream updates from actor/sensor events.
3. Run VIATRA incremental graph queries over the synchronized model.
4. Apply VIATRA transformations to derive digital twin state and alerts.

## 8. Export First Scene Snapshot

Use the repository extractor to produce your first `.xmi` scene graph.

Quick mock run (no CARLA required):

```powershell
python .\src\carla_scenegraph_export.py --mock --output .\data\scene_snapshot.xmi
```

Live CARLA run (CARLA server running on default host/port):

```powershell
python .\src\carla_scenegraph_export.py --host 127.0.0.1 --port 2000 --output .\data\scene_snapshot.xmi
```

See `docs/extractor_usage.md` for details.

## 9. End-to-End Boot And Stream Runbook

Use this when you are ready to boot CARLA and push scene graph updates to VIATRA.

1. Start CARLA server:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_carla_server.ps1 -CarlaRoot C:\carla-src\carla
```

2. Start scene graph stream bridge (live CARLA):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_scenegraph_stream.ps1 -Interval 1.0 -CarlaAddress 127.0.0.1 -Port 2000
```

3. Open live graph visualization:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\open_live_view.ps1
```

4. In Eclipse + VIATRA, load:

- `model/SceneGraph.ecore`
- `queries/scenegraph.vql`
- `data/stream/latest_snapshot.xmi`

5. Use `data/stream/events.jsonl` as the event stream contract for incremental model updates.

Optional one-command mock startup for development:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev_up.ps1 -Mock -Interval 1.0
```
