"""TEAM Problem 24 feasibility check: solve the locked-rotor rig with both solvers, compare static torque
and the voltage-step current rise (dpsi/dt = V - R*i on the psi(i) map) with the measured tables.

Run from the repo root:  .venv\\Scripts\\python examples\\team24_check.py [size_scale]
"""
import sys
import time
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from team24_fixture import RESISTANCE, VOLTAGE, team24_problem  # noqa: E402

from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque  # noqa: E402
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter  # noqa: E402
from srmcore.solvers.skfem_reference import SkfemReference  # noqa: E402

# Report Tables III and IV: time in s, current in A, torque in N.m.
TIME = np.array([0.002, 0.005, 0.010, 0.015, 0.020, 0.030, 0.040, 0.050, 0.060, 0.070, 0.080, 0.090, 0.100,
                 0.120, 0.140, 0.160, 0.180, 0.200, 0.240, 0.300])
CURRENT = np.array([0.91, 1.80, 2.95, 3.82, 4.49, 5.45, 6.05, 6.45, 6.71, 6.91, 7.04, 7.15, 7.22, 7.31,
                    7.36, 7.38, 7.40, 7.40, 7.41, 7.41])
TORQUE = np.array([0.02, 0.17, 0.39, 0.68, 0.96, 1.48, 1.90, 2.24, 2.48, 2.68, 2.82, 2.93, 3.02, 3.11,
                   3.17, 3.19, 3.21, 3.22, 3.22, 3.22])
I_FINAL = 7.41

scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
skfem, ngsolve = SkfemReference(), NgsolveAdapter()


def rel(x, y):
    return abs(x - y) / max(abs(y), 1e-30)


print(f"--- solver agreement at {I_FINAL} A (size_scale {scale})")
p = team24_problem(I_FINAL, scale)
print(f"nodes {len(p.nodes)}, triangles {len(p.triangles)}")
t0 = time.perf_counter()
ref = skfem.solve(p)
t1 = time.perf_counter()
ngs = ngsolve.solve(p)
t2 = time.perf_counter()
print(f"skfem {ref.status.value} it={ref.iterations} {t1 - t0:.1f}s; ngsolve {ngs.status.value} it={ngs.iterations} {t2 - t1:.1f}s")
psi_r, psi_n = flux_linkage(p, ref)[0], flux_linkage(p, ngs)[0]
tr = {"arkkio": (arkkio_torque(p, ref), arkkio_torque(p, ngs)),
      "virtual work": (virtual_work_torque(p, ref), virtual_work_torque(p, ngs))}
print(f"max|dA|/max|A| = {np.abs(ngs.a - ref.a).max() / np.abs(ref.a).max():.2e}")
print(f"psi  skfem {psi_r:.6f}  ngsolve {psi_n:.6f}  rel diff {rel(psi_n, psi_r):.2e}")
print(f"energy rel diff {rel(ngs.energy, ref.energy):.2e}  coenergy rel diff {rel(ngs.coenergy, ref.coenergy):.2e}")
for name, (a, b) in tr.items():
    print(f"T {name:<13} skfem {a:+.5f}  ngsolve {b:+.5f}  rel diff {rel(b, a):.2e} N.m")
bmag = np.hypot(ref.b[:, 0], ref.b[:, 1])
iron = p.element_law == 1
print(f"peak |B| in iron {bmag[iron].max():.3f} T (table ends at 2.472 T)")
t_arkkio = tr["arkkio"][0]
print(f"static torque {t_arkkio:+.3f} N.m (Arkkio) / {tr['virtual work'][0]:+.3f} (virtual work) vs measured 3.22: "
      f"{100 * (abs(t_arkkio) - 3.22) / 3.22:+.1f} %")

print("--- psi(i) map and current rise (skfem)")
grid = np.concatenate([np.linspace(0.0, 1.0, 5), np.linspace(1.5, 4.0, 6), np.linspace(4.5, 7.5, 7)])
psi, torque, a0 = [], [], None
for i in grid:
    q = team24_problem(i, scale)
    s = skfem.solve(q, initial=a0)
    assert s.status.value == "OK", (i, s.status)
    a0 = s.a
    psi.append(flux_linkage(q, s)[0])
    torque.append(arkkio_torque(q, s))
psi, torque = np.array(psi), np.array(torque)
psi_of_i, torque_of_i = PchipInterpolator(grid, psi), PchipInterpolator(grid, np.abs(torque))
dpsi = psi_of_i.derivative()
# dt = dpsi / (V - R i)  =>  t(i) = integral of psi'(i) / (V - R i) di
t_of_i = np.array([quad(lambda x: dpsi(x) / (VOLTAGE - RESISTANCE * x), 0.0, i, limit=200)[0] for i in np.linspace(0, 7.47, 300)])
i_fine = np.linspace(0, 7.47, 300)
i_model = np.interp(TIME, t_of_i, i_fine)
print(f"V/R = {VOLTAGE / RESISTANCE:.3f} A;  psi(7.41 A) = {psi_of_i(7.41):.5f} Wb-turns")
print(f"{'t/s':>6} {'i meas':>7} {'i model':>8} {'dev %':>7} {'T meas':>7} {'T model':>8} {'dev %':>7}")
for t, im, tm, ic in zip(TIME, CURRENT, TORQUE, i_model):
    tc = float(torque_of_i(ic))
    print(f"{t:6.3f} {im:7.2f} {ic:8.3f} {100 * (ic - im) / im:+7.1f} {tm:7.2f} {tc:8.3f} {100 * (tc - tm) / tm:+7.1f}")
