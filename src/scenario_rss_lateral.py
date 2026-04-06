#!/usr/bin/env python3
"""
CARLA Scenario: RSS Lateral Safe-Distance Test
================================================
Spawns ego + adjacent vehicle in neighbouring lanes.

Phase 1 (0-10 s): Both drive straight at ~30 km/h, ~3.5 m lateral gap.
                   No lateral drift → no RSS lateral violations expected.
Phase 2 (10+ s):  Adjacent vehicle steers toward ego's lane, creating
                   lateral closing velocity.  Once the combined lateral
                   speed and proximity cross the RSS threshold, violations
                   are flagged.

Duration: configurable (default 30 s).
"""

from __future__ import annotations

import glob
import math
import os
import random
import sys
import time

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
carla_api_root = os.path.join(workspace_root, "PythonAPI", "carla")
for whl in glob.glob(os.path.join(carla_api_root, "dist", "carla-*.whl")):
    if whl not in sys.path:
        sys.path.append(whl)
if carla_api_root not in sys.path:
    sys.path.append(carla_api_root)

src_dir = os.path.join(workspace_root, "src")
if src_dir not in sys.path:
    sys.path.append(src_dir)

import carla
from agents.navigation.controller import VehiclePIDController
from carla_scenegraph_export import Node
from rss_safety_check import RSSParams, check_rss_safety

CONTROL_DT = 0.1


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def limit_steer_rate(ctrl, prev, max_d):
    ctrl.steer = clamp(ctrl.steer, prev - max_d, prev + max_d)
    return ctrl


def choose_straight(wp, ahead):
    opts = wp.next(ahead)
    if not opts:
        return None
    base = wp.transform.rotation.yaw

    def delta(c):
        return abs((c.transform.rotation.yaw - base + 180) % 360 - 180)

    return min(opts, key=delta)


def _node_from_actor(actor, eid: str) -> Node:
    tf = actor.get_transform()
    vel = actor.get_velocity()
    spd = math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2)
    return Node(
        node_type="Vehicle",
        external_id=eid,
        x=tf.location.x,
        y=tf.location.y,
        z=tf.location.z,
        heading=math.radians(tf.rotation.yaw),
        speed=spd,
        vx=vel.x,
        vy=vel.y,
    )


# ---------------------------------------------------------------------------
# Adjacent lane spawn helper
# ---------------------------------------------------------------------------

def find_adjacent_lane_spawn(world_map, spawn_tf):
    """Find a spawn transform in an adjacent lane (left or right)."""
    wp = world_map.get_waypoint(
        spawn_tf.location, project_to_road=True, lane_type=carla.LaneType.Driving
    )
    if wp is None:
        return None

    # Try right lane first, then left
    for get_lane in (wp.get_right_lane, wp.get_left_lane):
        adj = get_lane()
        if adj is not None and adj.lane_type == carla.LaneType.Driving:
            tf = adj.transform
            tf.location.z += 0.5  # small lift to avoid ground collision
            return tf, adj

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DURATION_S = 30
DRIFT_START_S = 8.0        # when the adjacent vehicle starts drifting
STATUS_INTERVAL = 2.0
DRIFT_STEER = 0.14         # steering input for the drift toward ego
DRIFT_MIN_GAP = 1.8        # reverse drift direction at this gap (m)
DRIFT_MAX_GAP = 4.5        # resume drift toward ego at this gap (m)


