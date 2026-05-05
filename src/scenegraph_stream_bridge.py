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
from typing import Dict, List, Optional, Set, Tuple

from carla_scenegraph_export import Edge, Node, collect_carla_nodes, collect_mock_nodes, write_scene_xmi
from rss_safety_check import RSSParams, gather_rss_checks

try:
    portalocker = importlib.import_module("portalocker")
except ImportError:
    portalocker = None


LANE_WIDTH_M = 3.5
LANE_LENGTH_M = 25.0


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
    cy = height * 0.44
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

    vehicle_name_by_id = {
        "147": "ego",
        "148": "lead",
    }

    def display_id(node_id: str) -> str:
        return vehicle_name_by_id.get(node_id, node_id)

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
        "rss_longitudinal": ("#dc2626", 7.0, ""),
        "rss_lateral":      ("#ea580c", 7.0, ""),
        "vehicle":          ("#738497", 4.0, ""),
        "lane":             ("#94a3b8", 3.0, "6,4"),
    }

    # Collect RSS violation info for the panel
    rss_violations: List[Dict[str, str]] = []

    # Python-side RSS checks (works without VIATRA/Eclipse)
    vehicles = [n for n in nodes if n.node_type == "Vehicle"]
    _rss_params = RSSParams()
    for i, ego in enumerate(vehicles):
        others = vehicles[:i] + vehicles[i+1:]
        for chk in gather_rss_checks(ego, others, _rss_params):
            rss_violations.append({
                "check_source": "python",
                "type": chk["type"],
                "source": chk["ego_id"],
                "target": chk["other_id"],
                "actual": f"{chk['actual']:.1f}",
                "safe": f"{chk['safe']:.1f}",
                "violation": bool(chk.get("violation", False)),
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

        # Draw connector directly between node centers (natural center alignment)

        stroke, sw, dash = edge_styles.get(edge.edge_type, ("#738497", 4.0, ""))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        line_parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-opacity="0.85" stroke-width="{sw}"{dash_attr} />'
        )

        # Build label
        if edge.edge_type.startswith("rss_"):
            label = edge.edge_type.replace("_", " ").upper()
            rss_violations.append({
                "check_source": "viatra",
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
        else:
            label = edge.edge_type

        # Skip text label for lane edges - dashed gray style is enough
        if edge.edge_type != "lane":
            # Center label at the true midpoint of the connector
            lx = (x1 + x2) / 2.0
            ly = (y1 + y2) / 2.0

            mid_key = f"{int(lx/30)},{int(ly/30)}"
            stagger = label_offset_counter.get(mid_key, 0)
            label_offset_counter[mid_key] = stagger + 1

            # Stagger multiple labels at the same midpoint by increasing vertical offset
            # Increase spacing to reduce overlap and improve readability
            base_vertical = 40.0
            stagger_gap = 40.0
            label_y = ly + base_vertical + stagger * stagger_gap

            font_size = 30
            text_fill = stroke if edge.edge_type.startswith("rss_") else "#334155"

            edge_text_parts.append(
                f'<text x="{lx:.1f}" y="{label_y:.1f}" '
                f'font-size="{font_size}" font-weight="{"700" if edge.edge_type.startswith("rss_") else "400"}" '
                f'fill="{text_fill}" stroke="#ffffff" stroke-width="2.5" paint-order="stroke" '
                f'text-anchor="middle" alignment-baseline="central">{label}</text>'
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
                f'<text x="{x:.1f}" y="{y + 44:.1f}" font-size="26" fill="#64748b" text-anchor="middle">{speed_str}</text>'
            )
        else:
            circle_parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{color}" />'
            )

        # Node label - offset above-left for vehicles, above for roads
        if node.node_type == "Vehicle":
            label_text = display_id(node_id)
        else:
            label_text = f"{node.node_type}:{node_id}"
        circle_parts.append(
            f'<text x="{x:.1f}" y="{y - 28:.1f}" font-size="30" fill="#1a1a1a" '
            f'text-anchor="middle" font-weight="500">{label_text}</text>'
        )

    # Separate RSS panel rows by source
    python_rows, viatra_rows = "", ""
    python_checks = [v for v in rss_violations if v.get("check_source") == "python"]
    python_violations = [v for v in python_checks if v.get("violation")]
    if python_checks:
        for v in python_checks:
            is_violation = v.get("violation")
            badge_color = ("#dc2626" if v["type"] == "Longitudinal" else "#ea580c") if is_violation else "#16a34a"
            dist_info = f' <span style="font-size:15px;color:#64748b;">({v["actual"]}m / {v["safe"]}m safe)</span>' if "actual" in v and "safe" in v else ""
            source_label = display_id(v["source"])
            target_label = display_id(v["target"])
            python_rows += f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;"><span style="background:{badge_color};color:white;padding:2px 8px;border-radius:4px;font-size:16px;font-weight:600;">{v["type"]}</span><span style="font-size:17px;color:#1e293b;">{source_label} &rarr; {target_label}{dist_info}</span></div>'
    else:
        python_rows = '<div style="color:#16a34a;font-size:18px;font-weight:600;">No violations</div>'
    viatra_violations = [v for v in rss_violations if v.get("check_source") == "viatra"]
    if viatra_violations:
        for v in viatra_violations:
            badge_color = "#dc2626" if v["type"] == "Longitudinal" else "#ea580c"
            source_label = display_id(v["source"])
            target_label = display_id(v["target"])
            viatra_rows += f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;"><span style="background:{badge_color};color:white;padding:2px 8px;border-radius:4px;font-size:16px;font-weight:600;">{v["type"]}</span><span style="font-size:17px;color:#1e293b;">{source_label} &rarr; {target_label}</span></div>'
    else:
        viatra_rows = '<div style="color:#16a34a;font-size:18px;font-weight:600;">No violations</div>'

    vehicle_count = sum(1 for n in nodes if n.node_type == "Vehicle")

    html = f"""<!doctype html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script>
        setInterval(function() {{
            location.reload();
        }}, 150);
    </script>
    <title>Scene Graph Live View</title>
    <style>
        html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
        body {{ font-family: Segoe UI, Tahoma, sans-serif; background: #f3f6f9; }}
        .wrap {{
            width: 100vw; height: 100vh; margin: 0; background: white;
            display: flex; flex-direction: column; box-sizing: border-box;
        }}
        .head {{
            padding: 8px 18px; border-bottom: 1px solid #e5e7eb;
            flex: 0 0 auto; display: flex; justify-content: space-between; align-items: flex-start;
        }}
        .head-left {{ flex: 1; }}
        .head-left strong {{ font-size: 26px; font-weight: 700; }}
        .meta {{ color: #3f4b5b; font-size: 16px; margin-top: 4px; }}
        .rss-panels {{ flex: 0 0 auto; display: flex; gap: 8px; margin-left: 16px; }}
        .rss-panel {{
            flex: 0 0 auto; min-width: 350px; max-width: 350px; height: 125px; overflow: auto;
            background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;
            padding: 10px 12px; display: flex; flex-direction: column;
        }}
        .rss-panel.danger {{ background: #fef2f2; border: 1px solid #fecaca; }}
        .rss-panel.safe {{ background: #f0fdf4; border-color: #bbf7d0; }}
        .rss-title {{
            font-size: 16px; font-weight: 700; color: #1e293b; margin-bottom: 4px;
            display: flex; align-items: center; gap: 4px;
        }}
        .rss-count {{ font-size: 14px; color: #64748b; margin-bottom: 3px; }}
        svg {{ display: block; width: 100%; flex: 1 1 auto; background: #fcfdff; }}
        .legend {{
            display: flex; gap: 16px; padding: 6px 18px; border-top: 1px solid #e5e7eb;
            flex: 0 0 auto; font-size: 18px; color: #64748b; align-items: center;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 4px; }}
        .legend-swatch {{ width: 22px; height: 4px; border-radius: 2px; }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="head">
            <div class="head-left">
                <strong>CARLA Scene Graph Live View</strong>
                <div class="meta">Tick: {tick} | Vehicles: {vehicle_count} | Nodes: {len(visible_node_ids)} | Edges: {visible_edge_count}</div>
            </div>
            <div class="rss-panels">
                <div class="rss-panel {'danger' if python_violations else 'safe'}">
                    <div class="rss-title">
                        {'&#x26A0;' if python_violations else '&#x2705;'} Ground Truth
                    </div>
                    <div style="font-size:13px;color:#64748b;margin-bottom:2px;">Python</div>
                    {python_rows}
                </div>
                <div class="rss-panel {'danger' if viatra_violations else 'safe'}">
                    <div class="rss-title">
                        {'&#x26A0;' if viatra_violations else '&#x2705;'} VIATRA
                    </div>
                    <div style="font-size:13px;color:#64748b;margin-bottom:2px;">Query Results</div>
                    {viatra_rows}
                </div>
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
            <div class="legend-item"><div class="legend-swatch" style="background:#738497;"></div> Vehicle proximity</div>
            <div class="legend-item"><div class="legend-swatch" style="background:none;border-top:4px dashed #94a3b8;height:0;"></div> Lane</div>
        </div>
    </div>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def collect_nodes(mock: bool, host: str, port: int, timeout: float, tick: int) -> List[Node]:
    """Collect vehicles and pedestrians only (every tick).
    
    Lanes are cached separately and will be combined in main().
    """
    if mock:
        base = collect_mock_nodes()
        # Return only vehicles and pedestrians from mock data
        return [
            Node(
                node_type=node.node_type,
                external_id=node.external_id,
                x=node.x + math.cos(tick * 0.5 + idx),
                y=node.y + math.sin(tick * 0.5 + idx),
                z=0.0,
                heading=node.heading,
                speed=node.speed,
            )
            for idx, node in enumerate(base)
            if node.node_type != "RoadSegment"
        ]

    return collect_carla_nodes(host, port, timeout)


def synthesize_lanes_from_ego(actors: List[Node]) -> List[Node]:
    """Create center/left/right lane nodes anchored to the first vehicle (ego)."""
    ego_node = next((n for n in actors if n.node_type == "Vehicle"), None)
    if ego_node is None:
        return []

    heading = ego_node.heading
    perp_x = -math.sin(heading)
    perp_y = math.cos(heading)

    lane_specs = [
        ("lane_center", 0.0),
            ("lane_left", LANE_WIDTH_M),
            ("lane_right", -LANE_WIDTH_M),
    ]

    lanes: List[Node] = []
    for lane_id, offset in lane_specs:
        lanes.append(
            Node(
                node_type="RoadSegment",
                external_id=lane_id,
                x=ego_node.x + perp_x * offset,
                y=ego_node.y + perp_y * offset,
                z=0.0,
                heading=heading,
                length=LANE_LENGTH_M,
                width=LANE_WIDTH_M,
            )
        )
    return lanes


def wait_for_viatra_completion(flag_dir: Path, expected_tick: int, timeout: float = 10.0) -> bool:
    """Wait for VIATRA to complete the requested tick."""
    done_flag = flag_dir / "viatra_done.seq"
    start = time.time()

    while time.time() - start < timeout:
        if done_flag.exists():
            try:
                done_tick = int(done_flag.read_text(encoding="utf-8").strip())
            except Exception:
                done_tick = -1
            if done_tick >= expected_tick:
                return True
    
    return False


def signal_ready_for_viatra(flag_dir: Path, tick: int) -> None:
    """Signal to VIATRA that new data is ready to be processed."""
    flag_dir.mkdir(parents=True, exist_ok=True)
    ready_flag = flag_dir / "ready_for_viatra.seq"
    ready_flag.write_text(str(tick), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream CARLA scene graphs to XMI + JSONL")
    parser.add_argument("--out-dir", default="data/stream", help="Output stream directory")
    parser.add_argument("--scene-name", default="CARLA_Stream", help="Scene name for XMI files")
    # Interval-based polling removed: stream emits snapshots as-produced
    parser.add_argument("--ticks", type=int, default=0, help="Number of ticks (0 = infinite)")
    parser.add_argument("--carla-address", default="127.0.0.1", help="CARLA host")
    parser.add_argument("--port", type=int, default=2000, help="CARLA RPC port")
    parser.add_argument("--timeout", type=float, default=60.0, help="CARLA RPC timeout")
    parser.add_argument("--mock", action="store_true", help="Run without CARLA using synthetic movement")
    return parser.parse_args()


def read_xml_with_retry(path, retries=5):
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
                    continue

                try:
                    return ET.parse(f)
                finally:
                    portalocker.unlock(f)

        except Exception:
            if attempt == retries - 1:
                raise

    raise RuntimeError("Unexpected XML read retry state")


def load_edges_from_snapshot(latest_path: Path) -> Optional[List[Edge]]:
    if not latest_path.exists():
        return []

    edges: List[Edge] = []
    try:
        tree = read_xml_with_retry(latest_path)
        if tree is None:
            return None

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
        return None

    return edges


def persist_event(event: Dict[str, object], events_path: Path) -> None:
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def main() -> int:
    args = parse_args()

    out_dir = Path(args.out_dir)
    latest_path = out_dir / "latest_snapshot.xmi"
    events_path = out_dir / "events.jsonl"
    # `current_state.json` mirror removed; use `events.jsonl` and `latest_snapshot.xmi`
    view_path = out_dir / "live_view.html"

    out_dir.mkdir(parents=True, exist_ok=True)

    # NOTE: lane nodes are generated dynamically each tick relative to the ego
    # vehicle position instead of being collected from CARLA topology.

    prev_nodes, prev_edges = {}, set()
    last_known_edges: List[Edge] = []
    tick = 0
    while True:
        tick += 1
        
        # Wait for VIATRA to complete processing previous frame (except on first tick)
        if tick > 1:
            if not wait_for_viatra_completion(out_dir, tick - 1, timeout=10.0):
                print(f"WARNING: VIATRA did not complete in time at tick {tick}")
        
        actors = collect_nodes(args.mock, args.carla_address, args.port, args.timeout, tick)
        
        lanes = synthesize_lanes_from_ego(actors)

        # Combine actors (vehicles/pedestrians) with synthesized lane nodes
        nodes = actors + lanes

        # Preserve existing edges while refreshing nodes to avoid wiping edge state.
        existing_edges = load_edges_from_snapshot(latest_path)
        if existing_edges is None:
            edges_for_write = last_known_edges
            print("WARNING: Could not read existing edges; reusing last known edges for snapshot write")
        else:
            edges_for_write = existing_edges

        # Write only the rolling latest snapshot with current node state.
        write_scene_xmi(args.scene_name, nodes, edges_for_write, latest_path)
        
        # Signal VIATRA that new data is ready
        signal_ready_for_viatra(out_dir, tick)

        viatra_ok = wait_for_viatra_completion(out_dir, tick, timeout=10.0)
        if not viatra_ok:
            print(f"WARNING: VIATRA did not complete in time for tick {tick}")

        edges = load_edges_from_snapshot(latest_path)
        if edges is None:
            edges = last_known_edges
            print("WARNING: Could not read post-VIATRA edges; reusing last known edges")
        else:
            last_known_edges = edges

        if viatra_ok:
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

        persist_event(event, events_path)

        prev_nodes = {node.external_id: normalize_node(node) for node in nodes}
        prev_edges = {k for edge in edges if (k := edge_key(edge, nodes)) is not None}

        print(
            f"tick={tick} nodes={len(nodes)} edges={len(edges)} snapshot={latest_path}",
            flush=True,
        )

        if args.ticks > 0 and tick >= args.ticks:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
