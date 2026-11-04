"""Nonlinear H(curl) magnetostatics on a 3D mesh: Newton on the magnetic energy, CG + BDDC steps."""
from __future__ import annotations

import resource
import time
from dataclasses import dataclass
from typing import Mapping

import ngsolve as ng
import numpy as np
from ngsolve.krylovspace import CGSolver

from srmcore.materials.laws import ReluctivityLaw
from srmcore.model.constants import MU0

from .coil import coil_current_density
from .material import energy_bspline

# times nu0, on every region: without it in the iron the higher-order gradient modes there are
# singular and BDDC-preconditioned CG stalls (measured: 2000 iterations against 50)
REGULARISATION = 1e-6
LINEAR_TOL = 1e-10
NEWTON_TOL = 1e-8
LINE_SEARCH_HALVINGS = 8


@dataclass(frozen=True)
class Model3D:
    """A 3D mesh (the half z >= 0, or a slab), a law per volume material and the coil solids.

    Every coil's `<coil>_in` and `<coil>_out` faces are also Dirichlet (they lie on the mirror
    plane or on the slab faces).
    """
    mesh: ng.Mesh
    laws: dict[str, ReluctivityLaw]
    coils: tuple[str, ...]
    dirichlet: str = "sym_z|outer"
    order: int = 2


@dataclass(frozen=True, eq=False)
class Solution3D:
    a: ng.GridFunction
    converged: bool
    iterations: int
    residuals: tuple[float, ...]
    ndof: int
    seconds: float
    peak_rss_bytes: int


def _peak_rss_bytes() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024   # kilobytes on Linux


def solve3d(model: Model3D, ampere_turns: Mapping[str, float],
            initial: ng.GridFunction | None = None, max_iter: int = 30) -> Solution3D:
    """Minimise the energy for the given coil ampere-turns; non-convergence is reported, never raised.

    The update's energy norm is sqrt(du.K du) with K the current linearisation.
    """
    t0 = time.perf_counter()
    mesh = model.mesh
    materials = list(dict.fromkeys(mesh.GetMaterials()))   # one entry per region index otherwise
    missing = [m for m in materials if m not in model.laws]
    if missing:
        raise ValueError(f"no reluctivity law for mesh material {missing[0]!r}")
    coil_faces = [f"{c}{s}" for c in model.coils for s in ("_in", "_out")]
    fes = ng.HCurl(mesh, order=model.order, nograds=True,
                   dirichlet="|".join([model.dirichlet, *coil_faces]))
    u = fes.TrialFunction()
    curl_u = ng.curl(u)
    nu0 = 1.0 / MU0

    a = ng.BilinearForm(fes)
    for name in materials:
        law = model.laws[name]
        region = ng.dx(definedon=mesh.Materials(name))
        a += ng.Variation(energy_bspline(law)(ng.InnerProduct(curl_u, curl_u)) * region)
        a += ng.Variation(REGULARISATION * nu0 * ng.InnerProduct(u, u) * region)
    j = sum((coil_current_density(mesh, c, ampere_turns[c]) for c in model.coils),
            ng.CoefficientFunction((0, 0, 0)))
    a += ng.Variation(-ng.InnerProduct(j, u) * ng.dx(definedon=mesh.Materials("|".join(model.coils))))
    pre = ng.Preconditioner(a, "bddc")

    gf = ng.GridFunction(fes)
    if initial is not None:
        gf.vec.data = initial.vec
    free = fes.FreeDofs()
    fixed = np.array([not f for f in free])
    res, du = gf.vec.CreateVector(), gf.vec.CreateVector()
    tmp = gf.vec.CreateVector()

    def residual_norm() -> float:
        a.Apply(gf.vec, res)
        res.FV().NumPy()[fixed] = 0.0
        return float(np.linalg.norm(res.FV().NumPy()))

    residuals: list[float] = []
    converged, iterations = False, 0
    for _ in range(max_iter):
        a.AssembleLinearization(gf.vec)
        pre.Update()
        r = residual_norm()
        residuals.append(r)
        du.data = CGSolver(a.mat, pre.mat, tol=LINEAR_TOL, maxiter=2000, printrates=False) * res
        tmp.data = a.mat * du
        du_norm = float(ng.sqrt(abs(ng.InnerProduct(du, tmp))))
        tmp.data = a.mat * gf.vec
        u_norm = float(ng.sqrt(abs(ng.InnerProduct(gf.vec, tmp))))
        if r <= NEWTON_TOL * residuals[0] and du_norm <= NEWTON_TOL * u_norm:
            converged = True
            break
        e0, t = a.Energy(gf.vec), 1.0
        base = gf.vec.CreateVector()
        base.data = gf.vec
        for _ in range(LINE_SEARCH_HALVINGS + 1):
            gf.vec.data = base - t * du
            if a.Energy(gf.vec) <= e0 + 1e-12 * abs(e0):
                break
            t *= 0.5
        iterations += 1
    else:
        a.AssembleLinearization(gf.vec)
        residuals.append(residual_norm())
    return Solution3D(gf, converged, iterations, tuple(residuals), fes.ndof,
                      time.perf_counter() - t0, _peak_rss_bytes())
