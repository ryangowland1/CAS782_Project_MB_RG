#!/usr/bin/env python3
"""
Simple Multi-Vehicle Spawner
Spawns vehicles quickly and keeps them running.
"""

import carla
import time
import random

def main():
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10.0)
    world = client.get_world()
    
    print("Spawning 6 vehicles...")
    bp_lib = world.get_blueprint_library()
    spawns = world.get_map().get_spawn_points()
    
    vehicles = []
    for i in range(min(6, len(spawns))):
        bp = random.choice(bp_lib.filter('vehicle.*'))
        v = world.spawn_actor(bp, spawns[i])
        v.set_autopilot(True)
        vehicles.append(v)
        print(f"  {i+1}. Spawned {bp.id}")
    
    print(f"\n✓ Total spawned: {len(vehicles)} vehicles")
    print("Keeping alive for 90 seconds...")
    
    start = time.time()
    while time.time() - start < 90:
        active = sum(1 for v in vehicles if v.is_alive)
        if int(time.time() - start) % 10 == 0:
            print(f"  {active} vehicles active")
        time.sleep(1)
    
    print("\nCleaning up...")
    for v in vehicles:
        if v.is_alive:
            v.destroy()
    print("Done!")

if __name__ == "__main__":
    main()
