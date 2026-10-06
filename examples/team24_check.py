"""TEAM Problem 24: the 2D magnetostatic model against the published measurements. Prints solver
agreement, static torque, current rise, torque and rotor-pole flux against time and against the measured
current, and the sensitivity of each to R, the voltage waveform, Js and the mesh. The output is the
source of docs/m5b-team24-results.md.

Run from the repo root:  .venv\\Scripts\\python examples\\team24_check.py [--json PATH]
"""
import json
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import team24_fixture as t24  # noqa: E402

from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque  # noqa: E402
from srmcore.solvers.skfem_reference import SkfemReference  # noqa: E402

JSON_PATH = None
if "--json" in sys.argv:
    _i = sys.argv.index("--json")
    JSON_PATH = Path(sys.argv[_i + 1])
    del sys.argv[_i:_i + 2]

I_FINAL, T_MEASURED = 7.41, 3.22
skfem = SkfemReference()


def pct(model, measured):
    return 100 * (model - measured) / measured


def static(scale=1.0, js=t24.ASSUMED_JS):
    p = t24.team24_problem(I_FINAL, scale, js)
    s = skfem.solve(p)
    bmax = np.hypot(s.b[:, 0], s.b[:, 1])[p.element_law == 1].max()
    return p, s, bmax


print(f"--- static point at {I_FINAL} A")
p, s, bmax = static()
print(f"nodes {len(p.nodes)}, triangles {len(p.triangles)}, peak iron |B| {bmax:.2f} T")
t_ark, t_vw, psi = arkkio_torque(p, s), virtual_work_torque(p, s), flux_linkage(p, s)[0]
flux = t24.rotor_pole_flux(p, s)
print(f"psi {psi:.5f} Wb-turns; T Arkkio {t_ark:.4f} / virtual work {t_vw:.4f} N.m vs {T_MEASURED}: "
      f"{pct(t_ark, T_MEASURED):+.1f} %")
print(f"rotor-pole flux {flux:.4e} Wb (other pole {t24.rotor_pole_flux(p, s, -1):.4e}) vs "
      f"{t24.TABLE_ROTOR_FLUX[-1]:.2e}: {pct(flux, t24.TABLE_ROTOR_FLUX[-1]):+.1f} %")
try:
    from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
    n = NgsolveAdapter().solve(p)
    print(f"NGSolve vs skfem: max|dA|/max|A| {np.abs(n.a - s.a).max() / np.abs(s.a).max():.1e}, "
          f"torque rel {abs(arkkio_torque(p, n) - t_ark) / t_ark:.1e}")
except ImportError:
    print("NGSolve not installed: solver agreement skipped")

print("--- locked-rotor map")
m = t24.locked_rotor_map(skfem)
psi_i = PchipInterpolator(m["current"], m["psi"])
torque_i = PchipInterpolator(m["current"], m["torque"])
flux_i = PchipInterpolator(m["current"], m["rotor_flux"])
i_model = t24.current_rise(psi_i, t24.TABLE_TIME)
print(f"{'t/s':>6} {'i meas':>7} {'i model':>8} {'dev %':>6} | {'T meas':>6} {'T(t)':>6} {'dev %':>6} "
      f"{'T(i_m)':>6} {'dev %':>6} | {'F meas':>6} {'F(t)':>6} {'dev %':>6} {'F(i_m)':>6} {'dev %':>6}")
for k, t in enumerate(t24.TABLE_TIME):
    im, ic = t24.TABLE_CURRENT[k], i_model[k]
    tm, fm = t24.TABLE_TORQUE[k], 1e4 * t24.TABLE_ROTOR_FLUX[k]
    tt, ti = float(torque_i(ic)), float(torque_i(im))
    ft, fi = 1e4 * float(flux_i(ic)), 1e4 * float(flux_i(im))
    print(f"{t:6.3f} {im:7.2f} {ic:8.3f} {pct(ic, im):+6.1f} | {tm:6.2f} {tt:6.3f} {pct(tt, tm):+6.1f} "
          f"{ti:6.3f} {pct(ti, tm):+6.1f} | {fm:6.2f} {ft:6.3f} {pct(ft, fm):+6.1f} {fi:6.3f} {pct(fi, fm):+6.1f}")
print("(F in 1e-4 Wb; T(i_m), F(i_m): model at the measured current, which removes the time-axis error)")

print("--- sensitivity of the current rise (max |dev| %, t >= 5 ms; dev % at 20 ms; i at 300 ms)")
for label, r, v in [("R 3.09, V 23.1", t24.RESISTANCE, t24.VOLTAGE),
                    ("R 3.12, V 23.1", 3.12, t24.VOLTAGE),
                    ("R 3.12, V Table II", 3.12, t24.table_ii_voltage)]:
    i = t24.current_rise(psi_i, t24.TABLE_TIME, resistance=r, voltage=v)
    d = pct(i, t24.TABLE_CURRENT)
    print(f"{label:<20} {np.abs(d[1:]).max():5.1f} {d[4]:+6.1f} {i[-1]:.3f} A")

print("--- end-winding correction (srmcore.post.end_winding, image factor 1 / 2, midpoint used)")
l1, l2 = t24.end_winding_inductance(1.0), t24.end_winding_inductance(2.0)
l_end = 0.5 * (l1 + l2)
psi_final = float(psi_i(I_FINAL))
print(f"L_end {l1 * 1e3:.3f} / {l2 * 1e3:.3f} mH (midpoint {l_end * 1e3:.3f} mH); psi at {I_FINAL} A "
      f"{psi_final:.5f} -> {psi_final + l_end * I_FINAL:.5f} Wb-turns ({100 * l_end * I_FINAL / psi_final:+.1f} %)")
i_after = t24.current_rise(PchipInterpolator(m["current"], m["psi"] + l_end * m["current"]), t24.TABLE_TIME)
print(f"{'t/s':>6} {'i meas':>7} {'before':>8} {'dev %':>6} {'after':>8} {'dev %':>6}")
for k, t in enumerate(t24.TABLE_TIME):
    im = t24.TABLE_CURRENT[k]
    print(f"{t:6.3f} {im:7.2f} {i_model[k]:8.3f} {pct(i_model[k], im):+6.1f} {i_after[k]:8.3f} {pct(i_after[k], im):+6.1f}")
print("(static torque and rotor-pole flux are unchanged: a constant end inductance adds neither)")

print("--- sensitivity of the static point (torque N.m, psi Wb-turns, peak iron |B| T)")
for label, scale, js in [("Js 1.98", 1.0, 1.98), ("Js 2.05", 1.0, 2.05), ("mesh x0.5", 0.5, t24.ASSUMED_JS)]:
    q, r, b = static(scale, js)
    tq = arkkio_torque(q, r)
    print(f"{label:<10} T {tq:.4f} ({pct(tq, t_ark):+.3f} % vs default)  psi {flux_linkage(q, r)[0]:.5f}  B {b:.2f}")

if JSON_PATH:
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps({
        "srmcore": version("srmcore"),
        "static_torque": {"model": float(t_ark), "measured": T_MEASURED, "error_pct": float(pct(t_ark, T_MEASURED))},
        "rotor_flux": {"model": float(flux), "measured": float(t24.TABLE_ROTOR_FLUX[-1]),
                       "error_pct": float(pct(flux, t24.TABLE_ROTOR_FLUX[-1]))},
        "current_rise_max_dev_pct": {
            "before": float(np.abs(pct(i_model, t24.TABLE_CURRENT)[1:]).max()),
            "after": float(np.abs(pct(i_after, t24.TABLE_CURRENT)[1:]).max())}}, indent=1))
