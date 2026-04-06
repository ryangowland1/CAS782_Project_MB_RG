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
from rss_safety_check import RSSParams, check_rss_safety

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


def edge_key(edge: Edge, nodes: List[Node]):
    if not (0 <= edge.source_index < len(nodes) and 0 <= edge.target_index < len(nodes)):
        return None
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
    curr = {k for edge in curr_edges if (k := edge_key(edge, curr_nodes)) is not None}
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

    # Edge style lookup: type -> (stroke color, stroke width, dash)
    edge_styles = {
        "rss_longitudinal": ("#dc2626", 5.0, ""),
        "rss_lateral":      ("#ea580c", 5.0, ""),
        "following":        ("#7c3aed", 3.5, "12,6"),
        "vehicle":          ("#738497", 2.5, ""),
        "lane":             ("#94a3b8", 1.8, "6,4"),
    }

    # Collect RSS violation info for the panel
    rss_violations: List[Dict[str, str]] = []

    # Python-side RSS checks (works without VIATRA/Eclipse)
    vehicles = [n for n in nodes if n.node_type == "Vehicle"]
    _rss_params = RSSParams()
    for i, ego in enumerate(vehicles):
        others = vehicles[:i] + vehicles[i+1:]
        for v in check_rss_safety(ego, others, _rss_params):
            rss_violations.append({
                "type": "Longitudinal" if v.rule == "longitudinal" else "Lateral",
                "source": v.ego_id,
                "target": v.other_id,
                "actual": f"{v.actual_distance:.1f}",
                "safe": f"{v.safe_distance:.1f}",
            })
    # Deduplicate (A->B and B->A may both fire)
    _seen_pairs: Set[Tuple[str, str, str]] = set()
    _deduped: List[Dict[str, str]] = []
    for v in rss_violations:
        pair = (v["type"], min(v["source"], v["target"]), max(v["source"], v["target"]))
        if pair not in _seen_pairs:
            _seen_pairs.add(pair)
            _deduped.append(v)
    rss_violations = _deduped

    line_parts: List[str] = []
    edge_text_parts: List[str] = []
    visible_edge_count = 0
    label_offset_counter: Dict[str, int] = {}  # per-edge-midpoint offset to stagger labels

    for edge, src, dst in iter_valid_edge_endpoints(edges, nodes):
        if src not in visible_node_ids or dst not in visible_node_ids:
            continue
        x1, y1 = mapped[src]
        x2, y2 = mapped[dst]

        stroke, sw, dash = edge_styles.get(edge.edge_type, ("#738497", 2.5, ""))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        line_parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-opacity="0.85" stroke-width="{sw}"{dash_attr} />'
        )

        # Build label
        if edge.edge_type.startswith("rss_"):
            label = edge.edge_type.replace("_", " ").upper()
            rss_violations.append({
                "type": "Longitudinal" if "longitudinal" in edge.edge_type else "Lateral",
                "source": src,
                "target": dst,
            })
        elif edge.edge_type == "vehicle":
            parts = []
            if edge.distance:
                parts.append(edge.distance)
            if edge.spatial:
                parts.append(edge.spatial)
            label = " | ".join(parts) if parts else "vehicle"
        elif edge.edge_type == "following":
            label = "following"
        else:
            label = edge.edge_type

        # Skip text label for lane edges - dashed gray style is enough
        if edge.edge_type != "lane":
            t = 0.35
            lx = x1 + (x2 - x1) * t
            ly = y1 + (y2 - y1) * t

            mid_key = f"{int(lx/30)},{int(ly/30)}"
            stagger = label_offset_counter.get(mid_key, 0)
            label_offset_counter[mid_key] = stagger + 1

            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < 1e-6:
                nx, ny = 0.0, -1.0
            else:
                nx, ny = -dy / length, dx / length

            base_offset = 18.0
            offset = base_offset + stagger * 20.0

            font_size = 20
            text_fill = stroke if edge.edge_type.startswith("rss_") else "#334155"

            edge_text_parts.append(
                f'<text x="{lx + nx * offset:.1f}" y="{ly + ny * offset:.1f}" '
                f'font-size="{font_size}" font-weight="{"700" if edge.edge_type.startswith("rss_") else "400"}" '
                f'fill="{text_fill}" stroke="#ffffff" stroke-width="2.5" paint-order="stroke" '
                f'text-anchor="middle">{label}</text>'
            )
        visible_edge_count += 1

    circle_parts: List[str] = []
    node_colors = {"Vehicle": "#1f77b4", "Pedestrian": "#d62728"}
    for node in visible_nodes:
        node_id = node.external_id
        x, y = mapped[node_id]
        color = node_colors.get(node.node_type, "#2ca02c")

        if node.node_type == "Vehicle":
            circle_parts.append(
                f'<rect x="{x - 10:.1f}" y="{y - 10:.1f}" width="20" height="20" rx="4" fill="{color}" />'
            )
            # Speed label under the vehicle
            speed_str = f"{node.speed:.1f} m/s" if node.speed and node.speed > 0.01 else "stopped"
            circle_parts.append(
                f'<text x="{x:.1f}" y="{y + 36:.1f}" font-size="14" fill="#64748b" text-anchor="middle">{speed_str}</text>'
            )
        else:
            circle_parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{color}" />'
            )

        # Node label - offset above-left for vehicles, above for roads
        label_text = f"{node.node_type}:{node_id}"
        circle_parts.append(
            f'<text x="{x:.1f}" y="{y - 20:.1f}" font-size="16" fill="#1a1a1a" '
            f'text-anchor="middle" font-weight="500">{label_text}</text>'
        )

    # RSS panel rows
    rss_rows = ""
    if rss_violations:
        for v in rss_violations:
            badge_color = "#dc2626" if v["type"] == "Longitudinal" else "#ea580c"
            dist_info = ""
            if "actual" in v and "safe" in v:
                dist_info = f' <span style="font-size:11px;color:#64748b;">({v["actual"]}m / {v["safe"]}m safe)</span>'
            rss_rows += (
                f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">'
                f'<span style="background:{badge_color};color:white;padding:2px 8px;border-radius:4px;'
                f'font-size:12px;font-weight:600;">{v["type"]}</span>'
                f'<span style="font-size:13px;color:#1e293b;">{v["source"]} &rarr; {v["target"]}{dist_info}</span>'
                f'</div>'
            )
    else:
        rss_rows = '<div style="color:#16a34a;font-size:14px;font-weight:600;">No RSS violations</div>'

    vehicle_count = sum(1 for n in nodes if n.node_type == "Vehicle")
    rss_lon_count = sum(1 for v in rss_violations if v["type"] == "Longitudinal")
    rss_lat_count = sum(1 for v in rss_violations if v["type"] == "Lateral")

    html = f"""<!doctype html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta http-equiv="refresh" content="0.1" />
    <title>Scene Graph Live View</title>
    <style>
        html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
        body {{ font-family: Segoe UI, Tahoma, sans-serif; background: #f3f6f9; }}
        .wrap {{
            width: 100vw; height: 100vh; margin: 0; background: white;
            display: flex; flex-direction: column; box-sizing: border-box;
        }}
        .head {{
            padding: 12px 18px; border-bottom: 1px solid #e5e7eb;
            flex: 0 0 auto; display: flex; justify-content: space-between; align-items: flex-start;
        }}
        .head-left {{ flex: 1; }}
        .head-left strong {{ font-size: 22px; font-weight: 700; }}
        .meta {{ color: #3f4b5b; font-size: 14px; margin-top: 4px; }}
        .rss-panel {{
            flex: 0 0 auto; min-width: 280px; max-width: 400px;
            background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px;
            padding: 10px 14px; margin-left: 16px;
        }}
        .rss-panel.safe {{ background: #f0fdf4; border-color: #bbf7d0; }}
        .rss-title {{
            font-size: 14px; font-weight: 700; color: #1e293b; margin-bottom: 6px;
            display: flex; align-items: center; gap: 6px;
        }}
        .rss-count {{ font-size: 12px; color: #64748b; margin-bottom: 4px; }}
        svg {{ display: block; width: 100%; flex: 1 1 auto; background: #fcfdff; }}
        .legend {{
            display: flex; gap: 16px; padding: 6px 18px; border-top: 1px solid #e5e7eb;
            flex: 0 0 auto; font-size: 12px; color: #64748b; align-items: center;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 4px; }}
        .legend-swatch {{ width: 20px; height: 3px; border-radius: 2px; }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="head">
            <div class="head-left">
                <strong>CARLA Scene Graph Live View</strong>
                <div class="meta">Tick: {tick} | Vehicles: {vehicle_count} | Nodes: {len(visible_node_ids)} | Edges: {visible_edge_count} | Auto-refresh: 100ms</div>
            </div>
            <div class="rss-panel {'safe' if not rss_violations else ''}">
                <div class="rss-title">
                    {'&#x26A0;' if rss_violations else '&#x2705;'} RSS Safety Status
                </div>
                <div class="rss-count">Longitudinal: {rss_lon_count} | Lateral: {rss_lat_count}</div>
                {rss_rows}
            </div>
        </div>
        <svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
            {''.join(line_parts)}
            {''.join(edge_text_parts)}
            {''.join(circle_parts)}
        </svg>
        <div class="legend">
            <div class="legend-item"><div class="legend-swatch" style="background:#dc2626;height:4px;"></div> RSS Longitudinal</div>
            <div class="legend-item"><div class="legend-swatch" style="background:#ea580c;height:4px;"></div> RSS Lateral</div>
            <div class="legend-item"><div class="legend-swatch" style="background:#7c3aed;"></div> Following</div>
            <div class="legend-item"><div class="legend-swatch" style="background:#738497;"></div> Vehicle proximity</div>
            <div class="legend-item"><div class="legend-swatch" style="background:#94a3b8;" ></div> Lane</div>
        </div>
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
        prev_edges = {k for edge in edges if (k := edge_key(edge, nodes)) is not None}

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
