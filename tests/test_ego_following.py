#!/usr/bin/env python3
"""Automated tests for the EgoFollowing VIATRA query pattern.

Tests verify the geometric / speed logic that the VQL pattern encodes:
  - ego id == "veh-ego"
  - both vehicles moving (speed > 0.5 m/s)
  - Euclidean distance in [5, 50] m  (dist² in [25, 2500])
  - lead within ego's forward ±45° sector (relative angle in [-π/4, π/4])

Each test case also writes an XMI snapshot under tests/xmi_out/ so the
VIATRA QueryRunner can be pointed at them for a full end-to-end check.
"""

from __future__ import annotations

import math
import sys
import textwrap
from pathlib import Path

# Allow importing project modules from src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from carla_scenegraph_export import Node, Edge, write_scene_xmi

XMI_OUT = Path(__file__).resolve().parent / "xmi_out"
XMI_OUT.mkdir(exist_ok=True)


# ---------- replicate the Java helper's angle logic in Python ----------

def calculate_angle(sx: float, sy: float, sh: float, tx: float, ty: float) -> float:
    """Port of scenegraphhelper.calculateAngle (Java → Python)."""
    dx = tx - sx
    dy = ty - sy
    angle_to_target = math.atan2(dy, dx)
    relative = angle_to_target - sh
    while relative > math.pi:
        relative -= 2 * math.pi
    while relative < -math.pi:
        relative += 2 * math.pi
    return relative


def ego_following_matches(ego: Node, lead: Node) -> bool:
    """Return True when the VQL EgoFollowing pattern *should* fire."""
    if ego.external_id != "veh-ego":
        return False
    if ego.speed is None or lead.speed is None:
        return False
    if ego.speed <= 0.5 or lead.speed <= 0.5:
        return False
    dx = ego.x - lead.x
    dy = ego.y - lead.y
    dist_sq = dx * dx + dy * dy
    if dist_sq < 25.0 or dist_sq > 2500.0:
        return False
    angle = calculate_angle(ego.x, ego.y, ego.heading, lead.x, lead.y)
    if angle < -0.7854 or angle > 0.7854:
        return False
    return True


# ---------- test-case definitions ----------

def _make_ego(heading: float = 0.0, speed: float = 10.0) -> Node:
    return Node("Vehicle", "veh-ego", 0.0, 0.0, 0.0, heading, speed=speed)


def _make_lead(x: float, y: float, speed: float = 10.0) -> Node:
    return Node("Vehicle", "veh-lead", x, y, 0.0, 0.0, speed=speed)


def _write_case(name: str, ego: Node, lead: Node) -> Path:
    """Write a two-vehicle XMI and return the path."""
    nodes = [ego, lead]
    edges: list[Edge] = []
    path = XMI_OUT / f"{name}.xmi"
    write_scene_xmi(f"Test_{name}", nodes, edges, path)
    return path


CASES: list[tuple[str, bool, Node, Node]] = [
    # ---------- POSITIVE (should match) ----------
    (
        "straight_ahead_10m",
        True,
        _make_ego(heading=0.0, speed=10.0),
        _make_lead(x=10.0, y=0.0, speed=8.0),
    ),
    (
        "straight_ahead_50m",
        True,
        _make_ego(heading=0.0, speed=5.0),
        _make_lead(x=50.0, y=0.0, speed=5.0),
    ),
    (
        "slight_left_20m",
        True,
        _make_ego(heading=0.0, speed=6.0),
        _make_lead(x=19.0, y=6.0, speed=6.0),       # angle ≈ +17°
    ),
    (
        "slight_right_15m",
        True,
        _make_ego(heading=0.0, speed=7.0),
        _make_lead(x=14.0, y=-5.0, speed=7.0),       # angle ≈ −20°
    ),
    (
        "heading_north_lead_ahead",
        True,
        _make_ego(heading=math.pi / 2, speed=12.0),  # facing +Y
        _make_lead(x=0.0, y=20.0, speed=10.0),
    ),

    # ---------- NEGATIVE (should NOT match) ----------
    (
        "too_close_3m",
        False,
        _make_ego(heading=0.0, speed=10.0),
        _make_lead(x=3.0, y=0.0, speed=10.0),
    ),
    (
        "too_far_60m",
        False,
        _make_ego(heading=0.0, speed=10.0),
        _make_lead(x=60.0, y=0.0, speed=10.0),
    ),
    (
        "behind_ego",
        False,
        _make_ego(heading=0.0, speed=10.0),
        _make_lead(x=-15.0, y=0.0, speed=10.0),      # 180° behind
    ),
    (
        "to_the_side_90deg",
        False,
        _make_ego(heading=0.0, speed=10.0),
        _make_lead(x=0.0, y=15.0, speed=10.0),       # 90° left
    ),
    (
        "ego_stopped",
        False,
        _make_ego(heading=0.0, speed=0.0),
        _make_lead(x=10.0, y=0.0, speed=10.0),
    ),
    (
        "lead_stopped",
        False,
        _make_ego(heading=0.0, speed=10.0),
        _make_lead(x=10.0, y=0.0, speed=0.0),
    ),
    (
        "wrong_ego_id",
        False,
        Node("Vehicle", "veh-1", 0.0, 0.0, 0.0, 0.0, speed=10.0),  # NOT "veh-ego"
        _make_lead(x=10.0, y=0.0, speed=10.0),
    ),
    (
        "at_boundary_45deg_outside",
        False,
        _make_ego(heading=0.0, speed=10.0),
        _make_lead(x=7.0, y=7.1, speed=10.0),        # angle ≈ 45.4° → just outside
    ),
]


# ---------- runner ----------

def run_tests() -> bool:
    passed = 0
    failed = 0
    total = len(CASES)

    print(f"Running {total} EgoFollowing test cases ...\n")

    for name, expected, ego, lead in CASES:
        actual = ego_following_matches(ego, lead)
        xmi_path = _write_case(name, ego, lead)
        status = "PASS" if actual == expected else "FAIL"
        if actual != expected:
            failed += 1
            angle = calculate_angle(ego.x, ego.y, ego.heading, lead.x, lead.y)
            dx = ego.x - lead.x
            dy = ego.y - lead.y
            dist = math.sqrt(dx * dx + dy * dy)
            print(f"  [{status}] {name}: expected={expected}, got={actual}  "
                  f"(dist={dist:.2f}m, angle={math.degrees(angle):.1f}°, "
                  f"ego_spd={ego.speed}, lead_spd={lead.speed})")
        else:
            passed += 1
            print(f"  [{status}] {name}")

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print(f"XMI snapshots written to: {XMI_OUT}")

    if failed:
        print("\nFAILED test cases above need investigation.")
        return False

    print("\nAll tests passed!")
    return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
