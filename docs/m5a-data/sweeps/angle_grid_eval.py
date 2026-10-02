"""THROWAWAY: evaluate candidate angle grids against the dense sweeps (angle-interpolation error only)."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\y\srm-designer\tests")
from conftest import make_8_6, make_12_8, make_24_16  # noqa: E402

from srmcore.maps.grids import angle_grid  # noqa: E402
from srmcore.maps.tables import angle_spline  # noqa: E402

HERE = Path(__file__).parent
MACH = {"8_6": make_8_6(), "8_6_sharp": make_8_6(stator_fillet_radius=0, rotor_fillet_radius=0),
        "12_8": make_12_8(), "24_16": make_24_16()}


def corners(m, tau):
    bs, br = m.stator_pole_arc, m.rotor_pole_arc
    tf, tc = abs(br - bs) / 2, (bs + br) / 2
    return sorted({0.0, tf % tau, tc % tau, (tau - tc) % tau, (tau - tf) % tau})


def density_grid(m, d, n, tau, amp, width):
    """Inverse-CDF placement with density 1 + amp * sum of periodic Gaussians (width as fraction of tau) at the corners."""
    x = np.linspace(0, tau, 20001)
    rho = np.ones_like(x)
    for c in corners(m, tau):
        for k in (-1, 0, 1):
            rho += amp * np.exp(-0.5 * ((x - c - k * tau) / (width * tau)) ** 2)
    cdf = np.concatenate([[0], np.cumsum((rho[1:] + rho[:-1]) / 2 * np.diff(x))])
    cdf /= cdf[-1]
    t = np.interp(np.arange(n) / n, cdf, x)
    pitch = 2 * math.pi / d
    return np.unique(np.round(t / pitch).astype(int) % round(tau / pitch))


def evaluate(name, idx):
    z = np.load(HERE / f"sweep_{name}.npz")
    a, tau = z["angles"], float(z["tau"])
    idx = np.unique(idx)
    rest = np.setdiff1d(np.arange(len(a)), idx)
    peak = np.abs(z["torque"]).max()
    psimax = np.abs(z["psi"]).max()
    et = max(np.abs(angle_spline(a[idx], z["torque"][idx, j], tau)(a[rest]) - z["torque"][rest, j]).max()
             for j in range(len(z["currents"]))) / peak
    ep = max(np.abs(angle_spline(a[idx], z["psi"][idx, j], tau)(a[rest]) - z["psi"][rest, j]).max()
             for j in range(len(z["currents"]))) / psimax
    return len(idx), 100 * ep, 100 * et


def search():
    names = [n for n in MACH if (HERE / f"sweep_{n}.npz").exists()]
    print("designs:", names)
    for n_ang in (12, 16, 20, 24, 30, 36, 40, 48, 60):
        best = []
        for amp in (0, 1, 1.5, 2, 3, 4):
            for w in (0.01, 0.015, 0.02, 0.025, 0.03, 0.04):
                if amp == 0 and w != 0.01:
                    continue
                worst_p = worst_t = 0.0
                ks = []
                for name in names:
                    z = np.load(HERE / f"sweep_{name}.npz")
                    idx = density_grid(MACH[name], int(z["divisions"]), n_ang, float(z["tau"]), amp, w)
                    k, ep, et = evaluate(name, idx)
                    worst_p, worst_t = max(worst_p, ep), max(worst_t, et)
                    ks.append(k)
                best.append((worst_t, worst_p, amp, w, min(ks)))
        best.sort()
        print(f"n={n_ang}: " + "  ".join(f"a{a} w{w} (min n {k}): T{t:.2f} psi{p:.3f}" for t, p, a, w, k in best[:4]))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "search":
    search()
elif __name__ == "__main__":
    names = [n for n in MACH if (HERE / f"sweep_{n}.npz").exists()]
    for n_ang in (12, 30, 60):
        print(f"--- n = {n_ang}")
        for name in names:
            m = MACH[name]
            z = np.load(HERE / f"sweep_{name}.npz")
            d, tau = int(z["divisions"]), float(z["tau"])
            pitch = 2 * math.pi / d
            stock = np.round(angle_grid(m, d, n_ang) / pitch).astype(int)
            rows = [("stock", stock)]
            unif = np.round(np.arange(n_ang) / n_ang * tau / pitch).astype(int)
            rows.append(("uniform", unif))
            for amp in (2, 4, 8):
                for w in (0.01, 0.02, 0.04):
                    rows.append((f"dens a{amp} w{w}", density_grid(m, d, n_ang, tau, amp, w)))
            res = [(lab,) + evaluate(name, idx) for lab, idx in rows]
            print(name, "  ".join(f"{lab}: n{k} psi{ep:.3f} T{et:.2f}" for lab, k, ep, et in res))
