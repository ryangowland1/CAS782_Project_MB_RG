#!/usr/bin/env python3
"""Continuously export CARLA scene graphs as XMI snapshots + JSONL change events.

Outputs:
- data/stream/snapshots/snapshot_XXXXXX.xmi
- data/stream/latest_snapshot.xmi
- data/stream/events.jsonl
- data/stream/live_view.html
"""

from __future__ import annotations

import argparse
import json
import math
import portalocker
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from carla_scenegraph_export import Edge, Node, build_edges, collect_carla_nodes, collect_mock_nodes, write_scene_xmi


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_node(node: Node) -> Dict[str, object]:
    return {
        "node_type": node.node_type,
        "external_id": node.external_id,
        "x": round(node.x, 4),
        "y": round(node.y, 4),
        "z": round(node.z, 4),
        "heading": round(node.heading, 4),
        "speed": None if node.speed is None else round(node.speed, 4),
        "length": None if node.length is None else round(node.length, 4),
        "width": None if node.width is None else round(node.width, 4),
    }


def edge_key(edge: Edge, nodes: List[Node]) -> Tuple[str, str, str, str, str]:
    src = nodes[edge.source_index].external_id
    dst = nodes[edge.target_index].external_id
    if src > dst:
        src, dst = dst, src
    return (edge.edge_type, src, dst, edge.distance, edge.spatial)


def diff_nodes(prev: Dict[str, Dict[str, object]], curr_nodes: List[Node]) -> Dict[str, List[object]]:
    curr = {node.external_id: normalize_node(node) for node in curr_nodes}

    prev_ids = set(prev)
    curr_ids = set(curr)

    added: List[object] = [curr[i] for i in sorted(curr_ids - prev_ids)]
    removed: List[object] = [prev[i] for i in sorted(prev_ids - curr_ids)]

    updated: List[object] = []
    for node_id in sorted(curr_ids & prev_ids):
        before = prev[node_id]
        after = curr[node_id]
        if before != after:
            updated.append({"before": before, "after": after})

    return {"added": added, "removed": removed, "updated": updated}


def diff_edges(prev: Set[Tuple[str, str, str, str, str]], curr_edges: List[Edge], curr_nodes: List[Node]) -> Dict[str, List[object]]:
    curr = {edge_key(edge, curr_nodes) for edge in curr_edges}
    added = sorted(curr - prev)
    removed = sorted(prev - curr)
    return {
        "added": [{"type": t, "source": s, "target": d, "distance": i, "spatial": j} for t, s, d, i, j in added],
        "removed": [{"type": t, "source": s, "target": d , "distance": i, "spatial": j} for t, s, d, i, j in removed],
    }


def to_view_space(nodes: List[Node], width: int = 960, height: int = 540) -> Dict[str, Tuple[float, float]]:
    if not nodes:
        return {}

    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    margin = 40.0
    scale_x = (width - 2 * margin) / span_x
    scale_y = (height - 2 * margin) / span_y
    scale = min(scale_x, scale_y)

    mapped: Dict[str, Tuple[float, float]] = {}
    for node in nodes:
        vx = margin + (node.x - min_x) * scale
        vy = height - (margin + (node.y - min_y) * scale)
        mapped[node.external_id] = (vx, vy)
    return mapped

def compute_view_scale(nodes: List[Node], width: int = 960, height: int = 540) -> float:
    """Compute world-to-view scale factor (px per meter)."""
    if not nodes:
        return 1.0

    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    span_x = max(max(xs) - min(xs), 1.0)
    span_y = max(max(ys) - min(ys), 1.0)

    margin = 40.0
    scale_x = (width - 2 * margin) / span_x
    scale_y = (height - 2 * margin) / span_y
    return min(scale_x, scale_y)


