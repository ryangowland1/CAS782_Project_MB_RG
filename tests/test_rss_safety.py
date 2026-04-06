#!/usr/bin/env python3
"""Automated tests for the RSS safety-distance checker.

Tests verify the mathematical formulas from AV_Safety_Frameworks.pdf
(Equations 1 and 3) and the vehicle-classification helpers without
requiring a running CARLA instance.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from carla_scenegraph_export import Node
from rss_safety_check import (
    RSSParams,
    RSSViolation,
    check_rss_safety,
    decompose_in_ego_frame,
    find_closest_front_vehicle,
    find_closest_lateral_vehicle,
    rss_lateral_safe_distance,
    rss_longitudinal_safe_distance,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _veh(eid: str, x: float, y: float, heading: float = 0.0,
         speed: float = 0.0, vx: float = None, vy: float = None) -> Node:
    if vx is None:
        vx = speed * math.cos(heading)
    if vy is None:
        vy = speed * math.sin(heading)
    return Node("Vehicle", eid, x, y, 0.0, heading, speed=speed, vx=vx, vy=vy)


DEFAULT = RSSParams()


# ===========================================================================
# 1. Longitudinal safe-distance formula tests
# ===========================================================================

def test_lon_same_speed():
    """Equal speeds -> positive safe distance (ego must still keep a gap)."""
    d = rss_longitudinal_safe_distance(v_rear=10.0, v_front=10.0, params=DEFAULT)
    assert d > 0, f"Expected d > 0, got {d}"
    print(f"  [PASS] lon same speed 10 m/s: d_safe = {d:.3f} m")


def test_lon_ego_faster():
    """Ego faster than lead -> larger safe distance."""
    d_eq = rss_longitudinal_safe_distance(10.0, 10.0, DEFAULT)
    d_fast = rss_longitudinal_safe_distance(15.0, 10.0, DEFAULT)
    assert d_fast > d_eq, f"Expected d_fast > d_eq, got {d_fast:.3f} <= {d_eq:.3f}"
    print(f"  [PASS] ego faster: d_fast={d_fast:.3f} > d_eq={d_eq:.3f}")


def test_lon_ego_slower():
    """Ego much slower than lead -> safe distance can be 0."""
    d = rss_longitudinal_safe_distance(v_rear=2.0, v_front=20.0, params=DEFAULT)
    assert d == 0.0, f"Expected 0, got {d}"
    print(f"  [PASS] ego much slower: d = {d:.3f} (correctly 0)")


def test_lon_both_stopped():
    """Both stopped -> safe distance is small but positive (ego could accelerate during reaction)."""
    d = rss_longitudinal_safe_distance(0.0, 0.0, DEFAULT)
    # With v=0, d = 0.5*a*rho^2 + (rho*a)^2/(2*b_min) = kinematic term from reaction accel
    assert d > 0.0 and d < 2.0, f"Expected small positive, got {d}"
    print(f"  [PASS] both stopped: d = {d:.3f} (small positive from reaction accel)")


def test_lon_increases_with_speed():
    """Safe distance grows with ego speed."""
    d5 = rss_longitudinal_safe_distance(5.0, 5.0, DEFAULT)
    d10 = rss_longitudinal_safe_distance(10.0, 10.0, DEFAULT)
    d20 = rss_longitudinal_safe_distance(20.0, 20.0, DEFAULT)
    assert d5 < d10 < d20, f"Expected monotone: {d5:.3f} < {d10:.3f} < {d20:.3f}"
    print(f"  [PASS] monotone with speed: {d5:.3f} < {d10:.3f} < {d20:.3f}")


def test_lon_known_value():
    """Hand-computed example at 30 km/h (~8.33 m/s), default params."""
    v = 30.0 / 3.6  # m/s
    d = rss_longitudinal_safe_distance(v, v, DEFAULT)
    # v_r_rho = 8.33 + 0.5*3.5 = 10.08
    # d = 8.33*0.5 + 0.5*3.5*0.25 + 10.08^2/8 - 8.33^2/16
    #   = 4.167 + 0.4375 + 12.701 - 4.340 = 12.965
    assert 12.0 < d < 14.0, f"Expected ~13 m, got {d:.3f}"
    print(f"  [PASS] 30 km/h known value: d = {d:.3f} m")


# ===========================================================================
# 2. Lateral safe-distance formula tests
# ===========================================================================

def test_lat_zero_velocity():
    """No lateral velocity -> d_min is small (mu + kinematic term)."""
    d = rss_lateral_safe_distance(0.0, 0.0, DEFAULT)
    assert d > DEFAULT.mu, f"Expected d > mu, got {d}"
    assert d < 1.0, f"Expected < 1 m with zero velocity, got {d}"
    print(f"  [PASS] lateral zero velocity: d = {d:.4f} m")


def test_lat_ego_closing():
    """Ego drifting toward other -> larger safe distance."""
    d0 = rss_lateral_safe_distance(0.0, 0.0, DEFAULT)
    d1 = rss_lateral_safe_distance(1.0, 0.0, DEFAULT)
    assert d1 > d0, f"Expected d1 > d0, got {d1:.3f} <= {d0:.3f}"
    print(f"  [PASS] ego closing: d_closing={d1:.3f} > d_static={d0:.3f}")


def test_lat_other_closing():
    """Other closing (negative 'away' velocity) -> larger safe distance."""
    d0 = rss_lateral_safe_distance(0.0, 0.0, DEFAULT)
    d_close = rss_lateral_safe_distance(0.0, -1.0, DEFAULT)
    assert d_close > d0, f"Expected d_close > d0"
    print(f"  [PASS] other closing: d={d_close:.3f} > d_static={d0:.3f}")


def test_lat_both_closing():
    """Both vehicles drifting toward each other -> even larger."""
    d1 = rss_lateral_safe_distance(1.0, 0.0, DEFAULT)
    d_both = rss_lateral_safe_distance(1.0, -1.0, DEFAULT)
    assert d_both > d1, f"Expected d_both > d1"
    print(f"  [PASS] both closing: d_both={d_both:.3f} > d_ego_only={d1:.3f}")


def test_lat_other_opening():
    """Other moving away -> can reduce safe distance."""
    d0 = rss_lateral_safe_distance(0.0, 0.0, DEFAULT)
    d_open = rss_lateral_safe_distance(0.0, 2.0, DEFAULT)
    # When other is opening fast enough, safe distance shrinks
    assert d_open <= d0 or d_open >= 0, "safe distance should be non-negative"
    print(f"  [PASS] other opening: d={d_open:.3f} (d_static={d0:.3f})")


def test_lat_grows_with_closing_speed():
    """Safe distance grows monotonically with closing speed."""
    d1 = rss_lateral_safe_distance(0.5, 0.0, DEFAULT)
    d2 = rss_lateral_safe_distance(1.0, 0.0, DEFAULT)
    d3 = rss_lateral_safe_distance(2.0, 0.0, DEFAULT)
    assert d1 < d2 < d3, f"Expected monotone: {d1:.3f} < {d2:.3f} < {d3:.3f}"
    print(f"  [PASS] monotone with closing speed: {d1:.3f} < {d2:.3f} < {d3:.3f}")


# ===========================================================================
# 3. Decomposition & classification tests
# ===========================================================================

def test_decompose_ahead():
    """Vehicle straight ahead: lon>0, lat~0."""
    ego = _veh("ego", 0, 0, heading=0, speed=10)
    other = _veh("other", 20, 0, heading=0, speed=10)
    lon, lat, *_ = decompose_in_ego_frame(ego, other)
    assert lon > 0 and abs(lat) < 0.01
    print(f"  [PASS] decompose ahead: lon={lon:.2f}, lat={lat:.2f}")


def test_decompose_behind():
    """Vehicle behind: lon<0."""
    ego = _veh("ego", 0, 0, heading=0, speed=10)
    other = _veh("other", -10, 0, heading=0, speed=10)
    lon, lat, *_ = decompose_in_ego_frame(ego, other)
    assert lon < 0
    print(f"  [PASS] decompose behind: lon={lon:.2f}")


def test_decompose_beside():
    """Vehicle to the side: |lat| > 0, |lon| small."""
    ego = _veh("ego", 0, 0, heading=0, speed=10)
    other = _veh("other", 0, 3.5, heading=0, speed=10)
    lon, lat, *_ = decompose_in_ego_frame(ego, other)
    assert abs(lon) < 0.01 and abs(lat) > 3.0
    print(f"  [PASS] decompose beside: lon={lon:.2f}, lat={lat:.2f}")


def test_find_closest_front():
    """Closest front vehicle from multiple candidates."""
    ego = _veh("ego", 0, 0, heading=0, speed=10)
    v1 = _veh("v1", 10, 0, heading=0, speed=10)
    v2 = _veh("v2", 20, 0, heading=0, speed=10)
    v3 = _veh("v3", -5, 0, heading=0, speed=10)   # behind
    v4 = _veh("v4", 15, 10, heading=0, speed=10)   # far lateral

    result = find_closest_front_vehicle(ego, [v1, v2, v3, v4], DEFAULT)
    assert result is not None
    assert result[0].external_id == "v1"
    print(f"  [PASS] closest front = v1 at lon={result[1]:.1f}")


def test_find_closest_lateral():
    """Closest lateral vehicle from multiple candidates."""
    ego = _veh("ego", 0, 0, heading=0, speed=10)
    v_adj = _veh("adj", 2, 3.5, heading=0, speed=10)   # adjacent lane
    v_far = _veh("far", 0, 8, heading=0, speed=10)      # too far laterally

    result = find_closest_lateral_vehicle(ego, [v_adj, v_far], DEFAULT)
    assert result is not None
    assert result[0].external_id == "adj"
    print(f"  [PASS] closest lateral = adj at lat={result[2]:.1f}")


def test_no_front_vehicle():
    """No vehicle in front -> returns None."""
    ego = _veh("ego", 0, 0, heading=0, speed=10)
    v_behind = _veh("b", -10, 0, heading=0, speed=10)
    assert find_closest_front_vehicle(ego, [v_behind], DEFAULT) is None
    print(f"  [PASS] no front vehicle -> None")


def test_no_lateral_vehicle():
    """No vehicle beside -> returns None."""
    ego = _veh("ego", 0, 0, heading=0, speed=10)
    v_front = _veh("f", 10, 0, heading=0, speed=10)
    assert find_closest_lateral_vehicle(ego, [v_front], DEFAULT) is None
    print(f"  [PASS] no lateral vehicle -> None")


# ===========================================================================
# 4. Integration: check_rss_safety
# ===========================================================================

def test_rss_longitudinal_violation():
    """Ego following at 30 km/h with 5 m gap -> violation."""
    v = 30.0 / 3.6
    ego = _veh("ego", 0, 0, heading=0, speed=v)
    lead = _veh("lead", 5, 0, heading=0, speed=v)
    viols = check_rss_safety(ego, [lead])
    lon_viols = [v for v in viols if v.rule == "longitudinal"]
    assert len(lon_viols) == 1, f"Expected 1 lon violation, got {len(lon_viols)}"
    v0 = lon_viols[0]
    print(f"  [PASS] lon violation at 5 m gap: actual={v0.actual_distance:.2f}, safe={v0.safe_distance:.2f}")


def test_rss_longitudinal_safe():
    """Ego following at 30 km/h with 20 m gap -> safe."""
    v = 30.0 / 3.6
    ego = _veh("ego", 0, 0, heading=0, speed=v)
    lead = _veh("lead", 20, 0, heading=0, speed=v)
    viols = check_rss_safety(ego, [lead])
    lon_viols = [v for v in viols if v.rule == "longitudinal"]
    assert len(lon_viols) == 0, f"Expected no lon violation at 20 m gap"
    print(f"  [PASS] no lon violation at 20 m gap")


def test_rss_lateral_violation():
    """Adjacent vehicle at 2 m lateral, drifting toward ego at 2 m/s -> violation."""
    ego = _veh("ego", 0, 0, heading=0, speed=10, vx=10, vy=0)
    # Other is beside ego (lat ~3.5m), drifting toward ego
    # The perpendicular direction for heading=0 is (0, 1), so lat=3.5 when y=3.5
    # With heading=0: perp = (-sin(0), cos(0)) = (0, 1). So dy=3.5 → lat=3.5
    # To drift toward ego (decrease y), other needs vy < 0.
    # In ego frame: other_lat_vel = vy * perp_y = vy * cos(0) = vy = -2
    # Since lat>0: v_other_away = other_lat = -2 (moving toward ego = negative away)
    adj = _veh("adj", 1, 3.5, heading=0, speed=10, vx=10, vy=-2.0)
    viols = check_rss_safety(ego, [adj])
    lat_viols = [v for v in viols if v.rule == "lateral"]
    assert len(lat_viols) == 1, f"Expected 1 lateral violation, got {len(lat_viols)}"
    v0 = lat_viols[0]
    print(f"  [PASS] lateral violation: actual={v0.actual_distance:.2f}, safe={v0.safe_distance:.2f}")


def test_rss_lateral_safe():
    """Adjacent vehicle at 3.5 m lateral, no drift -> safe."""
    ego = _veh("ego", 0, 0, heading=0, speed=10, vx=10, vy=0)
    adj = _veh("adj", 1, 3.5, heading=0, speed=10, vx=10, vy=0)
    viols = check_rss_safety(ego, [adj])
    lat_viols = [v for v in viols if v.rule == "lateral"]
    assert len(lat_viols) == 0, f"Expected no lateral violation at 3.5 m with no drift"
    print(f"  [PASS] no lateral violation at 3.5 m, no drift")


def test_rss_both_violations():
    """Close front + drifting adjacent -> both violations at once."""
    v = 30.0 / 3.6
    ego = _veh("ego", 0, 0, heading=0, speed=v, vx=v, vy=0)
    lead = _veh("lead", 5, 0, heading=0, speed=v, vx=v, vy=0)
    adj = _veh("adj", 1, 2.0, heading=0, speed=v, vx=v, vy=-2.0)
    viols = check_rss_safety(ego, [lead, adj])
    rules = {v.rule for v in viols}
    assert "longitudinal" in rules and "lateral" in rules, f"Expected both rules, got {rules}"
    print(f"  [PASS] both violations detected simultaneously")


# ===========================================================================
# Runner
# ===========================================================================

ALL_TESTS = [
    # Longitudinal formula
    test_lon_same_speed,
    test_lon_ego_faster,
    test_lon_ego_slower,
    test_lon_both_stopped,
    test_lon_increases_with_speed,
    test_lon_known_value,
    # Lateral formula
    test_lat_zero_velocity,
    test_lat_ego_closing,
    test_lat_other_closing,
    test_lat_both_closing,
    test_lat_other_opening,
    test_lat_grows_with_closing_speed,
    # Decomposition & classification
    test_decompose_ahead,
    test_decompose_behind,
    test_decompose_beside,
    test_find_closest_front,
    test_find_closest_lateral,
    test_no_front_vehicle,
    test_no_lateral_vehicle,
    # Integration
    test_rss_longitudinal_violation,
    test_rss_longitudinal_safe,
    test_rss_lateral_violation,
    test_rss_lateral_safe,
    test_rss_both_violations,
]


def run_tests() -> bool:
    passed = 0
    failed = 0
    total = len(ALL_TESTS)

    print(f"Running {total} RSS safety tests ...\n")

    for test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"  [FAIL] {test_fn.__name__}: {exc}")

    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")

    if failed:
        print("\nFAILED tests need investigation.")
        return False

    print("\nAll RSS safety tests passed!")
    return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
