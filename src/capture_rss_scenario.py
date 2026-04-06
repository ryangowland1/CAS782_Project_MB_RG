#!/usr/bin/env python3
"""
Capture side-by-side frames: CARLA 3rd-person camera + scene-graph diagram.

Runs the RSS longitudinal scenario, attaches a chase camera to the ego
vehicle, and renders a scene-graph diagram (nodes, edges, RSS status)
using Pillow.  At exit, calls ffmpeg to combine frames into a video.

Usage:
    python src/capture_rss_scenario.py [--duration 30] [--fps 10] [--no-video]
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import queue
import random
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import carla
from agents.navigation.controller import VehiclePIDController
from carla_scenegraph_export import Edge, Node
from rss_safety_check import RSSParams, RSSViolation, check_rss_safety

# ── constants ────────────────────────────────────────────────────────────────
CONTROL_DT = 0.1
FOLLOW_GAP = 5.0
IMG_W, IMG_H = 960, 540          # per-panel resolution
GRAPH_W, GRAPH_H = IMG_W, IMG_H  # scene-graph panel size

# Colors (RGB)
COL_BG       = (252, 253, 255)
COL_VEHICLE  = ( 31, 119, 180)
COL_ROAD     = ( 44, 160,  44)
COL_EDGE_VEH = (115, 132, 151)
COL_EDGE_LN  = (148, 163, 184)
COL_RSS_LON  = (220,  38,  38)
COL_RSS_LAT  = (234,  88,  12)
COL_FOLLOW   = (124,  58, 237)
COL_TEXT     = ( 26,  26,  26)
COL_SAFE     = ( 22, 163,  74)
COL_WARN     = (220,  38,  38)
COL_SUBTEXT  = (100, 116, 139)

# ── helpers ──────────────────────────────────────────────────────────────────

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


# ── Scene-graph diagram renderer (Pillow) ───────────────────────────────────

def _try_font(size: int):
    """Try to load a proportional font; fall back to default."""
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


_FONT_TITLE = _try_font(18)
_FONT_LABEL = _try_font(14)
_FONT_SMALL = _try_font(11)
_FONT_BADGE = _try_font(12)


def render_scene_graph(
    ego: Node,
    lead: Node,
    violations: List[RSSViolation],
    edges: List[Tuple[str, str, str]],   # (edge_type, src_id, dst_id)
    tick: int,
    elapsed: float,
) -> Image.Image:
    """Return a Pillow image of the scene-graph diagram."""
    img = Image.new("RGB", (GRAPH_W, GRAPH_H), COL_BG)
    draw = ImageDraw.Draw(img)

    # ── header ──
    draw.text((14, 8), "CARLA Scene Graph", fill=COL_TEXT, font=_FONT_TITLE)
    draw.text((14, 30), f"Tick {tick}  |  t = {elapsed:.1f}s", fill=COL_SUBTEXT, font=_FONT_SMALL)

    # ── RSS status badge ──
    if violations:
        badge_text = f"  RSS VIOLATION x{len(violations)}  "
        badge_color = COL_WARN
    else:
        badge_text = "  RSS SAFE  "
        badge_color = COL_SAFE
    bw = draw.textlength(badge_text, font=_FONT_BADGE)
    bx = GRAPH_W - int(bw) - 14
    draw.rounded_rectangle([bx, 10, bx + int(bw) + 4, 30], radius=4, fill=badge_color)
    draw.text((bx + 2, 12), badge_text, fill=(255, 255, 255), font=_FONT_BADGE)

    # ── violation detail lines ──
    vy = 36
    for v in violations[:4]:
        tag = v.rule.upper()
        detail = f"{tag}: {v.ego_id}→{v.other_id}  {v.actual_distance:.1f}m / {v.safe_distance:.1f}m safe"
        draw.text((GRAPH_W - 14 - draw.textlength(detail, font=_FONT_SMALL), vy),
                  detail, fill=COL_WARN, font=_FONT_SMALL)
        vy += 16

    # ── compute node positions in diagram space ──
    # Two vehicles in a row, road segments above if present
    nodes_info: Dict[str, Tuple[float, float, Tuple[int, int, int], str]] = {}
    ego_x, ego_y = GRAPH_W * 0.30, GRAPH_H * 0.55
    lead_x, lead_y = GRAPH_W * 0.70, GRAPH_H * 0.55
    nodes_info[ego.external_id] = (ego_x, ego_y, COL_VEHICLE, "Vehicle")
    nodes_info[lead.external_id] = (lead_x, lead_y, COL_VEHICLE, "Vehicle")

    # ── draw edges ──
    for etype, src, dst in edges:
        if src not in nodes_info or dst not in nodes_info:
            continue
        sx, sy = nodes_info[src][:2]
        dx, dy = nodes_info[dst][:2]
        if etype.startswith("rss_"):
            color = COL_RSS_LON if "longitudinal" in etype else COL_RSS_LAT
            width = 3
        elif etype == "following":
            color = COL_FOLLOW
            width = 2
        elif etype == "vehicle":
            color = COL_EDGE_VEH
            width = 2
        else:
            color = COL_EDGE_LN
            width = 1
        draw.line([(sx, sy), (dx, dy)], fill=color, width=width)

    # ── draw nodes ──
    for nid, (nx, ny, color, ntype) in nodes_info.items():
        r = 14
        draw.rounded_rectangle([nx - r, ny - r, nx + r, ny + r], radius=4, fill=color)
        # id label
        draw.text((nx, ny - r - 18), nid, fill=COL_TEXT, font=_FONT_LABEL, anchor="mm")

    # ── speed labels under vehicles ──
    ego_spd = f"{ego.speed:.1f} m/s" if ego.speed and ego.speed > 0.01 else "stopped"
    lead_spd = f"{lead.speed:.1f} m/s" if lead.speed and lead.speed > 0.01 else "stopped"
    draw.text((ego_x, ego_y + 24), f"Ego: {ego_spd}", fill=COL_SUBTEXT, font=_FONT_SMALL, anchor="mm")
    draw.text((lead_x, lead_y + 24), f"Lead: {lead_spd}", fill=COL_SUBTEXT, font=_FONT_SMALL, anchor="mm")

    # ── distance bar between vehicles ──
    ego_tf_x, lead_tf_x = ego.x, lead.x
    dist = math.sqrt((ego.x - lead.x) ** 2 + (ego.y - lead.y) ** 2)
    bar_y = GRAPH_H * 0.75
    draw.line([(ego_x, bar_y), (lead_x, bar_y)], fill=COL_TEXT, width=1)
    draw.line([(ego_x, bar_y - 6), (ego_x, bar_y + 6)], fill=COL_TEXT, width=1)
    draw.line([(lead_x, bar_y - 6), (lead_x, bar_y + 6)], fill=COL_TEXT, width=1)

    dist_label = f"dist = {dist:.1f} m"
    draw.text(((ego_x + lead_x) / 2, bar_y - 12), dist_label, fill=COL_TEXT, font=_FONT_LABEL, anchor="mm")

    if violations:
        safe_d = violations[0].safe_distance
        safe_label = f"RSS safe = {safe_d:.1f} m"
        draw.text(((ego_x + lead_x) / 2, bar_y + 14), safe_label, fill=COL_WARN, font=_FONT_SMALL, anchor="mm")

    # ── legend ──
    ly = GRAPH_H - 30
    items = [
        (COL_RSS_LON, "RSS Longitudinal"),
        (COL_RSS_LAT, "RSS Lateral"),
        (COL_EDGE_VEH, "Proximity"),
        (COL_FOLLOW, "Following"),
    ]
    lx = 14
    for color, label in items:
        draw.line([(lx, ly + 6), (lx + 18, ly + 6)], fill=color, width=3)
        lx += 22
        draw.text((lx, ly), label, fill=COL_SUBTEXT, font=_FONT_SMALL)
        lx += int(draw.textlength(label, font=_FONT_SMALL)) + 14

    return img


# ── Camera callback ──────────────────────────────────────────────────────────

class CameraCapture:
    """Thread-safe single-frame buffer for a CARLA camera sensor."""

    def __init__(self):
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()

    def callback(self, image):
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = array.reshape((image.height, image.width, 4))[:, :, :3]  # BGRA → BGR
        array = array[:, :, ::-1]  # BGR → RGB
        with self._lock:
            self._frame = array.copy()

    def get(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None


# ── Main ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Capture RSS scenario side-by-side video")
    p.add_argument("--duration", type=int, default=30, help="Scenario duration in seconds")
    p.add_argument("--fps", type=int, default=10, help="Capture frame rate")
    p.add_argument("--no-video", action="store_true", help="Skip ffmpeg video encoding")
    p.add_argument("--out-dir", default="data/capture", help="Output directory")
    return p.parse_args()


def main():
    args = parse_args()
    out = Path(args.out_dir)
    frames_dir = out / "frames"

    # Clean previous capture
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

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

    actors_to_destroy = []

    print("=" * 60)
    print("RSS Scenario Capture")
    print(f"  Duration: {args.duration}s  |  FPS: {args.fps}  |  Out: {out}")
    print("=" * 60)

    # ── Spawn vehicles ──
    ego_bp = vehicle_bps[0]
    ego_spawn = spawn_points[0]
    ego_vehicle = world.try_spawn_actor(ego_bp, ego_spawn)
    if not ego_vehicle:
        print("ERROR: could not spawn ego")
        return 1
    actors_to_destroy.append(ego_vehicle)

    lead_bp = vehicle_bps[1]
    lead_vehicle = None
    for gap in (10.0, 8.0, 6.0):
        lead_vehicle = world.try_spawn_actor(lead_bp, spawn_ahead(ego_spawn, gap))
        if lead_vehicle:
            break
    if not lead_vehicle:
        print("ERROR: could not spawn lead")
        for a in actors_to_destroy:
            a.destroy()
        return 1
    actors_to_destroy.append(lead_vehicle)

    # ── Attach 3rd-person camera to ego ──
    cam_bp = bp_lib.find("sensor.camera.rgb")
    cam_bp.set_attribute("image_size_x", str(IMG_W))
    cam_bp.set_attribute("image_size_y", str(IMG_H))
    cam_bp.set_attribute("fov", "90")
    cam_transform = carla.Transform(
        carla.Location(x=-6.0, z=3.0),   # behind and above
        carla.Rotation(pitch=-12.0),
    )
    camera = world.spawn_actor(cam_bp, cam_transform, attach_to=ego_vehicle)
    actors_to_destroy.append(camera)

    cam_capture = CameraCapture()
    camera.listen(cam_capture.callback)

    # ── PID controllers ──
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
        spawn_ahead(ego_spawn, 10.0).location, project_to_road=True, lane_type=carla.LaneType.Driving
    )
    lead_target_wp = choose_straight(lead_wp, 10.0) if lead_wp else None
    lead_cruise_kmh = 30.0

    rss_params = RSSParams()
    lead_prev_steer = 0.0
    ego_prev_steer = 0.0
    steer_lim = 0.06

    frame_interval = 1.0 / args.fps
    next_capture = 0.0
    frame_idx = 0
    total_violations = 0
    total_ticks = 0

    print(f"  Capturing at {args.fps} fps → {frames_dir}")
    print("-" * 60)

    try:
        t0 = time.time()
        while True:
            loop0 = time.perf_counter()
            elapsed = time.time() - t0
            if elapsed >= args.duration:
                break

            # ── Lead vehicle control ──
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

            # ── Ego vehicle control ──
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

            # ── RSS check ──
            ego_node = node_from_actor(ego_vehicle, "ego")
            lead_node = node_from_actor(lead_vehicle, "lead")
            viols = check_rss_safety(ego_node, [lead_node], rss_params)
            total_ticks += 1
            if viols:
                total_violations += 1

            # ── Capture frame at fixed FPS ──
            if elapsed >= next_capture:
                cam_frame = cam_capture.get()
                if cam_frame is not None:
                    # Build scene-graph diagram
                    graph_edges = [("vehicle", ego_node.external_id, lead_node.external_id)]
                    graph_img = render_scene_graph(
                        ego_node, lead_node, viols, graph_edges, total_ticks, elapsed
                    )

                    # Resize camera frame to match
                    carla_img = Image.fromarray(cam_frame).resize((IMG_W, IMG_H), Image.LANCZOS)

                    # Stitch side by side
                    combined = Image.new("RGB", (IMG_W * 2, IMG_H), (0, 0, 0))
                    combined.paste(carla_img, (0, 0))
                    combined.paste(graph_img, (IMG_W, 0))

                    fname = frames_dir / f"frame_{frame_idx:05d}.png"
                    combined.save(fname, "PNG")
                    frame_idx += 1

                    tag = "VIOLATION" if viols else "safe"
                    if frame_idx % (args.fps * 2) == 1:  # print every ~2s
                        print(f"  t={elapsed:5.1f}s  frame={frame_idx}  dist={dist:.1f}m  [{tag}]")

                next_capture += frame_interval

            world.wait_for_tick()
            loop_dt = time.perf_counter() - loop0
            if loop_dt < CONTROL_DT:
                time.sleep(CONTROL_DT - loop_dt)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        camera.stop()
        for a in reversed(actors_to_destroy):
            a.destroy()
        world.apply_settings(original_settings)

    print()
    print("=" * 60)
    print(f"  Frames captured: {frame_idx}")
    print(f"  Violations: {total_violations}/{total_ticks} ticks")
    print("=" * 60)

    # ── Encode video with ffmpeg ──
    if not args.no_video and frame_idx > 0:
        video_path = out / "rss_scenario_capture.mp4"
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-framerate", str(args.fps),
            "-i", str(frames_dir / "frame_%05d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            str(video_path),
        ]
        print(f"\n  Encoding video: {video_path}")
        print(f"  Command: {' '.join(ffmpeg_cmd)}")
        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            print(f"  Video saved: {video_path}")
        except FileNotFoundError:
            print("  ERROR: ffmpeg not found. Restart your shell (winget install added it to PATH).")
            print(f"  Frames are in: {frames_dir}")
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: ffmpeg failed: {e.stderr.decode()[:500]}")
            print(f"  Frames are in: {frames_dir}")
    elif frame_idx > 0:
        print(f"\n  --no-video: frames saved to {frames_dir}")
        print(f"  To encode manually:")
        print(f"    ffmpeg -framerate {args.fps} -i {frames_dir}/frame_%05d.png -c:v libx264 -pix_fmt yuv420p -crf 20 {out}/rss_scenario_capture.mp4")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