def write_live_view_html(output_path: Path, nodes: List[Node], edges: List[Edge], tick: int) -> None:
        mapped = to_view_space(nodes)
        view_scale = compute_view_scale(nodes)
        node_by_id = {n.external_id: n for n in nodes}

        lane_parts: List[str] = []
        for node in nodes:
                if node.node_type != "RoadSegment":
                        continue
                if node.length is None or node.width is None:
                        continue

                center = mapped.get(node.external_id)
                if center is None:
                        continue

                cx, cy = center
                lane_len_px = max(node.length * view_scale, 6.0)
                lane_width_px = max(node.width * view_scale, 2.0)
                x = cx - lane_len_px / 2.0
                y = cy - lane_width_px / 2.0
                angle_deg = -math.degrees(node.heading)

                lane_parts.append(
                        f'<rect x="{x:.1f}" y="{y:.1f}" width="{lane_len_px:.1f}" height="{lane_width_px:.1f}" '
                        f'rx="1.5" fill="#81c784" fill-opacity="0.28" stroke="#2e7d32" stroke-width="0.9" '
                        f'transform="rotate({angle_deg:.2f} {cx:.1f} {cy:.1f})" />'
                )

        line_parts: List[str] = []
        for edge in edges:
                src = nodes[edge.source_index].external_id
                dst = nodes[edge.target_index].external_id
                x1, y1 = mapped[src]
                x2, y2 = mapped[dst]
                line_parts.append(
                        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#5d6d7e" stroke-width="1.5" />'
                )

        circle_parts: List[str] = []
        for node_id, (x, y) in mapped.items():
                node = node_by_id[node_id]
                if node.node_type == "Vehicle":
                        color = "#1f77b4"  # Blue
                elif node.node_type == "Pedestrian":
                        color = "#d62728"  # Red
                else:  # RoadSegment or other types
                        color = "#2ca02c"  # Green
                circle_parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}" />')
                circle_parts.append(
                        f'<text x="{x + 10:.1f}" y="{y - 10:.1f}" font-size="12" fill="#1a1a1a">{node.node_type}:{node_id}</text>'
                )

        html = f"""<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta http-equiv=\"refresh\" content=\"0.2\" />
    <title>Scene Graph Live View</title>
    <style>
        body {{ font-family: Segoe UI, Tahoma, sans-serif; background: #f3f6f9; margin: 0; }}
        .wrap {{ max-width: 1000px; margin: 24px auto; background: white; border: 1px solid #d0d7de; border-radius: 10px; }}
        .head {{ padding: 14px 16px; border-bottom: 1px solid #e5e7eb; }}
        .meta {{ color: #3f4b5b; font-size: 14px; }}
        svg {{ display: block; width: 100%; height: auto; background: #fcfdff; }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"head\">
            <strong>CARLA Scene Graph Live View</strong>
            <div class=\"meta\">Tick: {tick} | Nodes: {len(nodes)} | Edges: {len(edges)} | Auto-refresh: 200ms</div>
        </div>
        <svg viewBox=\"0 0 960 540\" xmlns=\"http://www.w3.org/2000/svg\">
            {''.join(lane_parts)}
            {''.join(line_parts)}
            {''.join(circle_parts)}
        </svg>
    </div>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")


def collect_nodes(mock: bool, host: str, port: int, timeout: float, tick: int) -> List[Node]:
    if mock:
        base = collect_mock_nodes()
        moved: List[Node] = []
        for idx, node in enumerate(base):
            phase = tick * 0.2 + idx
            moved.append(
                Node(
                    node_type=node.node_type,
                    external_id=node.external_id,
                    x=node.x + math.cos(phase),
                    y=node.y + math.sin(phase),
                    z=node.z,
                    heading=node.heading,
                    speed=node.speed,
                    length=node.length,
                    width=node.width,
                )
            )
        return moved

    return collect_carla_nodes(host, port, timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream CARLA scene graphs to XMI + JSONL")
    parser.add_argument("--out-dir", default="data/stream", help="Output stream directory")
    parser.add_argument("--scene-name", default="CARLA_Stream", help="Scene name for XMI files")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between snapshots")
    parser.add_argument("--ticks", type=int, default=0, help="Number of ticks (0 = infinite)")
    parser.add_argument("--carla-address", default="127.0.0.1", help="CARLA host")
    parser.add_argument("--port", type=int, default=2000, help="CARLA RPC port")
    parser.add_argument("--timeout", type=float, default=5.0, help="CARLA RPC timeout")
    parser.add_argument("--proximity-threshold", type=float, default=12.0, help="Edge creation threshold")
    parser.add_argument("--mock", action="store_true", help="Run without CARLA using synthetic movement")
    return parser.parse_args()

def read_xml_with_retry(path, retries=5, delay=0.05):
    last_exception = None

    for attempt in range(retries):
        try:
            with open(path, 'rb') as f:
                try:
                    # Match Java tryLock(): exclusive + non-blocking
                    portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
                except portalocker.exceptions.LockException as e:
                    last_exception = e
                    if attempt == retries - 1:
                        print(f"File is locked after {retries} attempts: {path}")
                        return None
                    time.sleep(delay)
                    continue

                try:
                    return ET.parse(f)
                finally:
                    portalocker.unlock(f)

        except Exception as e:
            last_exception = e
            if attempt == retries - 1:
                raise
            time.sleep(delay)

    raise Exception("Unexpected failure") from last_exception

def main() -> int:
    args = parse_args()

    out_dir = Path(args.out_dir)
    snap_dir = out_dir / "snapshots"
    latest_path = out_dir / "latest_snapshot.xmi"
    events_path = out_dir / "events.jsonl"
    state_path = out_dir / "current_state.json"
    view_path = out_dir / "live_view.html"

    snap_dir.mkdir(parents=True, exist_ok=True)

    prev_nodes: Dict[str, Dict[str, object]] = {}
    prev_edges: Set[Tuple[str, str, str, str, str]] = set()

    tick = 0
    while True:
        tick += 1
        nodes = collect_nodes(args.mock, args.carla_address, args.port, args.timeout, tick)
        new_edges = [] # build_edges(nodes, args.proximity_threshold)

        # Read existing edges from latest XMI
        edges: List[Edge] = []
        if latest_path.exists():
            try:
                tree = read_xml_with_retry(latest_path)
                if tree is None:
                    raise ET.ParseError("Latest snapshot is temporarily unavailable")
                root = tree.getroot()
                for edge_elem in root.findall("edges"):
                    edge_type = edge_elem.get("type") or ""
                    distance = edge_elem.get("distance") or ""
                    spatial = edge_elem.get("spatial") or ""
                    source_ref = edge_elem.get("source")
                    target_ref = edge_elem.get("target")

                    # Ignore malformed persisted edges rather than crashing stream updates.
                    if not source_ref or not target_ref:
                        continue

                    try:
                        source_index = int(source_ref.rsplit(".", 1)[-1])
                        target_index = int(target_ref.rsplit(".", 1)[-1])
                    except (ValueError, TypeError):
                        continue

                    edges.append(
                        Edge(
                            edge_type=edge_type,
                            distance=distance,
                            spatial=spatial,
                            source_index=source_index,
                            target_index=target_index,
                        )
                    )
            except ET.ParseError:
                # If file is corrupted or empty, fallback to new edges
                edges = []

        # Merge new edges with existing ones, avoiding duplicates
        existing_keys = {(e.source_index, e.target_index, e.edge_type, e.distance, e.spatial or "") for e in edges}
        for e in new_edges:
            key = (e.source_index, e.target_index, e.edge_type, e.distance, e.spatial or "")
            if key not in existing_keys:
                edges.append(e)
                existing_keys.add(key)

        snapshot_name = f"snapshot_{tick:06d}.xmi"
        snapshot_path = snap_dir / snapshot_name
        # Write scene with merged edges
        write_scene_xmi(args.scene_name, nodes, edges, latest_path)
        write_live_view_html(view_path, nodes, edges, tick)

        node_diff = diff_nodes(prev_nodes, nodes)
        edge_diff = diff_edges(prev_edges, edges, nodes)

        event = {
            "timestamp": now_iso(),
            "tick": tick,
            "snapshot": str(snapshot_path).replace("\\", "/"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_changes": node_diff,
            "edge_changes": edge_diff,
        }

        with events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        state_path.write_text(json.dumps(event, indent=2), encoding="utf-8")

        prev_nodes = {node.external_id: normalize_node(node) for node in nodes}
        prev_edges = {edge_key(edge, nodes) for edge in edges}

        print(
            f"tick={tick} nodes={len(nodes)} edges={len(edges)} snapshot={snapshot_name}",
            flush=True,
        )

        if args.ticks > 0 and tick >= args.ticks:
            break

        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
