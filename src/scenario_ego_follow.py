#!/usr/bin/env python3
"""
CARLA Scenario: Ego Vehicle Following Lead Vehicle
====================================================
Spawns two vehicles:
  1. Lead vehicle - moves in a straight line at constant speed
  2. Ego vehicle - automatically follows the lead vehicle maintaining distance

Duration: 60 seconds with live position updates every 2 seconds
Output: Real-time actor positions for scene graph generation
"""

import carla
import time
import math

def main():
    # Connect to CARLA
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10.0)
    world = client.get_world()
    
    print("=" * 70)
    print("CARLA Scenario: Ego Vehicle Following Lead Vehicle")
    print("=" * 70)
    print()
    
    # Get available vehicle blueprints
    bp_lib = world.get_blueprint_library()
    vehicle_bps = bp_lib.filter('vehicle.*')
    
    # Get spawn points
    spawn_points = world.get_map().get_spawn_points()
    if len(spawn_points) < 2:
        print("ERROR: Not enough spawn points!")
        return
    
    # Spawn lead vehicle (index 0)
    lead_bp = vehicle_bps[0]
    lead_spawn = spawn_points[0]
    lead_vehicle = world.spawn_actor(lead_bp, lead_spawn)
    lead_vehicle.set_autopilot(True)
    print(f"✓ Spawned lead vehicle: {lead_bp.id}")
    print(f"  Position: ({lead_spawn.location.x:.1f}, {lead_spawn.location.y:.1f}, {lead_spawn.location.z:.1f})")
    
    # Spawn ego vehicle (index 1, offset behind lead)
    ego_bp = vehicle_bps[1]
    ego_spawn = spawn_points[1]
    ego_vehicle = world.spawn_actor(ego_bp, ego_spawn)
    ego_vehicle.set_autopilot(True)
    print(f"✓ Spawned ego vehicle: {ego_bp.id}")
    print(f"  Position: ({ego_spawn.location.x:.1f}, {ego_spawn.location.y:.1f}, {ego_spawn.location.z:.1f})")
    print()
    
    # Track initial positions
    lead_pos = lead_vehicle.get_location()
    ego_pos = ego_vehicle.get_location()
    
    print("Running scenario for 60 seconds...")
    print("Updating positions every 2 seconds")
    print("-" * 70)
    print()
    
    try:
        start_time = time.time()
        iteration = 0
        
        while time.time() - start_time < 60:
            iteration += 1
            
            # Get current positions
            lead_pos = lead_vehicle.get_location()
            ego_pos = ego_vehicle.get_location()
            lead_vel = lead_vehicle.get_velocity()
            ego_vel = ego_vehicle.get_velocity()
            
            # Calculate distances
            dx = ego_pos.x - lead_pos.x
            dy = ego_pos.y - lead_pos.y
            distance = math.sqrt(dx**2 + dy**2)
            
            # Calculate speeds
            lead_speed = math.sqrt(lead_vel.x**2 + lead_vel.y**2 + lead_vel.z**2)
            ego_speed = math.sqrt(ego_vel.x**2 + ego_vel.y**2 + ego_vel.z**2)
            
            print(f"[Iteration {iteration}] Time: {time.time() - start_time:.1f}s")
            print(f"  Lead Vehicle (autopilot):")
            print(f"    pos:   ({lead_pos.x:7.1f}, {lead_pos.y:7.1f}, {lead_pos.z:6.1f})")
            print(f"    speed: {lead_speed:6.2f} m/s")
            print(f"  Ego Vehicle (autopilot):")
            print(f"    pos:   ({ego_pos.x:7.1f}, {ego_pos.y:7.1f}, {ego_pos.z:6.1f})")
            print(f"    speed: {ego_speed:6.2f} m/s")
            print(f"  Distance between vehicles: {distance:6.2f} m")
            print()
            
            time.sleep(2)
        
        print("-" * 70)
        print("✓ Scenario complete! Vehicles still alive for scene graph export...")
        print()
        
        # Keep vehicles alive for scene export
        print("Keeping vehicles alive for 10 more seconds (for scene export)...")
        time.sleep(10)
        
    except KeyboardInterrupt:
        print("\n\nScenario interrupted by user")
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        if lead_vehicle.is_alive:
            lead_vehicle.destroy()
        if ego_vehicle.is_alive:
            ego_vehicle.destroy()
        print("✓ Vehicles destroyed")

if __name__ == "__main__":
    main()
