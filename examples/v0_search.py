"""Run a small requirements-driven search and print the scored candidates.

    python examples/v0_search.py [n_candidates] [shortlist]

Peak-only and unvalidated. Stage 2 builds a full-preset map (about 13 min) and scans the windings per design."""
import sys
import time

from srmapp.pipeline import SearchSettings, run_search
from srmapp.requirements import Requirements
from srmapp.wire import LitzWire, RectangularWire, RoundWire

# Example wires: Ø1.0 mm grade-2 round, 2.0 x 1.0 mm rectangular, 60 x Ø0.1 mm litz. Sizes in metres.
WIRES = (RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3),
         RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3),
         LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3))

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    shortlist = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    req = Requirements(peak_power_w=10_000.0, peak_torque_nm=32.0, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                       wires=WIRES, phase_current_a=150.0)
    t0 = time.perf_counter()
    res = run_search(req, SearchSettings(n_candidates=n, shortlist=shortlist),
                     progress=lambda d, t: print(f"  {d}/{t} designs", flush=True))
    print(f"sampled {res.sampled}, dropped {res.dropped}, stage 1 rejected {res.stage1_rejected}, "
          f"evaluated {len(res.evaluations)} in {time.perf_counter() - t0:.0f} s")
    front = {e.id for e in res.pareto()}
    print(f"{'id':14}{'poles':>7}{'OD mm':>7}{'wire':>12}{'N':>5}{'par':>5}{'R mΩ':>8}{'J A/mm²':>9}{'mass kg':>9}"
          f"{'T ratio':>9}{'P ratio':>9}{'kW/kg':>7}{'eff':>6}  status")
    for e in res.evaluations:
        m, w = e.design.machine, e.winding
        wire = "-" if w is None else req.wires[w.wire].kind
        wind = (f"{'-':>5}{'-':>5}{'-':>8}{'-':>9}" if w is None else
                f"{w.turns:5d}{w.strands:5d}{w.resistance * 1e3:8.1f}{w.current_density / 1e6:9.1f}")
        print(f"{e.id:14}{m.n_stator_poles:>4}/{m.n_rotor_poles:<2}{m.stator_outer_diameter * 1e3:7.0f}{wire:>12}{wind}"
              f"{e.mass_kg:9.2f}{e.torque_ratio:9.2f}{e.power_ratio:9.2f}{e.power_density_kw_per_kg:7.2f}"
              f"{e.efficiency_base:6.2f}  {e.status}{' *' if e.id in front else ''}")
    print("* = Pareto front (feasible designs; mass down, kW/kg up, copper-only efficiency up)")
