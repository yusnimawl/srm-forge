"""Stage-2 accuracy check (v0a-2 spec §5) on one candidate per pole set, all with the winding chosen on the
30-angle map: envelope from 30 angles against 60 angles on the `full` mesh, and the drive discretisation
(N_THETA 181 against 361, a 40 x 40 against an 80 x 80 on/off grid) on the 30-angle map.

    python examples/v0_angle_check.py [n_candidates] [n_currents]

Prints, per design, the torque ratio at base speed and the worst power ratio over base..max speed for each
variant, and their change against the default (30 angles, 181, 40 x 40). Maps are cached in out/v0_angle_check.
Hours on a laptop."""
import sys
import time

from srmapp.drive.envelope import envelope
from srmapp.requirements import Requirements
from srmapp.sizing.generator import sample_candidates
from srmapp.sizing.stage1 import stage1
from srmapp.turns import choose_turns, requirement_ratios, rescale_turns, speed_grid
from srmapp.wire import LitzWire, RectangularWire, RoundWire
from srmcore.maps import build_map

REQ = Requirements(peak_power_w=10_000.0, peak_torque_nm=32.0, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                   wires=(RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3),
                          RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3),
                          LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3)),
                   phase_current_a=150.0)
# name: (map angles, n_theta, on/off grid size)
VARIANTS = {"default": (30, 181, 40), "60 angles": (60, 181, 40), "n_theta 361": (30, 361, 40),
            "on/off 80": (30, 181, 80)}
CACHE = "out/v0_angle_check"

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n_currents = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    candidates, _ = sample_candidates(REQ, n, seed=0)
    for c in candidates:
        m = c.design.machine
        t0 = time.perf_counter()
        i_map = stage1(REQ, m).i_map
        maps = {a: build_map(c.design, i_map, n_angles=a, n_currents=n_currents, cache_dir=CACHE)
                for a in sorted({v[0] for v in VARIANTS.values()})}
        choice = choose_turns(maps[30], m, REQ)
        print(f"\n{c.id} {m.n_stator_poles}/{m.n_rotor_poles} OD {m.stator_outer_diameter * 1e3:.0f} mm "
              f"({time.perf_counter() - t0:.0f} s)")
        if choice.point is None:
            print("  no winding meets the limits; skipped")
            continue
        w = choice.point.winding
        print(f"  wire {REQ.wires[w.wire].kind}, N {w.turns}, strands {w.strands}, R {w.resistance * 1e3:.1f} mOhm")
        rows = {}
        for name, (n_a, n_theta, n_sw) in VARIANTS.items():
            env = envelope(rescale_turns(maps[n_a], w.turns / m.turns_per_pole), m, REQ.bus_voltage_v,
                           w.resistance, speed_grid(REQ), current_limit=w.current, n_theta=n_theta, n_on=n_sw,
                           n_off=n_sw)
            rows[name] = requirement_ratios(env, REQ)
        ref = rows["default"]
        print(f"  {'variant':14}{'T ratio':>9}{'P ratio':>9}{'dT':>9}{'dP':>9}")
        for name, (t, p) in rows.items():
            print(f"  {name:14}{t:9.3f}{p:9.3f}{(t - ref[0]) / ref[0]:9.2%}{(p - ref[1]) / ref[1]:9.2%}")
