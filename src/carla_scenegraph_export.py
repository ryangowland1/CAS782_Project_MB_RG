#!/usr/bin/env python3
"""Export a CARLA world snapshot to SceneGraph XMI.

This script writes XMI instances that conform to model/SceneGraph.ecore.
Use --mock to generate a deterministic sample without CARLA.
"""

from __future__ import annotations

import argparse
import math
import sys
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
    speed: Optional[float] = None


@dataclass
class Edge:
    edge_type: str
    source_index: int
    target_index: int


def _distance(a: Node, b: Node) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def collect_mock_nodes() -> List[Node]:
    return [
        Node("Vehicle", "veh-ego", 0.0, 0.0, 0.0, speed=8.0),
        Node("Vehicle", "veh-1", 10.0, 0.0, 0.0, speed=12.5),
        Node("Pedestrian", "ped-1", 11.0, 1.0, 0.0),
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
    for actor in world.get_actors():
        actor_type = actor.type_id
        transform = actor.get_transform()
        velocity = actor.get_velocity()
        speed = math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)

        if actor_type.startswith("vehicle."):
            nodes.append(
                Node(
                    node_type="Vehicle",
                    external_id=str(actor.id),
                    x=transform.location.x,
                    y=transform.location.y,
                    z=transform.location.z,
                    speed=speed,
                )
            )
        elif actor_type.startswith("walker.pedestrian."):
            nodes.append(
                Node(
                    node_type="Pedestrian",
                    external_id=str(actor.id),
                    x=transform.location.x,
                    y=transform.location.y,
                    z=transform.location.z,
                )
            )

    return nodes


def build_edges(nodes: List[Node], proximity_m: float) -> List[Edge]:
    edges: List[Edge] = []
    for i, src in enumerate(nodes):
        for j, dst in enumerate(nodes):
            if i >= j:
                continue
            if _distance(src, dst) <= proximity_m:
                edges.append(Edge("proximity", i, j))
    return edges


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
        attrs = {
            f"{{{XSI_NS}}}type": f"scenegraph:{node.node_type}",
            "id": node.external_id,
            "x": f"{node.x:.6f}",
            "y": f"{node.y:.6f}",
            "z": f"{node.z:.6f}",
        }
        if node.node_type == "Vehicle" and node.speed is not None:
            attrs["speed"] = f"{node.speed:.6f}"
        ET.SubElement(root, "nodes", attrs)

    for edge in edges:
        ET.SubElement(
            root,
            "edges",
            {
                "type": edge.edge_type,
                "source": f"//@nodes.{edge.source_index}",
                "target": f"//@nodes.{edge.target_index}",
            },
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export CARLA snapshot to SceneGraph XMI")
    parser.add_argument("--output", default="data/scene_snapshot.xmi", help="Output XMI path")
    parser.add_argument("--scene-name", default="CARLA_Snapshot", help="Scene name")
    parser.add_argument("--host", default="127.0.0.1", help="CARLA host")
    parser.add_argument("--port", type=int, default=2000, help="CARLA RPC port")
    parser.add_argument("--timeout", type=float, default=5.0, help="CARLA client timeout seconds")
    parser.add_argument(
        "--proximity-threshold",
        type=float,
        default=12.0,
        help="Distance threshold for generating proximity edges",
    )
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

    edges = build_edges(nodes, args.proximity_threshold)
    write_scene_xmi(args.scene_name, nodes, edges, Path(args.output))

    print(f"Wrote {len(nodes)} nodes and {len(edges)} edges to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
