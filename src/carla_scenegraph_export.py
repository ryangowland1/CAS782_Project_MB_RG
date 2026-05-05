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
    heading: float
    z: float = 0.0
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


def collect_mock_nodes() -> List[Node]:
    return [
        Node("Vehicle", "veh-ego", 0.0, 0.0, heading=0.0, speed=8.0),
        Node("Vehicle", "veh-1", 10.0, 0.0, heading=1.57, speed=12.5),
        Node("Pedestrian", "ped-1", 11.0, 1.0, heading=0.785),
        Node("RoadSegment", "lane-1", 0.0, -2.0, heading=0.0, length=40.0, width=3.5),
        Node("RoadSegment", "lane-2", 0.0, 2.0, heading=0.0, length=40.0, width=3.5),
        Node("RoadSegment", "lane-3", 10.0, -2.0, heading=1.57, length=30.0, width=3.5),
    ]


def _get_carla_world(host: str, port: int, timeout: float):
    try:
        import carla  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "CARLA Python API not available. Install CARLA Python package or use --mock."
        ) from exc

    client = carla.Client(host, port)
    client.set_timeout(timeout)
    return client.get_world()


def collect_carla_nodes(host: str, port: int, timeout: float) -> List[Node]:
    """Collect vehicles and pedestrians from CARLA world (every tick).
    
    Lanes are not collected by this function; it returns only actors (vehicles and pedestrians).
    """
    world = _get_carla_world(host, port, timeout)

    nodes: List[Node] = []
    
    # Collect vehicles and pedestrians only
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

        # Map ego/lead vehicles to synthetic IDs 147/148 for display purposes
        role = actor.attributes.get('role_name', '')
        if role == 'ego':
            external_id = "147"
        elif role == 'lead':
            external_id = "148"
        else:
            external_id = str(actor.id)

        nodes.append(
            Node(
                node_type=node_type,
                external_id=external_id,
                x=transform.location.x,
                y=transform.location.y,
                z=transform.location.z,
                heading=heading,
                speed=node_speed,
                vx=node_vx,
                vy=node_vy,
            )
        )

    return nodes


def write_xmi_with_retry(tree, path, retries=5):
    """
    Writes an XML/XMI file with retry logic if the file is locked.

    :param tree: ElementTree to write
    :param path: Output file path
    :param retries: Number of retry attempts
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
            # immediate retry without sleeping to minimize latency on contention
            continue

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
    parser.add_argument("--timeout", type=float, default=60.0, help="CARLA client timeout seconds")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Generate deterministic sample without CARLA connection",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.mock:
        # Mock mode: use mock nodes for testing
        nodes = collect_mock_nodes()
    else:
        try:
            # In real mode: collect actors (vehicles + pedestrians) only; lanes are cached separately
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
