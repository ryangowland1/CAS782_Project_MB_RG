#!/usr/bin/env python3
"""Export a CARLA world snapshot to SceneGraph XMI.

This script writes XMI instances that conform to
SceneGraphModel/model/sceneGraphModel.ecore.
Use --mock to generate a deterministic sample without CARLA.
"""

# NOTE: THIS WILL NOT HANDLE CURVED LANES PROPERLY AS IT ASSUMES ALL LANES ARE STRAIGHT FOR LENGTH/WIDTH ATTRIBUTES. 
# A PROPER IMPLEMENTATION WOULD NEED TO CAPTURE LANE CURVATURE AND REPRESENT IT IN THE SCENEGRAPH MODEL, 
# WHICH MAY REQUIRE EXTENDING THE MODEL TO SUPPORT CURVED ROAD SEGMENTS OR POLYLINE REPRESENTATIONS.

from __future__ import annotations

import argparse
import math
import sys
import time
import portalocker
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

SCENEGRAPH_NS = "http://cas782/scenegraph"
XMI_NS = "http://www.omg.org/XMI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("scenegraph", SCENEGRAPH_NS)
ET.register_namespace("xmi", XMI_NS)
ET.register_namespace("xsi", XSI_NS)


@dataclass
class Node:
    node_type: str
    external_id: str
    x: float
    y: float
    z: float
    heading: float
    speed: Optional[float] = None
    length: Optional[float] = None
    width: Optional[float] = None
    vx: Optional[float] = None
    vy: Optional[float] = None


@dataclass
class Edge:
    edge_type: str
    distance: str
    spatial: str
    source_index: int
    target_index: int


def _waypoint_segment_length(start_waypoint, end_waypoint) -> float:
    """Estimate lane segment length for a topology edge in meters."""
    try:
        # CARLA waypoint.s is longitudinal arc-length along the road reference line.
        seg = abs(float(end_waypoint.s) - float(start_waypoint.s))
        if seg > 0.0:
            return seg
    except Exception:
        pass

    # Fallback for unusual topology entries where s is unavailable/degenerate.
    return float(start_waypoint.transform.location.distance(end_waypoint.transform.location))


def collect_mock_nodes() -> List[Node]:
    return [
        Node("Vehicle", "veh-ego", 0.0, 0.0, 0.0, 0.0, speed=8.0),
        Node("Vehicle", "veh-1", 10.0, 0.0, 0.0, 1.57, speed=12.5),
        Node("Pedestrian", "ped-1", 11.0, 1.0, 0.0, 0.785),
        Node("RoadSegment", "lane-1", 0.0, -2.0, 0.0, 0.0, length=40.0, width=3.5),
        Node("RoadSegment", "lane-2", 0.0, 2.0, 0.0, 0.0, length=40.0, width=3.5),
        Node("RoadSegment", "lane-3", 10.0, -2.0, 0.0, 1.57, length=30.0, width=3.5),
    ]


