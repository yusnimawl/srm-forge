"""Time the thermal rating of a case evaluation, the span the web evaluate job spends after the winding choice, on
the rated 8/6 setup of tests/app/test_thermal_check.py (`RATING_BUDGET_S` in srmweb/cases.py is set from this).

Usage: python examples/rating_timing.py [--preset screening|full] [--cache-dir DIR] [--json PATH]

Runs `evaluate_design` with thermal on and times from the first `thermal_progress` call to the return. The default
cache directory is a fresh temporary one, so the map is built (the output says whether it was a cache hit)."""
import argparse
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import srmapp
import srmapp.thermal as th
from srmapp.cooling import ROWS, coefficients
from srmapp.mechanical import mechanical_loss
from srmapp.case import CaseInputs, evaluate_design
from srmapp.references import make_8_6
from srmapp.requirements import Requirements
from srmcore.model.design import Design, MeshSettings, RegionMaterials


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=["screening", "full"], default="screening")
    ap.add_argument("--cache-dir", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    cache_dir = args.cache_dir or Path(tempfile.mkdtemp(prefix="rating_timing_"))
    req = Requirements(peak_power_w=628.0, peak_torque_nm=3.0, base_speed_rpm=2000.0, max_speed_rpm=6000.0,
                       wires=[dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)], phase_current_a=20.0,
                       continuous_power_w=100.0)
    machine = make_8_6(materials=RegionMaterials(stator="10JNEX900", rotor="10JNEX900"), lamination_thickness=1.0e-4)
    inputs = CaseInputs(requirements=req, design=Design(machine=machine, mesh=MeshSettings(preset=args.preset)))
    marks: dict[str, float] = {}
    log: list[dict] = []     # every stroke the rating solved: speed, torque asked, torque reached, iron loss
    stroke = th.ThermalContext.stroke

    def logged(self, rpm, torque):
        fresh = (rpm, torque) not in self.strokes
        s = stroke(self, rpm, torque)
        if fresh:
            log.append(dict(rpm=rpm, ask_nm=torque, torque_avg_nm=None if s is None else s[0].torque_avg,
                            iron_w=None if s is None else s[1].iron_w))
        return s

    th.ThermalContext.stroke = logged
    t0 = time.monotonic()
    ev = evaluate_design(inputs, cache_dir=cache_dir, thermal=True,
                         on_scan=lambda: marks.setdefault("scan", time.monotonic()),
                         thermal_progress=lambda *_: marks.setdefault("rating", time.monotonic()))
    end = time.monotonic()
    rated = ev.rating is not None
    speeds = []
    if rated:
        machine, req_ = ev.design.machine, req
        for sets, rows in (("nominal", frozenset()), ("rated", frozenset(ROWS))):
            for r in getattr(ev.rating, sets):
                c = coefficients(req_.cooling, machine, r.rpm, rows, None, fill=machine.fill_factor)
                mech = mechanical_loss(machine, req_.bearing, r.rpm, unfavourable="mechanical_loss" in rows)
                speeds.append(dict(set=sets, rpm=r.rpm, envelope_nm=r.envelope_nm, continuous_nm=r.continuous_nm,
                                   peak_nm=r.peak_nm, iron_factor=c.iron_factor, torque_factor=ev.rating.torque_factor if sets == "rated" else 1.0,
                                   mechanical_w=mech.total_w, omega=r.rpm * 2 * math.pi / 60))
    # a cached map reaches the scan almost at once; a built one takes minutes
    out = dict(preset=args.preset, rating_s=end - marks["rating"] if "rating" in marks else None,
               total_s=end - t0, map_cache_hit=("scan" in marks and marks["scan"] - t0 < 10.0), rated=rated,
               n_strokes=len(log), strokes=log, speeds=speeds, status=ev.status, notes=ev.error, srmapp=srmapp.__version__)
    print(json.dumps(out, indent=2))
    if args.json:
        args.json.write_text(json.dumps(out, indent=2))
    if not rated:
        sys.exit("not rated: not a rating measurement")


if __name__ == "__main__":
    main()
