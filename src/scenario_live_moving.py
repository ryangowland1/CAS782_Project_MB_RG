#!/usr/bin/env python3
"""Spawn multiple moving vehicles in CARLA for live scene graph streaming."""

from __future__ import annotations

import random
import time

import carla


def main() -> int:
    client = carla.Client("127.0.0.1", 2000)
    client.set_timeout(10.0)
    world = client.get_world()

    tm = client.get_trafficmanager(8000)
    tm.set_synchronous_mode(False)
    tm.set_global_distance_to_leading_vehicle(2.5)

    vehicle_bps = world.get_blueprint_library().filter("vehicle.*")
    spawn_points = world.get_map().get_spawn_points()
    random.shuffle(spawn_points)

    actors: list[carla.Actor] = []
    target = min(8, len(spawn_points))

    print(f"Attempting to spawn {target} moving vehicles...", flush=True)
    for idx, sp in enumerate(spawn_points[:target]):
        bp = random.choice(vehicle_bps)
        actor = world.try_spawn_actor(bp, sp)
        if actor is None:
            continue
        actor.set_autopilot(True, tm.get_port())
        # Small speed variance so stream updates change over time.
        tm.vehicle_percentage_speed_difference(actor, random.uniform(-20.0, 15.0))
        actors.append(actor)
        print(f"  spawned[{len(actors)}]: {actor.type_id} id={actor.id}", flush=True)

    print(f"Spawned {len(actors)} vehicles. Running for 120s...", flush=True)
    start = time.time()

    try:
        while time.time() - start < 120:
            alive = [a for a in actors if a.is_alive]
            print(f"t={time.time()-start:5.1f}s alive={len(alive)}", flush=True)
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("Interrupted.", flush=True)
    finally:
        for actor in actors:
            if actor.is_alive:
                actor.destroy()
        print("Cleanup complete.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
