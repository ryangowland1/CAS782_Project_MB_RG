#!/usr/bin/env python3
"""Dummy VIATRA-style live consumer over scenegraph stream events.jsonl.

It mimics three query-style checks over each tick event:
- fastVehicle: vehicles with speed > 13.9 m/s
- connected: number of proximity edges present
- vehiclePedestrianSharedRoad (dummy): any proximity edge Vehicle<->Pedestrian
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Consume scenegraph stream events (dummy VIATRA)")
    p.add_argument("--events", default="data/stream/events.jsonl", help="Path to events.jsonl")
    p.add_argument("--ticks", type=int, default=15, help="How many events to consume before exiting")
    p.add_argument("--poll", type=float, default=0.5, help="Polling interval when waiting for new lines")
    p.add_argument("--from-end", action="store_true", help="Start from end of file and only consume new events")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.events)

    print("Dummy VIATRA consumer started", flush=True)
    print(f"events={path} ticks={args.ticks}", flush=True)

    consumed = 0
    offset = 0

    if args.from_end and path.exists():
        offset = len(path.read_text(encoding="utf-8").splitlines())

    while consumed < args.ticks:
        if not path.exists():
            time.sleep(args.poll)
            continue

        data = path.read_text(encoding="utf-8")
        lines = data.splitlines()

        if offset >= len(lines):
            time.sleep(args.poll)
            continue

        for line in lines[offset:]:
            evt = json.loads(line)
            tick = evt.get("tick", -1)

            added = evt.get("node_changes", {}).get("added", [])
            updated = evt.get("node_changes", {}).get("updated", [])
            edges_added = evt.get("edge_changes", {}).get("added", [])

            # Build current-node view from event deltas (dummy approximation).
            node_snap = []
            node_snap.extend(added)
            for upd in updated:
                after = upd.get("after")
                if after:
                    node_snap.append(after)

            fast_vehicle = [
                n for n in node_snap
                if n.get("node_type") == "Vehicle" and (n.get("speed") is not None) and float(n.get("speed")) > 13.9
            ]

            vehicle_ped = [
                e for e in edges_added
                if {str(e.get("source", "")), str(e.get("target", ""))}
            ]

            print(
                f"tick={tick:>3} nodes={evt.get('node_count', 0):>2} edges={evt.get('edge_count', 0):>2} "
                f"fastVehicle={len(fast_vehicle)} connected={len(edges_added)} "
                f"vehiclePedSharedRoad(dummy)={len(vehicle_ped)}",
                flush=True,
            )

            consumed += 1
            if consumed >= args.ticks:
                break

        offset = len(lines)

    print("Dummy VIATRA consumer finished.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
