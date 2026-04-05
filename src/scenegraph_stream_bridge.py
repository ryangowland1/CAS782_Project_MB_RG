#!/usr/bin/env python3
"""Continuously export CARLA scene graphs as XMI snapshots + JSONL change events.

Outputs:
- data/stream/latest_snapshot.xmi
- data/stream/events.jsonl
- data/stream/live_view.html
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from carla_scenegraph_export import Edge, Node, collect_carla_nodes, collect_mock_nodes, write_scene_xmi

try:
    portalocker = importlib.import_module("portalocker")
except ImportError:
    portalocker = None


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


def iter_valid_edge_endpoints(edges: List[Edge], nodes: List[Node]):
    for edge in edges:
        if not (0 <= edge.source_index < len(nodes) and 0 <= edge.target_index < len(nodes)):
            continue
        yield edge, nodes[edge.source_index].external_id, nodes[edge.target_index].external_id


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
        "removed": [{"type": t, "source": s, "target": d, "distance": i, "spatial": j} for t, s, d, i, j in removed],
    }


def to_view_space(nodes: List[Node], width: int = 1600, height: int = 1000) -> Dict[str, Tuple[float, float]]:
    if not nodes:
        return {}

    ordered_nodes = sorted(nodes, key=lambda n: (n.node_type, n.external_id))
    count = len(ordered_nodes)

    cx = width * 0.5
    cy = height * 0.55
    mapped: Dict[str, Tuple[float, float]] = {}

    if count == 1:
        mapped[ordered_nodes[0].external_id] = (cx, cy)
        return mapped

    if count == 2:
        spread = min(width * 0.38, 620.0)
        points = [(cx - spread / 2.0, cy), (cx + spread / 2.0, cy)]
    elif count == 3:
        # Equilateral triangle for 3 active nodes.
        side = min(width, height) * 0.58
        h = side * math.sqrt(3.0) / 2.0
        points = [
            (cx, cy - h / 2.0),
            (cx - side / 2.0, cy + h / 2.0),
            (cx + side / 2.0, cy + h / 2.0),
        ]
    elif count == 4:
        # Axis-aligned square for 4 active nodes.
        half = min(width, height) * 0.24
        points = [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx - half, cy + half),
            (cx + half, cy + half),
        ]
    elif count <= 12:
        # Small sets: regular polygon ring so spacing scales with active nodes.
        radius = min(width, height) * (0.30 + 0.016 * count)
        points = []
        for idx in range(count):
            angle = -math.pi / 2.0 + (2.0 * math.pi * idx) / count
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    else:
        # Larger sets: adaptive grid whose spacing depends on active node count.
        cols = math.ceil(math.sqrt(count))
        rows = math.ceil(count / cols)
        usable_width = width * 0.90
        usable_height = height * 0.90
        start_x = (width - usable_width) / 2.0
        start_y = (height - usable_height) / 2.0
        dx = usable_width / max(cols - 1, 1)
        dy = usable_height / max(rows - 1, 1)
        points = []
        for idx in range(count):
            gx = idx % cols
            gy = idx // cols
            points.append((start_x + gx * dx, start_y + gy * dy))

    min_x = width * 0.02
    max_x = width * 0.94
    min_y = height * 0.03
    max_y = height * 0.97
    for node, (x, y) in zip(ordered_nodes, points):
        mapped[node.external_id] = (min(max(x, min_x), max_x), min(max(y, min_y), max_y))

    return mapped


def write_live_view_html(output_path: Path, nodes: List[Node], edges: List[Edge], tick: int) -> None:
    node_by_id = {n.external_id: n for n in nodes}

    connected_lane_ids: Set[str] = {
        node_id
        for _edge, src_id, dst_id in iter_valid_edge_endpoints(edges, nodes)
        for node_id in (src_id, dst_id)
        if node_by_id.get(node_id) is not None and node_by_id[node_id].node_type == "RoadSegment"
    }

    visible_node_ids: Set[str] = {
        node.external_id
        for node in nodes
        if node.node_type != "RoadSegment" or node.external_id in connected_lane_ids
    }

    visible_nodes = [node_by_id[node_id] for node_id in sorted(visible_node_ids)]
    mapped = to_view_space(visible_nodes)

    line_parts: List[str] = []
    edge_text_parts: List[str] = []
    visible_edge_count = 0
    for edge, src, dst in iter_valid_edge_endpoints(edges, nodes):
        if src not in visible_node_ids or dst not in visible_node_ids:
            continue
        x1, y1 = mapped[src]
        x2, y2 = mapped[dst]
        line_parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#738497" stroke-opacity="0.80" stroke-width="4.2" />'
        )

        label_parts: List[str] = [edge.edge_type]
        if edge.distance:
            label_parts.append(f"dist={edge.distance}")
        if edge.spatial:
            label_parts.append(f"spatial={edge.spatial}")

        label = " | ".join(label_parts)
        mx = (x1 + x2) / 2.0
        my = (y1 + y2) / 2.0

        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-6:
            nx, ny = 0.0, -1.0
        else:
            nx, ny = -dy / length, dx / length

        src_type = node_by_id[src].node_type
        dst_type = node_by_id[dst].node_type
        if src_type == "Vehicle" or dst_type == "Vehicle":
            offset = 40.0
        else:
            offset = 28.0

        edge_text_parts.append(
            f'<text x="{mx + nx * offset:.1f}" y="{my + ny * offset:.1f}" font-size="28" fill="#334155" '
            f'stroke="#ffffff" stroke-width="1.4" paint-order="stroke">{label}</text>'
        )
        visible_edge_count += 1

    circle_parts: List[str] = []
    node_colors = {"Vehicle": "#1f77b4", "Pedestrian": "#d62728"}
    for node in visible_nodes:
        node_id = node.external_id
        x, y = mapped[node_id]
        color = node_colors.get(node.node_type, "#2ca02c")
        circle_parts.append(
            f'<rect x="{x - 9:.1f}" y="{y - 15:.1f}" width="18" height="30" rx="4" fill="{color}" />'
            if node.node_type == "Vehicle"
            else f'<circle cx="{x:.1f}" cy="{y:.1f}" r="14" fill="{color}" />'
        )

        circle_parts.append(
            f'<text x="{x + 26:.1f}" y="{y - 26:.1f}" font-size="34" fill="#1a1a1a">{node.node_type}:{node_id}</text>'
        )

    html = f"""<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <meta http-equiv=\"refresh\" content=\"0.1\" />
    <title>Scene Graph Live View</title>
    <style>
        html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
        body {{ font-family: Segoe UI, Tahoma, sans-serif; background: #f3f6f9; }}
        .wrap {{
            width: 100vw;
            height: 100vh;
            margin: 0;
            background: white;
            border: 0;
            border-radius: 0;
            display: flex;
            flex-direction: column;
            box-sizing: border-box;
        }}
        .head {{ padding: 18px 22px; border-bottom: 1px solid #e5e7eb; flex: 0 0 auto; }}
        .head strong {{ font-size: 36px; font-weight: 700; }}
        .meta {{ color: #3f4b5b; font-size: 28px; margin-top: 6px; }}
        svg {{ display: block; width: 100%; height: 100%; flex: 1 1 auto; background: #fcfdff; }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"head\">
            <strong>CARLA Scene Graph Live View</strong>
            <div class=\"meta\">Tick: {tick} | Nodes: {len(visible_node_ids)} | Edges: {visible_edge_count} | Auto-refresh: 100ms</div>
        </div>
        <svg viewBox=\"0 0 1600 1000\" preserveAspectRatio=\"none\" xmlns=\"http://www.w3.org/2000/svg\">
            {''.join(line_parts)}
                {''.join(edge_text_parts)}
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
        return [
            Node(
                node_type=node.node_type,
                external_id=node.external_id,
                x=node.x + math.cos(tick * 0.5 + idx),
                y=node.y + math.sin(tick * 0.5 + idx),
                z=node.z,
                heading=node.heading,
                speed=node.speed,
                length=node.length,
                width=node.width,
            )
            for idx, node in enumerate(base)
        ]

    return collect_carla_nodes(host, port, timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream CARLA scene graphs to XMI + JSONL")
    parser.add_argument("--out-dir", default="data/stream", help="Output stream directory")
    parser.add_argument("--scene-name", default="CARLA_Stream", help="Scene name for XMI files")
    parser.add_argument("--interval", type=float, default=0.1, help="Seconds between snapshots")
    parser.add_argument("--ticks", type=int, default=0, help="Number of ticks (0 = infinite)")
    parser.add_argument("--carla-address", default="127.0.0.1", help="CARLA host")
    parser.add_argument("--port", type=int, default=2000, help="CARLA RPC port")
    parser.add_argument("--timeout", type=float, default=5.0, help="CARLA RPC timeout")
    parser.add_argument("--mock", action="store_true", help="Run without CARLA using synthetic movement")
    return parser.parse_args()


def read_xml_with_retry(path, retries=5, delay=0.05):
    for attempt in range(retries):
        try:
            with open(path, "rb") as f:
                if portalocker is None:
                    return ET.parse(f)

                try:
                    # Match Java tryLock(): exclusive + non-blocking
                    portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
                except portalocker.exceptions.LockException:
                    if attempt == retries - 1:
                        print(f"File is locked after {retries} attempts: {path}")
                        return None
                    time.sleep(delay)
                    continue

                try:
                    return ET.parse(f)
                finally:
                    portalocker.unlock(f)

        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(delay)

    raise RuntimeError("Unexpected XML read retry state")


def load_edges_from_snapshot(latest_path: Path) -> List[Edge]:
    if not latest_path.exists():
        return []

    edges: List[Edge] = []
    try:
        tree = read_xml_with_retry(latest_path)
        if tree is None:
            raise ET.ParseError("Latest snapshot is temporarily unavailable")

        root = tree.getroot()
        for edge_elem in root.findall("edges"):
            source_ref = edge_elem.get("source")
            target_ref = edge_elem.get("target")
            if not source_ref or not target_ref:
                continue

            try:
                source_index = int(source_ref.rsplit(".", 1)[-1])
                target_index = int(target_ref.rsplit(".", 1)[-1])
            except (ValueError, TypeError):
                continue

            edges.append(
                Edge(
                    edge_type=edge_elem.get("type") or "",
                    distance=edge_elem.get("distance") or "",
                    spatial=edge_elem.get("spatial") or "",
                    source_index=source_index,
                    target_index=target_index,
                )
            )
    except ET.ParseError:
        return []

    return edges


def persist_event(event: Dict[str, object], events_path: Path, state_path: Path) -> None:
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    state_path.write_text(json.dumps(event, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()

    out_dir = Path(args.out_dir)
    latest_path = out_dir / "latest_snapshot.xmi"
    events_path = out_dir / "events.jsonl"
    state_path = out_dir / "current_state.json"
    view_path = out_dir / "live_view.html"

    out_dir.mkdir(parents=True, exist_ok=True)

    prev_nodes: Dict[str, Dict[str, object]] = {}
    prev_edges: Set[Tuple[str, str, str, str, str]] = set()

    tick = 0
    while True:
        tick += 1
        nodes = collect_nodes(args.mock, args.carla_address, args.port, args.timeout, tick)

        edges = load_edges_from_snapshot(latest_path)

        # Write only the rolling latest snapshot.
        write_scene_xmi(args.scene_name, nodes, edges, latest_path)
        write_live_view_html(view_path, nodes, edges, tick)

        node_diff = diff_nodes(prev_nodes, nodes)
        edge_diff = diff_edges(prev_edges, edges, nodes)

        event = {
            "timestamp": now_iso(),
            "tick": tick,
            "snapshot": str(latest_path).replace("\\", "/"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_changes": node_diff,
            "edge_changes": edge_diff,
        }

        persist_event(event, events_path, state_path)

        prev_nodes = {node.external_id: normalize_node(node) for node in nodes}
        prev_edges = {edge_key(edge, nodes) for edge in edges}

        print(
            f"tick={tick} nodes={len(nodes)} edges={len(edges)} snapshot={latest_path}",
            flush=True,
        )

        if args.ticks > 0 and tick >= args.ticks:
            break

        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
