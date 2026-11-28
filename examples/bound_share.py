"""Measure how much of the stage-1 torque bound a drive reaches, for the bike requirement.

Usage: python examples/bound_share.py [--ratio 12] [--per-set 3] [--workers N] [--cache-dir DIR] [--json PATH]

200 screening candidates (seed 0) go through stage 1 and the hard limits. For the first `per-set` designs of each
pole set by mass the screening map is built at the stage-1 range, and the script records the drive torque at 50 r/min
at the map top over the stage-1 `torque_upper` (the share), plus the regulated current of the best density winding
over the 170 A device peak."""
import argparse
import json
import math
import time
from pathlib import Path

from srmapp.drive.envelope import envelope
from srmapp.limits import SEARCH_REQUIRES_PASS, hard_limits
from srmapp.pipeline import SearchSettings
from srmapp.requirements import Requirements
from srmapp.sizing.estimates import J_SCREEN
from srmapp.sizing.generator import sample_candidates
from srmapp.sizing.stage1 import stage1
from srmapp.turns import choose_turns
from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding

WHEEL_RPM = 1326.0
DEVICE_PEAK_A = 170.0


def bike(ratio: float) -> Requirements:
    top = WHEEL_RPM * ratio
    base = top / 3
    return Requirements(peak_power_w=30_000.0, peak_torque_nm=30_000.0 / (base * 2 * math.pi / 60),
                        base_speed_rpm=base, max_speed_rpm=top, bus_voltage_v=300.0, max_bus_voltage_v=420.0,
                        max_outer_diameter_m=0.200, max_length_m=0.18, phase_current_a=DEVICE_PEAK_A,
                        switching_frequency_hz=20_000.0, continuous_power_w=12_000.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", type=float, default=12.0)
    ap.add_argument("--per-set", type=int, default=3)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--cache-dir", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    req = bike(args.ratio)
    settings = SearchSettings(preset="screening")
    margin = settings.resolved_margin
    cands, _ = sample_candidates(req, 200, seed=0, materials=settings.materials, preset="screening")
    by_set: dict[tuple[int, int], list] = {}
    for c in cands:
        m = c.design.machine
        st = stage1(req, m, margin, settings.j_peak, settings.peak_cap)
        if not st.passes:
            continue
        if any(lim.status == "fail" or (lim.status == "not_run" and lim.name in SEARCH_REQUIRES_PASS)
               for lim in hard_limits(req, m)):
            continue
        by_set.setdefault((m.n_stator_poles, m.n_rotor_poles), []).append((c, st))
    rows = []
    for key, items in sorted(by_set.items()):
        for c, st in sorted(items, key=lambda cs: cs[1].mass.total)[:args.per_set]:
            m = c.design.machine
            t0 = time.monotonic()
            result = build_map(c.design, st.i_map, solver="ngsolve", workers=args.workers, cache_dir=args.cache_dir)
            result = with_end_winding(result, end_winding_inductance(m, image_factor=1.5))
            env = envelope(result, m, req.bus_voltage_v, 0.0, [50.0], waveforms=False)
            share = float(env.torque[0]) / st.torque_upper
            choice = choose_turns(result, m, req, j_peak=settings.j_peak, j_limit=J_SCREEN, margin=margin,
                                  workers=args.workers)
            p = choice.point
            row = dict(pole_set=f"{key[0]}/{key[1]}", od_m=m.stator_outer_diameter, stack_m=m.stack_length,
                       mass_kg=st.mass.total, torque_upper_nm=st.torque_upper, torque_50rpm_nm=float(env.torque[0]),
                       share=share,
                       regulated_share=None if p is None else p.winding.current / DEVICE_PEAK_A,
                       turns=None if p is None else p.winding.turns,
                       paths=None if p is None else p.winding.paths,
                       single_pulse=None if p is None else p.single_pulse, feasible=choice.feasible,
                       seconds=time.monotonic() - t0)
            rows.append(row)
            print(json.dumps(row), flush=True)
    out = dict(ratio=args.ratio, margin=margin, n_designs=len(rows), rows=rows,
               max_share=max((r["share"] for r in rows), default=None))
    if args.json:
        args.json.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
