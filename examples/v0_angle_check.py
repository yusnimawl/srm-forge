"""Stage-2 accuracy check (v0a-2 spec §5, small-cycle spec §8) on one candidate per pole set, all with the winding
chosen on the 30-angle map at the search defaults (margin, RMS current-density limit, peak cap, paths): envelope
from 30 angles against 60 angles on the `full` mesh, 20 map currents against twice as many, and the drive
discretisation (N_THETA 181 against 361; the 80 x 80 on/off grid against 160 x 160 at N_THETA 361).

    python examples/v0_angle_check.py [n_candidates] [n_currents]

Prints, per design, the torque ratio at base speed and the worst power ratio over base..max speed for each
variant, and their change against the default (30 angles, 1x currents, 181, 80 x 80). The on/off grid effect is
the "361, on/off 160" row against the "n_theta 361" row. Maps are cached in out/v0_angle_check. Hours on a laptop."""
import sys
import time

from srmapp.drive.envelope import envelope
from srmapp.pipeline import SearchSettings
from srmapp.requirements import Requirements
from srmapp.sizing.generator import sample_candidates
from srmapp.sizing.stage1 import stage1
from srmapp.turns import choose_turns, requirement_ratios, rescale_turns, speed_grid, turns_scale
from srmapp.wire import LitzWire, RectangularWire, RoundWire
from srmcore.maps import build_map

REQ = Requirements(peak_power_w=10_000.0, peak_torque_nm=32.0, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                   wires=(RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3),
                          RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3),
                          LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3)),
                   phase_current_a=150.0)
# name: (map angles, current multiplier, n_theta, on/off grid size)
VARIANTS = {"default": (30, 1, 181, 80), "60 angles": (60, 1, 181, 80), "2x currents": (30, 2, 181, 80),
            "n_theta 361": (30, 1, 361, 80), "361, on/off 160": (30, 1, 361, 160)}
CACHE = "out/v0_angle_check"
S = SearchSettings()

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n_currents = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    candidates, _ = sample_candidates(REQ, n, seed=0)
    for c in candidates:
        m = c.design.machine
        t0 = time.perf_counter()
        stage = stage1(REQ, m, S.margin, S.j_peak, S.peak_cap)
        label = f"{c.id} {m.n_stator_poles}/{m.n_rotor_poles} OD {m.stator_outer_diameter * 1e3:.0f} mm"
        if stage.mmf == 0.0:
            print(f"\n{label}\n  no winding meets the limits; skipped")
            continue
        maps = {(a, k * n_currents): build_map(c.design, stage.i_map, n_angles=a, n_currents=k * n_currents,
                                               cache_dir=CACHE)
                for a, k in sorted({v[:2] for v in VARIANTS.values()})}
        choice = choose_turns(maps[(30, n_currents)], m, REQ, j_peak=S.j_peak, j_limit=S.j_limit,
                              j_peak_max=S.peak_cap, margin=S.margin)
        print(f"\n{label} ({time.perf_counter() - t0:.0f} s)")
        if choice.point is None:
            print("  no winding meets the limits; skipped")
            continue
        w = choice.point.winding
        print(f"  wire {REQ.wires[w.wire].kind}, N {w.turns}, paths {w.paths}, strands {w.strands}, "
              f"R {w.resistance * 1e3:.1f} mOhm, J_rms {choice.point.j_rms / 1e6:.1f} A/mm2, "
              f"feasible {choice.feasible}")
        rows = {}
        for name, (n_a, k, n_theta, n_sw) in VARIANTS.items():
            env = envelope(rescale_turns(maps[(n_a, k * n_currents)], turns_scale(m, w)), m, REQ.bus_voltage_v,
                           w.resistance, speed_grid(REQ), current_limit=w.current,
                           rms_limit=S.j_limit * w.paths * w.copper_area, n_theta=n_theta, n_on=n_sw, n_off=n_sw)
            rows[name] = requirement_ratios(env, REQ)
        ref = rows["default"]
        print(f"  {'variant':16}{'T ratio':>9}{'P ratio':>9}{'dT':>9}{'dP':>9}")
        for name, (t, p) in rows.items():
            dt = (t - ref[0]) / ref[0] if ref[0] else float("nan")
            dp = (p - ref[1]) / ref[1] if ref[1] else float("nan")
            print(f"  {name:16}{t:9.3f}{p:9.3f}{dt:9.2%}{dp:9.2%}")
