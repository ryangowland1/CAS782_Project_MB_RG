#!/usr/bin/env python3
"""
Run the RSS longitudinal scenario and produce paper-ready outputs:
  1. Per-tick CSV log  (data/results/rss_log.csv)
  2. Time-series plot  (data/results/rss_distance_plot.pdf + .png)
  3. Speed plot         (data/results/rss_speed_plot.pdf + .png)
  4. LaTeX table        (data/results/rss_table.tex)
  5. RSS parameters     (data/results/rss_params_table.tex)

Usage:
    python src/scenario_rss_results.py [--duration 30]
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path
from typing import List

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

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

import carla
from agents.navigation.controller import VehiclePIDController
from carla_scenegraph_export import Node
from rss_safety_check import (
    RSSParams,
    RSSViolation,
    check_rss_safety,
    rss_longitudinal_safe_distance,
)

# ── Helpers (from scenario_rss_longitudinal) ─────────────────────────────────

CONTROL_DT = 0.1
FOLLOW_GAP = 5.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def limit_steer_rate(ctrl, prev, max_d):
    ctrl.steer = clamp(ctrl.steer, prev - max_d, prev + max_d)
    return ctrl


def spawn_ahead(tf, dist):
    fwd = tf.get_forward_vector()
    return carla.Transform(
        carla.Location(
            x=tf.location.x + fwd.x * dist,
            y=tf.location.y + fwd.y * dist,
            z=tf.location.z + 0.5,
        ),
        tf.rotation,
    )


def spawn_behind(tf, dist):
    fwd = tf.get_forward_vector()
    return carla.Transform(
        carla.Location(
            x=tf.location.x - fwd.x * dist,
            y=tf.location.y - fwd.y * dist,
            z=tf.location.z + 0.5,
        ),
        tf.rotation,
    )


def choose_straight(wp, ahead):
    opts = wp.next(ahead)
    if not opts:
        return None
    base = wp.transform.rotation.yaw
    return min(opts, key=lambda c: abs((c.transform.rotation.yaw - base + 180) % 360 - 180))


def node_from_actor(actor, eid: str) -> Node:
    tf = actor.get_transform()
    vel = actor.get_velocity()
    spd = math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2)
    bb = actor.bounding_box
    return Node(
        node_type="Vehicle",
        external_id=eid,
        x=tf.location.x, y=tf.location.y, z=tf.location.z,
        heading=math.radians(tf.rotation.yaw),
        speed=spd, vx=vel.x, vy=vel.y,
        length=bb.extent.x * 2 if bb else None,
        width=bb.extent.y * 2 if bb else None,
    )


# ── Data row ─────────────────────────────────────────────────────────────────

CSV_HEADER = [
    "tick", "time_s",
    "ego_speed_ms", "lead_speed_ms",
    "actual_distance_m", "safe_distance_m",
    "violation",
]


# ── Run scenario & collect data ──────────────────────────────────────────────

def run_scenario(duration_s: int) -> List[dict]:
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

    actors = []

    ego_bp = vehicle_bps[0]
    ego_spawn = spawn_points[0]
    ego_vehicle = world.try_spawn_actor(ego_bp, ego_spawn)
    if not ego_vehicle:
        raise RuntimeError("Could not spawn ego vehicle")
    actors.append(ego_vehicle)

    lead_bp = vehicle_bps[1]
    lead_vehicle = None
    lead_spawn = None
    for gap in (10.0, 8.0, 6.0):
        candidate = spawn_ahead(ego_spawn, gap)
        lead_vehicle = world.try_spawn_actor(lead_bp, candidate)
        if lead_vehicle:
            lead_spawn = candidate
            break
    if not lead_vehicle:
        for a in actors:
            a.destroy()
        raise RuntimeError("Could not spawn lead vehicle")
    actors.append(lead_vehicle)

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

    lead_wp = world_map.get_waypoint(
        lead_spawn.location, project_to_road=True, lane_type=carla.LaneType.Driving
    )
    lead_target_wp = choose_straight(lead_wp, 10.0) if lead_wp else None
    lead_cruise_kmh = 30.0

    rss_params = RSSParams()
    lead_prev_steer = 0.0
    ego_prev_steer = 0.0
    steer_lim = 0.06
    rows: List[dict] = []
    tick = 0

    print(f"  Running scenario for {duration_s}s ...")

    try:
        t0 = time.time()
        while True:
            loop0 = time.perf_counter()
            elapsed = time.time() - t0
            if elapsed >= duration_s:
                break

            # -- Lead control --
            lead_target_kmh = lead_cruise_kmh + random.uniform(-4, 4)
            if random.random() < 0.03:
                lead_target_kmh = 0.0

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

            # -- Ego control --
            lead_tf = lead_vehicle.get_transform()
            ego_tf = ego_vehicle.get_transform()
            dx = ego_tf.location.x - lead_tf.location.x
            dy = ego_tf.location.y - lead_tf.location.y
            dist = math.sqrt(dx ** 2 + dy ** 2)

            target_tf = spawn_behind(lead_tf, FOLLOW_GAP)
            twp = world_map.get_waypoint(
                target_tf.location, project_to_road=True, lane_type=carla.LaneType.Driving
            )
            if twp is None:
                twp = world_map.get_waypoint(
                    lead_tf.location, project_to_road=True, lane_type=carla.LaneType.Driving
                )
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
            ego_node = node_from_actor(ego_vehicle, "ego")
            lead_node = node_from_actor(lead_vehicle, "lead")
            viols = check_rss_safety(ego_node, [lead_node], rss_params)
            lon_viols = [v for v in viols if v.rule == "longitudinal"]

            safe_dist = (
                lon_viols[0].safe_distance
                if lon_viols
                else rss_longitudinal_safe_distance(
                    max(ego_node.speed or 0, 0),
                    max(lead_node.speed or 0, 0),
                    rss_params,
                )
            )

            tick += 1
            rows.append({
                "tick": tick,
                "time_s": round(elapsed, 3),
                "ego_speed_ms": round(ego_node.speed or 0, 3),
                "lead_speed_ms": round(lead_node.speed or 0, 3),
                "actual_distance_m": round(dist, 3),
                "safe_distance_m": round(safe_dist, 3),
                "violation": 1 if lon_viols else 0,
            })

            if tick % 100 == 0:
                print(f"    tick {tick}  t={elapsed:.1f}s  dist={dist:.1f}m")

            world.wait_for_tick()
            dt = time.perf_counter() - loop0
            if dt < CONTROL_DT:
                time.sleep(CONTROL_DT - dt)

    except KeyboardInterrupt:
        print("\n  Interrupted.")
    finally:
        for a in reversed(actors):
            a.destroy()
        world.apply_settings(original_settings)

    return rows


# ── Output generators ────────────────────────────────────────────────────────

def write_csv(rows: List[dict], path: Path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f"  CSV: {path}")


def make_distance_plot(rows: List[dict], path_stem: Path):
    t = [r["time_s"] for r in rows]
    actual = [r["actual_distance_m"] for r in rows]
    safe = [r["safe_distance_m"] for r in rows]
    viol = [r["violation"] for r in rows]

    fig, ax = plt.subplots(figsize=(7, 3.5))

    # Shade violation regions
    in_violation = False
    start = None
    for i, v in enumerate(viol):
        if v and not in_violation:
            start = t[i]
            in_violation = True
        elif not v and in_violation:
            ax.axvspan(start, t[i], alpha=0.10, color="#dc2626", zorder=0)
            in_violation = False
    if in_violation:
        ax.axvspan(start, t[-1], alpha=0.10, color="#dc2626", zorder=0)

    ax.plot(t, actual, color="#1f77b4", linewidth=1.2, label="Actual distance")
    ax.plot(t, safe, color="#dc2626", linewidth=1.2, linestyle="--", label="RSS safe distance")
    ax.fill_between(t, 0, actual, where=[a < s for a, s in zip(actual, safe)],
                     alpha=0.18, color="#dc2626", interpolate=True)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Distance (m)")
    ax.set_title("Longitudinal Distance vs.\ RSS Safe Distance")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlim(t[0], t[-1])
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    fig.savefig(str(path_stem) + ".pdf", dpi=300)
    fig.savefig(str(path_stem) + ".png", dpi=200)
    plt.close(fig)
    print(f"  Plot: {path_stem}.pdf / .png")


def make_speed_plot(rows: List[dict], path_stem: Path):
    t = [r["time_s"] for r in rows]
    ego_spd = [r["ego_speed_ms"] for r in rows]
    lead_spd = [r["lead_speed_ms"] for r in rows]

    fig, ax = plt.subplots(figsize=(7, 3.0))
    ax.plot(t, ego_spd, color="#1f77b4", linewidth=1.1, label="Ego speed")
    ax.plot(t, lead_spd, color="#2ca02c", linewidth=1.1, label="Lead speed")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Speed (m/s)")
    ax.set_title("Vehicle Speeds Over Time")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlim(t[0], t[-1])
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    fig.savefig(str(path_stem) + ".pdf", dpi=300)
    fig.savefig(str(path_stem) + ".png", dpi=200)
    plt.close(fig)
    print(f"  Plot: {path_stem}.pdf / .png")


def make_combined_plot(rows: List[dict], path_stem: Path):
    """Two-subplot figure: distance + speed on shared time axis."""
    t = [r["time_s"] for r in rows]
    actual = [r["actual_distance_m"] for r in rows]
    safe = [r["safe_distance_m"] for r in rows]
    ego_spd = [r["ego_speed_ms"] for r in rows]
    lead_spd = [r["lead_speed_ms"] for r in rows]
    viol = [r["violation"] for r in rows]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5.5), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 2]})

    # Top: distance
    in_viol = False
    start = None
    for i, v in enumerate(viol):
        if v and not in_viol:
            start = t[i]
            in_viol = True
        elif not v and in_viol:
            ax1.axvspan(start, t[i], alpha=0.10, color="#dc2626", zorder=0)
            in_viol = False
    if in_viol:
        ax1.axvspan(start, t[-1], alpha=0.10, color="#dc2626", zorder=0)

    ax1.plot(t, actual, color="#1f77b4", linewidth=1.2, label="Actual distance")
    ax1.plot(t, safe, color="#dc2626", linewidth=1.2, linestyle="--", label="RSS safe distance")
    ax1.fill_between(t, 0, actual, where=[a < s for a, s in zip(actual, safe)],
                      alpha=0.15, color="#dc2626", interpolate=True)
    ax1.set_ylabel("Distance (m)")
    ax1.set_title("RSS Longitudinal Safety Analysis")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_ylim(bottom=0)
    ax1.grid(True, alpha=0.3)

    # Bottom: speed
    ax2.plot(t, ego_spd, color="#1f77b4", linewidth=1.1, label="Ego")
    ax2.plot(t, lead_spd, color="#2ca02c", linewidth=1.1, label="Lead")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Speed (m/s)")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.set_ylim(bottom=0)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(t[0], t[-1])

    fig.tight_layout()
    fig.savefig(str(path_stem) + ".pdf", dpi=300)
    fig.savefig(str(path_stem) + ".png", dpi=200)
    plt.close(fig)
    print(f"  Plot: {path_stem}.pdf / .png")


def write_summary_table(rows: List[dict], path: Path):
    """Write a LaTeX table with scenario summary statistics."""
    n = len(rows)
    n_viol = sum(r["violation"] for r in rows)
    n_safe = n - n_viol
    pct = n_viol / max(n, 1) * 100

    dists = [r["actual_distance_m"] for r in rows]
    safes = [r["safe_distance_m"] for r in rows]
    ego_spds = [r["ego_speed_ms"] for r in rows]
    lead_spds = [r["lead_speed_ms"] for r in rows]

    duration = rows[-1]["time_s"] - rows[0]["time_s"] if n > 1 else 0

    lines = [
        r"\begin{table}[ht]",
        r"  \centering",
        r"  \caption{RSS Longitudinal Safety Test -- Summary Results}",
        r"  \label{tab:rss-results}",
        r"  \begin{tabular}{l r}",
        r"    \toprule",
        r"    \textbf{Metric} & \textbf{Value} \\",
        r"    \midrule",
        f"    Duration (s) & {duration:.1f} \\\\",
        f"    Total ticks & {n} \\\\",
        f"    Violation ticks & {n_viol} \\\\",
        f"    Safe ticks & {n_safe} \\\\",
        f"    Violation rate (\\%) & {pct:.1f} \\\\",
        r"    \midrule",
        f"    Actual distance -- mean (m) & {statistics.mean(dists):.2f} \\\\",
        f"    Actual distance -- min (m) & {min(dists):.2f} \\\\",
        f"    Actual distance -- max (m) & {max(dists):.2f} \\\\",
        f"    Actual distance -- std (m) & {statistics.stdev(dists):.2f} \\\\",
        r"    \midrule",
        f"    RSS safe distance -- mean (m) & {statistics.mean(safes):.2f} \\\\",
        f"    RSS safe distance -- min (m) & {min(safes):.2f} \\\\",
        f"    RSS safe distance -- max (m) & {max(safes):.2f} \\\\",
        r"    \midrule",
        f"    Ego speed -- mean (m/s) & {statistics.mean(ego_spds):.2f} \\\\",
        f"    Ego speed -- max (m/s) & {max(ego_spds):.2f} \\\\",
        f"    Lead speed -- mean (m/s) & {statistics.mean(lead_spds):.2f} \\\\",
        f"    Lead speed -- max (m/s) & {max(lead_spds):.2f} \\\\",
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  LaTeX table: {path}")


def write_params_table(path: Path):
    """Write a LaTeX table with RSS parameter values."""
    p = RSSParams()
    lines = [
        r"\begin{table}[ht]",
        r"  \centering",
        r"  \caption{RSS Model Parameters}",
        r"  \label{tab:rss-params}",
        r"  \begin{tabular}{l l r l}",
        r"    \toprule",
        r"    \textbf{Parameter} & \textbf{Symbol} & \textbf{Value} & \textbf{Unit} \\",
        r"    \midrule",
        f"    Response time & $\\rho$ & {p.rho} & s \\\\",
        f"    Max longitudinal accel & $a_{{\\mathrm{{lon,max}}}}$ & {p.a_lon_max} & m/s$^2$ \\\\",
        f"    Min braking decel (ego) & $b_{{\\mathrm{{lon,min}}}}$ & {p.b_lon_min} & m/s$^2$ \\\\",
        f"    Max braking decel (other) & $b_{{\\mathrm{{lon,max}}}}$ & {p.b_lon_max} & m/s$^2$ \\\\",
        f"    Max lateral accel & $a_{{\\mathrm{{lat,max}}}}$ & {p.a_lat_max} & m/s$^2$ \\\\",
        f"    Min lateral braking decel & $b_{{\\mathrm{{lat,min}}}}$ & {p.b_lat_min} & m/s$^2$ \\\\",
        f"    Lateral fluctuation margin & $\\mu$ & {p.mu} & m \\\\",
        r"    \midrule",
        f"    Follow gap (test) & -- & {FOLLOW_GAP} & m \\\\",
        f"    Lead cruise speed (test) & -- & 30 & km/h \\\\",
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  LaTeX table: {path}")


def print_summary(rows: List[dict]):
    n = len(rows)
    n_viol = sum(r["violation"] for r in rows)
    pct = n_viol / max(n, 1) * 100
    dists = [r["actual_distance_m"] for r in rows]

    print()
    print("=" * 60)
    print("  SCENARIO RESULTS")
    print("=" * 60)
    print(f"  Ticks: {n}  |  Violations: {n_viol} ({pct:.1f}%)")
    print(f"  Distance: mean={statistics.mean(dists):.1f}m  min={min(dists):.1f}m  max={max(dists):.1f}m")
    print("=" * 60)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run RSS scenario and produce paper outputs")
    parser.add_argument("--duration", type=int, default=30, help="Scenario duration (s)")
    parser.add_argument("--out-dir", default="data/results", help="Output directory")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("RSS Scenario → Paper Results")
    print("=" * 60)

    rows = run_scenario(args.duration)

    if len(rows) < 2:
        print("ERROR: not enough data collected")
        return 1

    print_summary(rows)

    print("\nGenerating outputs ...")
    write_csv(rows, out / "rss_log.csv")
    make_distance_plot(rows, out / "rss_distance_plot")
    make_speed_plot(rows, out / "rss_speed_plot")
    make_combined_plot(rows, out / "rss_combined_plot")
    write_summary_table(rows, out / "rss_table.tex")
    write_params_table(out / "rss_params_table.tex")

    print("\nDone. All outputs in:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
