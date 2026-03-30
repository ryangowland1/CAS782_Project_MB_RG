#!/usr/bin/env python3
"""
CARLA Scenario: Multi-Vehicle Traffic Scene
=============================================
Spawns multiple vehicles in traffic mode with autopilot.
Creates a realistic traffic scenario for scene graph export.

Duration: 1200 seconds to allow rich state capture
"""

import carla
import time
import math
import random

def main():
    # Connect to CARLA
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10.0)
    world = client.get_world()
    
    print("=" * 70)
    print("CARLA Scenario: Multi-Vehicle Traffic Scene")
    print("=" * 70)
    print()
    
    # Get blueprints and spawn points
    bp_lib = world.get_blueprint_library()
    vehicle_bps = bp_lib.filter('vehicle.*')
    spawn_points = world.get_map().get_spawn_points()
    
    if len(spawn_points) < 5:
        print("ERROR: Not enough spawn points!")
        return
    
    # Spawn multiple vehicles (up to 8)
    vehicles = []
    num_vehicles = min(8, len(spawn_points))
    
    print(f"Spawning {num_vehicles} vehicles in traffic mode...")
    print()
    
    for i in range(num_vehicles):
        bp = random.choice(vehicle_bps)
        spawn = spawn_points[i]
        vehicle = world.spawn_actor(bp, spawn)
        vehicle.set_autopilot(True)
        vehicles.append(vehicle)
        print(f"  {i+1}. {bp.id:30s} at ({spawn.location.x:7.1f}, {spawn.location.y:7.1f})")
    
    print(f"\n✓ Spawned {len(vehicles)} vehicles in autopilot mode")
    print("-" * 70)
    print()
    
    # Run scenario
    start_time = time.time()
    iteration = 0
    
    try:
        while time.time() - start_time < 1200:  # 20 minutes
            iteration += 1
            elapsed = time.time() - start_time
            
            # Get live vehicle data
            active = 0
            total_distance = 0.0
            avg_speed = 0.0
            
            for vehicle in vehicles:
                if vehicle.is_alive:
                    active += 1
                    loc = vehicle.get_location()
                    vel = vehicle.get_velocity()
                    speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)
                    avg_speed += speed
            
            if active > 0:
                avg_speed /= active
            
            # Print every 10 seconds
            if iteration % 5 == 0:
                print(f"[{elapsed:6.1f}s] Active vehicles: {active:2d}  |  Avg speed: {avg_speed:6.2f} m/s")
            
            time.sleep(2)
        
        print()
        print("-" * 70)
        print(f"✓ Scenario complete! {active} vehicles still alive for export")
        print()
        
        # Keep vehicles alive for scene export
        print("Keeping vehicles alive for 15 seconds (for scene export)...")
        time.sleep(15)
        
    except KeyboardInterrupt:
        print("\n\nScenario interrupted by user")
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        destroyed = 0
        for vehicle in vehicles:
            if vehicle.is_alive:
                vehicle.destroy()
                destroyed += 1
        print(f"✓ Destroyed {destroyed} vehicles")

if __name__ == "__main__":
    main()
