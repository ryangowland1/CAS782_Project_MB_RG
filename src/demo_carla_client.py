#!/usr/bin/env python3
"""Simple CARLA client demo - connects, spawns vehicles, and shows activity."""

import carla
import random
import time
import sys

def main():
    print("\n" + "="*60)
    print("CARLA Client Demo")
    print("="*60 + "\n")
    
    # Connect to CARLA
    print("Connecting to CARLA server at 127.0.0.1:2000...")
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10.0)
    
    try:
        world = client.get_world()
        print(f"✓ Connected to world: {world.get_map().name}")
    except RuntimeError as e:
        print(f"✗ Cannot connect to CARLA server: {e}")
        print("\nMake sure CARLA server is running!")
        print("The CARLA window should be open and fully loaded.")
        return 1
    
    # Get spawn points
    spawn_points = world.get_map().get_spawn_points()
    print(f"Found {len(spawn_points)} spawn points")
    
    # Get vehicle blueprints
    blueprint_library = world.get_blueprint_library()
    vehicle_bps = blueprint_library.filter('vehicle.*')
    print(f"Available vehicle types: {len(vehicle_bps)}")
    
    # Spawn some vehicles
    print("\nSpawning vehicles...")
    spawned_vehicles = []
    
    for i in range(min(5, len(spawn_points))):
        bp = random.choice(vehicle_bps)
        spawn_point = spawn_points[i]
        
        try:
            vehicle = world.spawn_actor(bp, spawn_point)
            spawned_vehicles.append(vehicle)
            print(f"  {i+1}. Spawned {bp.id} at ({spawn_point.location.x:.1f}, {spawn_point.location.y:.1f})")
        except RuntimeError as e:
            print(f"  {i+1}. Failed to spawn vehicle: {e}")
    
    if not spawned_vehicles:
        print("\n✗ No vehicles spawned. Exiting.")
        return 1
    
    print(f"\n✓ Successfully spawned {len(spawned_vehicles)} vehicles")
    
    # Show live actor positions for a few iterations
    print("\n" + "-"*60)
    print("Live Actor Positions (updating every 2 seconds)")
    print("Press Ctrl+C to stop")
    print("-"*60 + "\n")
    
    try:
        for iteration in range(10):
            print(f"\n[Iteration {iteration + 1}]")
            
            actors = world.get_actors()
            vehicles = actors.filter('vehicle.*')
            walkers = actors.filter('walker.pedestrian.*')
            
            print(f"Active actors: {len(vehicles)} vehicles, {len(walkers)} pedestrians")
            
            # Show our spawned vehicles
            for idx, vehicle in enumerate(spawned_vehicles):
                if vehicle.is_alive:
                    transform = vehicle.get_transform()
                    velocity = vehicle.get_velocity()
                    speed = (velocity.x**2 + velocity.y**2 + velocity.z**2)**0.5
                    
                    print(f"  Vehicle {idx+1}: "
                          f"pos=({transform.location.x:6.1f}, {transform.location.y:6.1f}, {transform.location.z:5.1f}) "
                          f"speed={speed:5.2f} m/s")
            
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n\nStopping demo...")
    
    # Cleanup
    print("\nCleaning up spawned vehicles...")
    for vehicle in spawned_vehicles:
        if vehicle.is_alive:
            vehicle.destroy()
    
    print("✓ Demo complete!")
    return 0

if __name__ == '__main__':
    sys.exit(main())