def collect_carla_nodes(host: str, port: int, timeout: float) -> List[Node]:
    try:
        import carla  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "CARLA Python API not available. Install CARLA Python package or use --mock."
        ) from exc

    client = carla.Client(host, port)
    client.set_timeout(timeout)
    world = client.get_world()

    nodes: List[Node] = []
    
    # Collect vehicles and pedestrians
    for actor in world.get_actors():
        actor_type = actor.type_id
        transform = actor.get_transform()
        velocity = actor.get_velocity()
        speed = math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)
        heading = math.radians(transform.rotation.yaw)

        if actor_type.startswith("vehicle."):
            node_type, node_speed = "Vehicle", speed
            node_vx, node_vy = velocity.x, velocity.y
        elif actor_type.startswith("walker.pedestrian."):
            node_type, node_speed = "Pedestrian", None
            node_vx, node_vy = None, None
        else:
            continue

        nodes.append(
            Node(
                node_type=node_type,
                external_id=str(actor.id),
                x=transform.location.x,
                y=transform.location.y,
                z=transform.location.z,
                heading=heading,
                speed=node_speed,
                vx=node_vx,
                vy=node_vy,
            )
        )
    
    # Collect lanes as road segments
    try:
        carla_map = world.get_map()
        topology = carla_map.get_topology()

        # Track lane geometry from topology segments.
        lane_metrics = {}
        for start_waypoint, end_waypoint in topology:
            # Restrict to strict driving lanes
            if start_waypoint.lane_type != carla.LaneType.Driving:
                continue

            lane_id = start_waypoint.lane_id
            road_id = start_waypoint.road_id
            lane_key = (road_id, lane_id)

            start_loc = start_waypoint.transform.location
            end_loc = end_waypoint.transform.location
            s_start = float(start_waypoint.s)
            s_end = float(end_waypoint.s)
            segment_length = _waypoint_segment_length(start_waypoint, end_waypoint)
            if segment_length <= 0.0:
                continue

            # CARLA topology may contain repeated entries; use a rounded geometric key to de-duplicate.
            segment_key = (
                start_waypoint.road_id,
                start_waypoint.lane_id,
                start_waypoint.section_id,
                round(s_start, 3),
                round(s_end, 3),
                round(start_loc.x, 2),
                round(start_loc.y, 2),
                round(end_loc.x, 2),
                round(end_loc.y, 2),
            )

            if lane_key not in lane_metrics:
                lane_metrics[lane_key] = {
                    "waypoint": start_waypoint,
                    "width": float(start_waypoint.lane_width),
                    "length_sum": 0.0,
                    "segments_seen": set(),
                    "center_x_sum": 0.0,
                    "center_y_sum": 0.0,
                    "center_z_sum": 0.0,
                    "dir_x_sum": 0.0,
                    "dir_y_sum": 0.0,
                    "sample_points": [],
                }

            metrics = lane_metrics[lane_key]
            if segment_key in metrics["segments_seen"]:
                continue

            metrics["segments_seen"].add(segment_key)
            metrics["length_sum"] += segment_length
            metrics["center_x_sum"] += (start_loc.x + end_loc.x) * 0.5 * segment_length
            metrics["center_y_sum"] += (start_loc.y + end_loc.y) * 0.5 * segment_length
            metrics["center_z_sum"] += (start_loc.z + end_loc.z) * 0.5 * segment_length
            metrics["dir_x_sum"] += (end_loc.x - start_loc.x) * segment_length
            metrics["dir_y_sum"] += (end_loc.y - start_loc.y) * segment_length
            metrics["sample_points"].append((start_loc.x, start_loc.y, start_loc.z))
            metrics["sample_points"].append((end_loc.x, end_loc.y, end_loc.z))
            metrics["width"] = max(metrics["width"], float(start_waypoint.lane_width))

        # Create RoadSegment nodes for each unique lane
        for (road_id, lane_id), metrics in lane_metrics.items():
            waypoint = metrics["waypoint"]
            accumulated_length = float(metrics["length_sum"])
            if accumulated_length < 0.1:  # Skip degenerate lanes
                continue

            center_x = metrics["center_x_sum"] / accumulated_length
            center_y = metrics["center_y_sum"] / accumulated_length
            center_z = metrics["center_z_sum"] / accumulated_length
            if abs(metrics["dir_x_sum"]) > 1e-4 or abs(metrics["dir_y_sum"]) > 1e-4:
                heading_rad = math.atan2(metrics["dir_y_sum"], metrics["dir_x_sum"])
            else:
                heading_rad = math.radians(waypoint.transform.rotation.yaw)

            # For a straight rectangular lane model, use axis-projected extent rather than arc length.
            axis_x = math.cos(heading_rad)
            axis_y = math.sin(heading_rad)
            projections = [
                (px - center_x) * axis_x + (py - center_y) * axis_y
                for px, py, _pz in metrics["sample_points"]
            ]

            if projections:
                lane_length = max(projections) - min(projections)
            else:
                lane_length = accumulated_length

            if lane_length < 0.1:
                lane_length = accumulated_length

            external_id = f"lane_{road_id}_{lane_id}"
            nodes.append(
                Node(
                    node_type="RoadSegment",
                    external_id=external_id,
                    x=float(center_x),
                    y=float(center_y),
                    z=float(center_z),
                    heading=float(heading_rad),
                    length=lane_length,
                    width=float(metrics["width"]),
                )
            )
    except Exception as e:
        print(f"Warning: Could not collect lane data: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()

    return nodes


def write_xmi_with_retry(tree, path, retries=5, delay=0.05):
    """
    Writes an XML/XMI file with retry logic if the file is locked.

    :param tree: ElementTree to write
    :param path: Output file path
    :param retries: Number of retry attempts
    :param delay: Delay between retries in seconds
    :return: True if successful, False otherwise
    """
    for attempt in range(retries):
        try:
            with open(path, "wb") as f:
                try:
                    # Exclusive non-blocking lock (Java tryLock equivalent)
                    portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
                except portalocker.exceptions.LockException:
                    if attempt == retries - 1:
                        print(f"File is locked after {retries} attempts: {path}")
                        return False
                    time.sleep(delay)
                    continue

                try:
                    tree.write(f, encoding="utf-8", xml_declaration=True)
                    f.flush()
                    return True
                finally:
                    portalocker.unlock(f)

        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(delay)

    return False


def _node_attributes(node: Node) -> dict:
    attrs = {
        f"{{{XSI_NS}}}type": f"scenegraph:{node.node_type}",
        "id": str(node.external_id),
        "x": f"{node.x:.6f}",
        "y": f"{node.y:.6f}",
        "z": f"{node.z:.6f}",
        "heading": f"{node.heading:.6f}",
    }

    if node.node_type == "Vehicle" and node.speed is not None:
        attrs["speed"] = f"{node.speed:.6f}"

    if node.node_type == "Vehicle":
        if node.vx is not None:
            attrs["vx"] = f"{node.vx:.6f}"
        if node.vy is not None:
            attrs["vy"] = f"{node.vy:.6f}"

    if node.node_type == "RoadSegment":
        if node.length is not None:
            attrs["length"] = f"{node.length:.6f}"
        if node.width is not None:
            attrs["width"] = f"{node.width:.6f}"

    return attrs


def _edge_attributes(edge: Edge) -> dict:
    return {
        "type": str(edge.edge_type or ""),
        "distance": str(edge.distance or ""),
        "spatial": str(edge.spatial or ""),
        "source": f"//@nodes.{edge.source_index}",
        "target": f"//@nodes.{edge.target_index}",
    }

def write_scene_xmi(scene_name: str, nodes: List[Node], edges: List[Edge], output_path: Path) -> None:
    scene_tag = f"{{{SCENEGRAPH_NS}}}Scene"
    root = ET.Element(
        scene_tag,
        {
            f"{{{XMI_NS}}}version": "2.0",
            "name": scene_name,
        },
    )

    for node in nodes:
        ET.SubElement(root, "nodes", _node_attributes(node))

    for edge in edges:
        ET.SubElement(root, "edges", _edge_attributes(edge))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    write_xmi_with_retry(tree, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export CARLA snapshot to SceneGraph XMI")
    parser.add_argument("--output", default="data/scene_snapshot.xmi", help="Output XMI path")
    parser.add_argument("--scene-name", default="CARLA_Snapshot", help="Scene name")
    parser.add_argument("--host", default="127.0.0.1", help="CARLA host")
    parser.add_argument("--port", type=int, default=2000, help="CARLA RPC port")
    parser.add_argument("--timeout", type=float, default=5.0, help="CARLA client timeout seconds")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Generate deterministic sample without CARLA connection",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.mock:
        nodes = collect_mock_nodes()
    else:
        try:
            nodes = collect_carla_nodes(args.host, args.port, args.timeout)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    edges: List[Edge] = []
    write_scene_xmi(args.scene_name, nodes, edges, Path(args.output))

    print(f"Wrote {len(nodes)} nodes and {len(edges)} edges to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