def main():
    client = carla.Client("127.0.0.1", 2000)
    client.set_timeout(10.0)
    world = client.get_world()
    original_settings = world.get_settings()

    settings = world.get_settings()
    settings.synchronous_mode = False
    world.apply_settings(settings)

    bp_lib = world.get_blueprint_library()
    vehicle_bps = bp_lib.filter("vehicle.*")
    spawn_points = world.get_map().get_spawn_points()
    world_map = world.get_map()

    print("=" * 70)
    print("RSS Lateral Safe-Distance Test")
    print("=" * 70)

    # Find a spawn point with an adjacent lane
    ego_vehicle = None
    adj_vehicle = None
    ego_spawn = None
    adj_spawn = None
    adj_wp = None

    for sp in spawn_points:
        result = find_adjacent_lane_spawn(world_map, sp)
        if result is None:
            continue
        adj_tf, adj_waypoint = result

        ego_vehicle = world.try_spawn_actor(vehicle_bps[0], sp)
        if ego_vehicle is None:
            continue

        adj_vehicle = world.try_spawn_actor(vehicle_bps[1], adj_tf)
        if adj_vehicle is None:
            ego_vehicle.destroy()
            ego_vehicle = None
            continue

        ego_spawn = sp
        adj_spawn = adj_tf
        adj_wp = adj_waypoint
        break

    if ego_vehicle is None or adj_vehicle is None:
        print("ERROR: could not spawn two vehicles in adjacent lanes")
        if ego_vehicle:
            ego_vehicle.destroy()
        if adj_vehicle:
            adj_vehicle.destroy()
        world.apply_settings(original_settings)
        return 1

    ego_vehicle.set_autopilot(False)
    adj_vehicle.set_autopilot(False)

    ego_ctrl = VehiclePIDController(
        ego_vehicle,
        args_lateral={"K_P": 0.80, "K_I": 0.0, "K_D": 0.24, "dt": CONTROL_DT},
        args_longitudinal={"K_P": 1.25, "K_I": 0.05, "K_D": 0.16, "dt": CONTROL_DT},
        max_throttle=1.0, max_brake=0.9, max_steering=0.45,
    )
    adj_ctrl = VehiclePIDController(
        adj_vehicle,
        args_lateral={"K_P": 0.80, "K_I": 0.0, "K_D": 0.24, "dt": CONTROL_DT},
        args_longitudinal={"K_P": 1.25, "K_I": 0.05, "K_D": 0.16, "dt": CONTROL_DT},
        max_throttle=1.0, max_brake=0.9, max_steering=0.45,
    )

    # Waypoint tracking for straight driving
    ego_wp = world_map.get_waypoint(
        ego_spawn.location, project_to_road=True, lane_type=carla.LaneType.Driving
    )
    ego_target_wp = choose_straight(ego_wp, 10.0) if ego_wp else None
    adj_target_wp = choose_straight(adj_wp, 10.0) if adj_wp else None

    cruise_kmh = 30.0
    rss_params = RSSParams()
    violation_count = 0
    safe_count = 0
    total_ticks = 0
    phase1_violations = 0
    phase2_violations = 0

    lat_dist0 = math.sqrt(
        (ego_spawn.location.x - adj_spawn.location.x) ** 2
        + (ego_spawn.location.y - adj_spawn.location.y) ** 2
    )

    print(f"  Ego: {vehicle_bps[0].id} at {ego_spawn.location}")
    print(f"  Adjacent: {vehicle_bps[1].id} at {adj_spawn.location}")
    print(f"  Initial centre-centre distance: {lat_dist0:.1f} m")
    print(f"  Phase 1 (0-{DRIFT_START_S:.0f}s): Both drive straight — expect no lateral violations")
    print(f"  Phase 2 ({DRIFT_START_S:.0f}s+): Adjacent drifts toward ego — expect lateral violations")
    print(f"  Duration: {DURATION_S} s")
    print("-" * 70)

    ego_prev_steer = 0.0
    adj_prev_steer = 0.0
    steer_lim = 0.06
    next_status = 0.0

    try:
        t0 = time.time()
        while time.time() - t0 < DURATION_S:
            loop0 = time.perf_counter()
            now = time.time()
            elapsed = now - t0
            drifting = elapsed >= DRIFT_START_S

            # -- Ego: drive straight --
            ego_loc = ego_vehicle.get_location()
            if ego_target_wp and ego_loc.distance(ego_target_wp.transform.location) < 5.0:
                ego_wp = ego_target_wp
                ego_target_wp = choose_straight(ego_wp, 10.0)
            if ego_target_wp:
                ec = ego_ctrl.run_step(cruise_kmh, ego_target_wp)
            else:
                ec = carla.VehicleControl(throttle=0.3, steer=0, brake=0)
            ec = limit_steer_rate(ec, ego_prev_steer, steer_lim)
            ego_prev_steer = ec.steer
            ego_vehicle.apply_control(ec)

            # -- Adjacent: drive straight, then drift toward ego --
            adj_loc = adj_vehicle.get_location()
            if adj_target_wp and adj_loc.distance(adj_target_wp.transform.location) < 5.0:
                adj_wp_now = adj_target_wp
                adj_target_wp = choose_straight(adj_wp_now, 10.0)
            if adj_target_wp:
                ac = adj_ctrl.run_step(cruise_kmh, adj_target_wp)
            else:
                ac = carla.VehicleControl(throttle=0.3, steer=0, brake=0)

            if drifting:
                # Oscillate toward ego: drift in when far, drift away when close.
                ego_tf = ego_vehicle.get_transform()
                adj_tf = adj_vehicle.get_transform()
                fwd_x = math.cos(math.radians(adj_tf.rotation.yaw))
                fwd_y = math.sin(math.radians(adj_tf.rotation.yaw))
                perp_x, perp_y = -fwd_y, fwd_x  # perpendicular
                dx = ego_tf.location.x - adj_tf.location.x
                dy = ego_tf.location.y - adj_tf.location.y
                cross = dx * perp_x + dy * perp_y
                lat_gap = abs(cross)  # lateral gap in adj's frame
                steer_sign = 1.0 if cross > 0 else -1.0
                # Drift toward ego when gap > DRIFT_MAX_GAP, away when < DRIFT_MIN_GAP
                if lat_gap < DRIFT_MIN_GAP:
                    ac.steer = -steer_sign * DRIFT_STEER  # steer away
                elif lat_gap > DRIFT_MAX_GAP:
                    ac.steer = steer_sign * DRIFT_STEER   # steer toward
                else:
                    # In the band: gentle drift toward ego
                    ac.steer = steer_sign * DRIFT_STEER * 0.5

            ac = limit_steer_rate(ac, adj_prev_steer, steer_lim)
            adj_prev_steer = ac.steer
            adj_vehicle.apply_control(ac)

            # -- RSS check --
            ego_node = _node_from_actor(ego_vehicle, "ego")
            adj_node = _node_from_actor(adj_vehicle, "adj")
            viols = check_rss_safety(ego_node, [adj_node], rss_params)
            total_ticks += 1
            lat_viols = [v for v in viols if v.rule == "lateral"]

            if lat_viols:
                violation_count += 1
                if drifting:
                    phase2_violations += 1
                else:
                    phase1_violations += 1
            else:
                safe_count += 1

            # -- periodic status --
            if now >= next_status:
                ego_tf2 = ego_vehicle.get_transform()
                adj_tf2 = adj_vehicle.get_transform()
                gap = math.sqrt(
                    (ego_tf2.location.x - adj_tf2.location.x) ** 2
                    + (ego_tf2.location.y - adj_tf2.location.y) ** 2
                )
                phase = "DRIFT" if drifting else "straight"
                tag = "VIOLATION" if lat_viols else "safe"
                safe_d = lat_viols[0].safe_distance if lat_viols else "n/a"
                safe_str = f"{safe_d:.2f}" if isinstance(safe_d, float) else safe_d
                print(
                    f"  t={elapsed:5.1f}s  gap={gap:5.2f}m  d_safe={safe_str}  "
                    f"phase={phase:8s}  [{tag}]"
                )
                next_status = now + STATUS_INTERVAL

            world.wait_for_tick()
            el = time.perf_counter() - loop0
            if el < CONTROL_DT:
                time.sleep(CONTROL_DT - el)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        ego_vehicle.destroy()
        adj_vehicle.destroy()
        world.apply_settings(original_settings)

    print()
    print("=" * 70)
    print("LATERAL RSS TEST SUMMARY")
    print("=" * 70)
    print(f"  Total ticks:            {total_ticks}")
    print(f"  Phase 1 violations:     {phase1_violations}  (expected ≈ 0)")
    print(f"  Phase 2 violations:     {phase2_violations}  (expected > 0)")
    print(f"  Total violations:       {violation_count}")
    print(f"  Safe ticks:             {safe_count}")
    if phase2_violations > 0:
        print(f"  RESULT: Lateral RSS violations correctly detected during drift phase.")
    else:
        print(f"  RESULT: No lateral violations detected — try increasing DRIFT_STEER.")
    return 0 if phase2_violations > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
