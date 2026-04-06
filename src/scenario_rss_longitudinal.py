#!/usr/bin/env python3
"""
CARLA Scenario: RSS Longitudinal Safe-Distance Test
=====================================================
Spawns ego + lead vehicle in the same lane.  Ego deliberately follows
at a distance below the RSS safe longitudinal distance so that
violations are reliably triggered when both vehicles are in motion.

The lead vehicle cruises at ~30 km/h, randomly brakes, and resumes.
The ego vehicle follows using a PID controller with a short target
gap (~5 m), well inside the RSS envelope (~13 m at 30 km/h).

Duration: configurable (default 30 s).  Prints RSS status every tick
and a summary at exit.
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

# ---------------------------------------------------------------------------
# Helpers (reused from scenario_ego_follow)
# ---------------------------------------------------------------------------

CONTROL_DT = 0.1


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def limit_steer_rate(ctrl, prev, max_d):
    ctrl.steer = clamp(ctrl.steer, prev - max_d, prev + max_d)
    return ctrl


def spawn_ahead(tf, dist):
    fwd = tf.get_forward_vector()
    loc = carla.Location(
        x=tf.location.x + fwd.x * dist,
        y=tf.location.y + fwd.y * dist,
        z=tf.location.z + 0.5,
    )
    return carla.Transform(loc, tf.rotation)


def spawn_behind(tf, dist):
    fwd = tf.get_forward_vector()
    loc = carla.Location(
        x=tf.location.x - fwd.x * dist,
        y=tf.location.y - fwd.y * dist,
        z=tf.location.z + 0.5,
    )
    return carla.Transform(loc, tf.rotation)


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
# Main
# ---------------------------------------------------------------------------

DURATION_S = 120
FOLLOW_GAP = 5.0          # intentionally below RSS safe distance
STATUS_INTERVAL = 2.0


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

    if len(spawn_points) < 2:
        print("ERROR: not enough spawn points")
        return 1

    print("=" * 70)
    print("RSS Longitudinal Safe-Distance Test")
    print("=" * 70)

    # Spawn ego
    ego_bp = vehicle_bps[0]
    ego_spawn = spawn_points[0]
    ego_vehicle = world.try_spawn_actor(ego_bp, ego_spawn)
    if ego_vehicle is None:
        print("ERROR: could not spawn ego")
        return 1

    # Spawn lead ahead
    lead_bp = vehicle_bps[1]
    lead_vehicle = None
    lead_spawn = None
    for gap in (10.0, 8.0, 6.0):
        candidate = spawn_ahead(ego_spawn, gap)
        lead_vehicle = world.try_spawn_actor(lead_bp, candidate)
        if lead_vehicle is not None:
            lead_spawn = candidate
            break
    if lead_vehicle is None:
        print("ERROR: could not spawn lead")
        ego_vehicle.destroy()
        return 1

    ego_vehicle.set_autopilot(False)
    lead_vehicle.set_autopilot(False)

    lead_ctrl = VehiclePIDController(
        lead_vehicle,
        args_lateral={"K_P": 0.8, "K_I": 0.0, "K_D": 0.24, "dt": CONTROL_DT},
        args_longitudinal={"K_P": 1.25, "K_I": 0.05, "K_D": 0.16, "dt": CONTROL_DT},
        max_throttle=1.0, max_brake=0.9, max_steering=0.45,
    )
    ego_ctrl = VehiclePIDController(
        ego_vehicle,
        args_lateral={"K_P": 0.72, "K_I": 0.0, "K_D": 0.28, "dt": CONTROL_DT},
        args_longitudinal={"K_P": 1.1, "K_I": 0.06, "K_D": 0.22, "dt": CONTROL_DT},
        max_throttle=0.95, max_brake=0.75, max_steering=0.45,
    )

    lead_wp = world_map.get_waypoint(lead_spawn.location, project_to_road=True, lane_type=carla.LaneType.Driving)
    lead_target_wp = choose_straight(lead_wp, 10.0) if lead_wp else None
    lead_cruise_kmh = 30.0

    rss_params = RSSParams()
    violation_count = 0
    safe_count = 0
    total_ticks = 0

    print(f"  Ego: {ego_bp.id} at {ego_spawn.location}")
    print(f"  Lead: {lead_bp.id} at {lead_spawn.location}")
    print(f"  Target follow gap: {FOLLOW_GAP} m  (RSS safe ≈ 13 m at 30 km/h)")
    print(f"  Duration: {DURATION_S} s")
    print("-" * 70)

    lead_prev_steer = 0.0
    ego_prev_steer = 0.0
    steer_lim = 0.06
    next_status = 0.0

    try:
        t0 = time.time()
        while time.time() - t0 < DURATION_S:
            loop0 = time.perf_counter()
            now = time.time()

            # -- Lead vehicle: cruise with random brakes --
            lead_target_kmh = lead_cruise_kmh + random.uniform(-4, 4)
            if random.random() < 0.03:
                lead_target_kmh = 0.0  # surprise brake

            lead_loc = lead_vehicle.get_location()
            if lead_target_wp and lead_loc.distance(lead_target_wp.transform.location) < 5.0:
                lead_wp = lead_target_wp
                lead_target_wp = choose_straight(lead_wp, 10.0)
            if lead_target_wp:
                lc = lead_ctrl.run_step(lead_target_kmh, lead_target_wp)
            else:
                lc = carla.VehicleControl(throttle=0, steer=0, brake=0.25)
            lc = limit_steer_rate(lc, lead_prev_steer, steer_lim)
            lead_prev_steer = lc.steer
            lead_vehicle.apply_control(lc)

            # -- Ego vehicle: follow lead closely --
            lead_tf = lead_vehicle.get_transform()
            ego_tf = ego_vehicle.get_transform()
            dx = ego_tf.location.x - lead_tf.location.x
            dy = ego_tf.location.y - lead_tf.location.y
            dist = math.sqrt(dx ** 2 + dy ** 2)

            target_tf = spawn_behind(lead_tf, FOLLOW_GAP)
            twp = world_map.get_waypoint(target_tf.location, project_to_road=True, lane_type=carla.LaneType.Driving)
            if twp is None:
                twp = world_map.get_waypoint(lead_tf.location, project_to_road=True, lane_type=carla.LaneType.Driving)
            if twp is None:
                world.wait_for_tick()
                continue

            preview = choose_straight(twp, 4.0)
            twp = preview if preview else twp

            lead_vel = lead_vehicle.get_velocity()
            lead_spd = math.sqrt(lead_vel.x ** 2 + lead_vel.y ** 2 + lead_vel.z ** 2)
            target_kmh = lead_spd * 3.6 + 2.0 * (dist - FOLLOW_GAP)

            ec = ego_ctrl.run_step(target_kmh, twp)
            ec = limit_steer_rate(ec, ego_prev_steer, steer_lim)
            ego_prev_steer = ec.steer
            ego_vehicle.apply_control(ec)

            # -- RSS check --
            ego_node = _node_from_actor(ego_vehicle, "ego")
            lead_node = _node_from_actor(lead_vehicle, "lead")
            viols = check_rss_safety(ego_node, [lead_node], rss_params)
            total_ticks += 1
            lon_viols = [v for v in viols if v.rule == "longitudinal"]

            if lon_viols:
                violation_count += 1
            else:
                safe_count += 1

            # -- periodic status --
            if now >= next_status:
                ego_spd = ego_node.speed or 0.0
                lead_spd_v = lead_node.speed or 0.0
                tag = "VIOLATION" if lon_viols else "safe"
                d_safe = lon_viols[0].safe_distance if lon_viols else rss_longitudinal_safe_distance_quick(ego_spd, lead_spd_v, rss_params)
                print(
                    f"  t={now - t0:5.1f}s  dist={dist:5.1f}m  d_safe={d_safe:5.1f}m  "
                    f"ego={ego_spd:4.1f} m/s  lead={lead_spd_v:4.1f} m/s  [{tag}]"
                )
                next_status = now + STATUS_INTERVAL

            world.wait_for_tick()
            elapsed = time.perf_counter() - loop0
            if elapsed < CONTROL_DT:
                time.sleep(CONTROL_DT - elapsed)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        lead_vehicle.destroy()
        ego_vehicle.destroy()
        world.apply_settings(original_settings)

    print()
    print("=" * 70)
    print("LONGITUDINAL RSS TEST SUMMARY")
    print("=" * 70)
    print(f"  Total ticks:       {total_ticks}")
    print(f"  Violations:        {violation_count}")
    print(f"  Safe ticks:        {safe_count}")
    pct = violation_count / max(total_ticks, 1) * 100
    print(f"  Violation rate:    {pct:.1f}%")
    if violation_count > 0:
        print(f"  RESULT: Longitudinal RSS violations correctly detected.")
    else:
        print(f"  RESULT: No violations detected — increase speed or decrease follow gap.")
    return 0 if violation_count > 0 else 1


def rss_longitudinal_safe_distance_quick(v_ego, v_other, p):
    """Inline copy for status display."""
    from rss_safety_check import rss_longitudinal_safe_distance
    return rss_longitudinal_safe_distance(max(v_ego, 0), max(v_other, 0), p)


if __name__ == "__main__":
    raise SystemExit(main())
