"""Time the winding choice of a case evaluation, the span the web evaluate job records in `scan_times` (from the
complete map to the chosen winding), on the 8/6 screening case of docs/winding-scan-profile.md.

Usage: python examples/scan_timing.py [--cache-dir DIR] [--json PATH]

Runs density and wire mode, each with winding "auto" and then fixed at the winding auto chose, with one scan worker
and with the default (half the logical CPUs). The map is built once per mode and served from the cache after that."""
import argparse
import json
import os
import platform
import time
from pathlib import Path

from srmapp.case import CaseInputs, FixedWinding, evaluate_design
from srmapp.references import make_8_6
from srmapp.requirements import Requirements
from srmcore.maps.pool import default_workers
from srmcore.model.design import Design, MeshSettings

BASE = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
WIRE = dict(wires=[dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)], phase_current_a=100.0)
MODES = {"density": Requirements(**BASE), "wire": Requirements(**BASE, **WIRE)}


def timed(inputs: CaseInputs, workers: int | None, cache_dir: Path) -> tuple[float, object]:
    start = []
    ev = evaluate_design(inputs, workers=workers, cache_dir=cache_dir, on_scan=lambda: start.append(time.monotonic()))
    assert ev.status == "ok", (ev.status, ev.error)
    return time.monotonic() - start[0], ev


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", type=Path, default=Path("cache"))
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    rows = []
    for mode, req in MODES.items():
        auto = CaseInputs(requirements=req, design=design)
        evaluate_design(auto.model_copy(update=dict(winding=FixedWinding(turns=1, wire=0 if req.wire_mode else None))),
                        workers=None, cache_dir=args.cache_dir)          # build or load the map, untimed
        for workers in (1, None):
            seconds, ev = timed(auto, workers, args.cache_dir)
            w = ev.winding
            n = default_workers(workers, 10**6)
            rows.append(dict(mode=mode, winding="auto", workers=n, seconds=seconds, scanned=len(ev.scan)))
            print(f"{mode:8s} auto  workers={n:2d}  {seconds:8.1f} s  {len(ev.scan)} windings", flush=True)
            fixed = auto.model_copy(update=dict(winding=FixedWinding(
                turns=w.turns, strands=w.strands, paths=w.paths, wire=w.wire)))
            seconds, _ = timed(fixed, workers, args.cache_dir)
            rows.append(dict(mode=mode, winding="fixed", workers=n, seconds=seconds, scanned=1))
            print(f"{mode:8s} fixed workers={n:2d}  {seconds:8.1f} s", flush=True)
    out = dict(machine=platform.node(), cpus=os.cpu_count(), date=time.strftime("%Y-%m-%d"), rows=rows)
    if args.json:
        args.json.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
