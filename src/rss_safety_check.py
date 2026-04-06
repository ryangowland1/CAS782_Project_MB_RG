#!/usr/bin/env python3
"""RSS (Responsibility-Sensitive Safety) rule violation checker.

Implements safe distance calculations from:
  "On a Formal Model of Safe and Scalable Self-Driving Cars"
  (Shalev-Shwartz, Shammah, Shashua, 2017)

as outlined in AV_Safety_Frameworks.pdf (Equations 1 and 3).

Checks:
  1. Longitudinal safe distance to closest vehicle in front of ego (same lane)
  2. Lateral safe distance to closest vehicle beside ego (adjacent lane)

Usage:
  from rss_safety_check import check_rss_safety, RSSParams
  violations = check_rss_safety(ego_node, all_vehicle_nodes)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from carla_scenegraph_export import Node


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

@dataclass
class RSSParams:
    """RSS parameters for safe distance calculations.

    Defaults are representative values from the RSS literature.
    """

    # Reaction time (seconds) -- time before braking begins
    rho: float = 0.5

    # -- Longitudinal parameters (Table 1 in AV_Safety_Frameworks.pdf) --
    a_lon_max: float = 3.5   # Max longitudinal accel during reaction (m/s^2)
    b_lon_min: float = 4.0   # Min braking decel after reaction, ego (m/s^2)
    b_lon_max: float = 8.0   # Max braking decel of other vehicle (m/s^2)

    # -- Lateral parameters (Table 2 in AV_Safety_Frameworks.pdf) --
    a_lat_max: float = 0.2   # Max lateral accel during reaction (m/s^2)
    b_lat_min: float = 0.8   # Min lateral braking decel after reaction (m/s^2)
    mu: float = 0.1          # Lateral fluctuation margin (m)

    # -- Classification thresholds --
    same_lane_lat_threshold: float = 2.0   # Max lateral offset for "same lane" (m)
    beside_lat_min: float = 1.0            # Min lateral offset for "beside" (m)
    beside_lat_max: float = 5.0            # Max lateral offset for "beside" (m)
    beside_lon_max: float = 15.0           # Max |longitudinal dist| for "beside" (m)
    front_lon_max: float = 100.0           # Max longitudinal dist to consider (m)


# ---------------------------------------------------------------------------
# Violation record
# ---------------------------------------------------------------------------

@dataclass
class RSSViolation:
    """Represents an RSS rule violation."""

    rule: str               # "longitudinal" or "lateral"
    ego_id: str
    other_id: str
    actual_distance: float  # measured gap (m)
    safe_distance: float    # RSS minimum safe distance (m)
    ego_speed: float        # m/s
    other_speed: float      # m/s


# ---------------------------------------------------------------------------
# Safe-distance formulas
# ---------------------------------------------------------------------------

def rss_longitudinal_safe_distance(
    v_rear: float,
    v_front: float,
    params: RSSParams,
) -> float:
    """RSS minimum safe longitudinal distance -- Equation 1.

    v_rear:  longitudinal speed of the rear (ego) vehicle  (m/s, >= 0)
    v_front: longitudinal speed of the front (lead) vehicle (m/s, >= 0)
    """
    rho = params.rho
    a = params.a_lon_max
    b_min = params.b_lon_min
    b_max = params.b_lon_max

    v_r_rho = v_rear + rho * a          # ego velocity after reaction interval

    d_min = (
        v_rear * rho
        + 0.5 * a * rho ** 2
        + v_r_rho ** 2 / (2.0 * b_min)
        - v_front ** 2 / (2.0 * b_max)
    )
    return max(0.0, d_min)


def rss_lateral_safe_distance(
    v_ego_toward: float,
    v_other_away: float,
    params: RSSParams,
) -> float:
    """RSS minimum safe lateral distance -- Equation 3.

    v_ego_toward:  ego's lateral velocity *toward* the other vehicle
                   (positive = gap is closing from ego's side)
    v_other_away:  other vehicle's lateral velocity *away* from ego
                   (positive = gap is opening from other's side)

    Sign convention follows the paper: v1_rho = v1 + rho*a  (ego worst-case),
    v2_rho = v2 - rho*a  (other worst-case, decelerates its away-motion).
    """
    rho = params.rho
    a = params.a_lat_max
    b = params.b_lat_min
    mu = params.mu

    v1_rho = v_ego_toward + rho * a     # ego accelerates toward other
    v2_rho = v_other_away - rho * a     # other decelerates away-motion

    # Distance ego covers laterally (toward other) during reaction + braking
    D1 = (v_ego_toward + v1_rho) / 2.0 * rho + v1_rho ** 2 / (2.0 * b)

    # Distance other covers laterally (away from ego) during reaction - braking
    D2 = (v_other_away + v2_rho) / 2.0 * rho - v2_rho ** 2 / (2.0 * b)

    return mu + max(0.0, D1 - D2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_velocity_components(node: Node) -> Tuple[float, float]:
    """Return (vx, vy) world-frame velocity for a node."""
    if node.vx is not None and node.vy is not None:
        return node.vx, node.vy
    # Fall back: estimate from speed + heading
    speed = node.speed if node.speed is not None else 0.0
    return speed * math.cos(node.heading), speed * math.sin(node.heading)


def decompose_in_ego_frame(
    ego: Node,
    other: Node,
) -> Tuple[float, float, float, float, float, float]:
    """Decompose relative position & velocity into ego's longitudinal / lateral frame.

    Returns
    -------
    lon_dist       positive = other is in front of ego
    lat_dist       signed lateral offset (consistent but arbitrary sign)
    ego_lon_vel    ego longitudinal velocity
    ego_lat_vel    ego lateral velocity
    other_lon_vel  other longitudinal velocity
    other_lat_vel  other lateral velocity
    """
    fwd_x = math.cos(ego.heading)
    fwd_y = math.sin(ego.heading)
    perp_x = -fwd_y
    perp_y = fwd_x

    # Relative position
    dx = other.x - ego.x
    dy = other.y - ego.y
    lon_dist = dx * fwd_x + dy * fwd_y
    lat_dist = dx * perp_x + dy * perp_y

    # Velocities
    ego_vx, ego_vy = get_velocity_components(ego)
    other_vx, other_vy = get_velocity_components(other)

    ego_lon_vel = ego_vx * fwd_x + ego_vy * fwd_y
    ego_lat_vel = ego_vx * perp_x + ego_vy * perp_y
    other_lon_vel = other_vx * fwd_x + other_vy * fwd_y
    other_lat_vel = other_vx * perp_x + other_vy * perp_y

    return lon_dist, lat_dist, ego_lon_vel, ego_lat_vel, other_lon_vel, other_lat_vel


# ---------------------------------------------------------------------------
# Closest-vehicle finders
# ---------------------------------------------------------------------------

def find_closest_front_vehicle(
    ego: Node,
    vehicles: List[Node],
    params: RSSParams,
) -> Optional[Tuple[Node, float, float]]:
    """Find the closest vehicle in front of ego, roughly in the same lane.

    Returns (vehicle, lon_dist, lat_dist) or None.
    """
    best: Optional[Tuple[Node, float, float]] = None
    best_lon = float("inf")

    for v in vehicles:
        if v.external_id == ego.external_id or v.node_type != "Vehicle":
            continue

        lon, lat, *_ = decompose_in_ego_frame(ego, v)

        if 0 < lon < params.front_lon_max and abs(lat) < params.same_lane_lat_threshold:
            if lon < best_lon:
                best_lon = lon
                best = (v, lon, lat)

    return best


def find_closest_lateral_vehicle(
    ego: Node,
    vehicles: List[Node],
    params: RSSParams,
) -> Optional[Tuple[Node, float, float]]:
    """Find the closest vehicle beside ego (adjacent lane).

    Returns (vehicle, lon_dist, lat_dist) or None.
    """
    best: Optional[Tuple[Node, float, float]] = None
    best_abs_lat = float("inf")

    for v in vehicles:
        if v.external_id == ego.external_id or v.node_type != "Vehicle":
            continue

        lon, lat, *_ = decompose_in_ego_frame(ego, v)
        abs_lat = abs(lat)

        if (
            params.beside_lat_min < abs_lat < params.beside_lat_max
            and abs(lon) < params.beside_lon_max
        ):
            if abs_lat < best_abs_lat:
                best_abs_lat = abs_lat
                best = (v, lon, lat)

    return best


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

def check_rss_safety(
    ego: Node,
    vehicles: List[Node],
    params: Optional[RSSParams] = None,
) -> List[RSSViolation]:
    """Check RSS rules for *ego* against all nearby vehicles.

    Only considers:
      - the closest vehicle **in front** of ego  -> longitudinal rule
      - the closest vehicle **beside** ego        -> lateral rule

    Returns a (possibly empty) list of violations.
    """
    if params is None:
        params = RSSParams()

    violations: List[RSSViolation] = []

    # ---- longitudinal (closest vehicle in front) ----
    front = find_closest_front_vehicle(ego, vehicles, params)
    if front is not None:
        front_v, lon_dist, _lat = front
        _lon, _lat2, ego_lon, _elat, other_lon, _olat = decompose_in_ego_frame(ego, front_v)

        d_safe = rss_longitudinal_safe_distance(max(ego_lon, 0.0), max(other_lon, 0.0), params)

        if lon_dist < d_safe:
            violations.append(
                RSSViolation(
                    rule="longitudinal",
                    ego_id=ego.external_id,
                    other_id=front_v.external_id,
                    actual_distance=lon_dist,
                    safe_distance=d_safe,
                    ego_speed=ego.speed or 0.0,
                    other_speed=front_v.speed or 0.0,
                )
            )

    # ---- lateral (closest vehicle beside) ----
    beside = find_closest_lateral_vehicle(ego, vehicles, params)
    if beside is not None:
        beside_v, _lon, lat_dist = beside
        _lon2, lat2, _elon, ego_lat, _olon, other_lat = decompose_in_ego_frame(ego, beside_v)

        # Determine closing / opening lateral velocities relative to the gap.
        if lat2 > 0:
            # other is on the +perp side
            v_ego_toward = ego_lat       # positive ego_lat => moving toward other
            v_other_away = other_lat     # positive other_lat => moving away
        else:
            # other is on the -perp side
            v_ego_toward = -ego_lat
            v_other_away = -other_lat

        d_safe = rss_lateral_safe_distance(v_ego_toward, v_other_away, params)
        actual_gap = abs(lat2)

        if actual_gap < d_safe:
            violations.append(
                RSSViolation(
                    rule="lateral",
                    ego_id=ego.external_id,
                    other_id=beside_v.external_id,
                    actual_distance=actual_gap,
                    safe_distance=d_safe,
                    ego_speed=ego.speed or 0.0,
                    other_speed=beside_v.speed or 0.0,
                )
            )

    return violations
