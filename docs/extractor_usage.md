# CARLA Scene Graph Exporter Usage

This repository includes a minimal extractor at `src/carla_scenegraph_export.py`.
It exports a CARLA world snapshot to XMI conforming to `model/SceneGraph.ecore`.

## 1. Quick test without CARLA (`--mock`)

```powershell
python .\src\carla_scenegraph_export.py --mock --output .\data\scene_snapshot.xmi
```

## 2. Run against CARLA server

Start CARLA (`make launch`) and run:

```powershell
python .\src\carla_scenegraph_export.py --host 127.0.0.1 --port 2000 --output .\data\scene_snapshot.xmi
```

Optional parameters:

- `--scene-name`: root scene name in output XMI
- `--proximity-threshold`: controls generated proximity edges
- `--timeout`: CARLA RPC timeout in seconds

## 3. Expected output

- XMI file in `data/scene_snapshot.xmi`
- `nodes` include:
  - `Vehicle`
  - `Pedestrian`
- `edges` include:
  - `proximity` edges based on Euclidean distance threshold

## 4. Eclipse/VIATRA import

1. Ensure `model/SceneGraph.ecore` is in your Eclipse modeling project.
2. Import/open the generated `.xmi` file.
3. Run `queries/scenegraph.vql` patterns on the loaded model.
