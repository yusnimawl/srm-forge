"""Nonlinear H(curl) magnetostatics on a 3D mesh: Newton on the magnetic energy, CG + BDDC steps."""
from __future__ import annotations

import re
import sys
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
    preconditioner: str = "bddc-condense"      # "bddc", "bddc-condense" (static condensation of interior dofs) or "hcurlamg"


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
    """Peak resident set of this process: ru_maxrss (kilobytes on Linux, bytes on macOS) or the Windows peak working set."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(process), ctypes.byref(counters), counters.cb)
        return int(counters.PeakWorkingSetSize)
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def _names(*names: str) -> str:
    """Region or face names as one NGSolve pattern (names are regular expressions there)."""
    return "|".join(re.escape(n) for n in names)


def solve3d(model: Model3D, ampere_turns: Mapping[str, float],
            initial: ng.GridFunction | None = None, max_iter: int = 30,
            threads: int | None = None) -> Solution3D:
    """Minimise the energy for the given coil ampere-turns; non-convergence is reported, never raised.

    The update's energy norm is sqrt(du.K du) with K the current linearisation; the residual is
    measured against the free-dof norm of the load (the gradient at A = 0). Runs inside a
    TaskManager with `threads` NGSolve threads (None: the NGSolve default, all cores).
    """
    previous = ng.GetNumThreads()
    if threads is not None:
        ng.SetNumThreads(threads)
    try:
        with ng.TaskManager():
            return _solve(model, ampere_turns, initial, max_iter)
    finally:
        if threads is not None:
            ng.SetNumThreads(previous)


def _solve(model: Model3D, ampere_turns: Mapping[str, float],
           initial: ng.GridFunction | None, max_iter: int) -> Solution3D:
    t0 = time.perf_counter()
    mesh = model.mesh
    materials = list(dict.fromkeys(mesh.GetMaterials()))   # one entry per region index otherwise
    missing = [m for m in materials if m not in model.laws]
    if missing:
        raise ValueError(f"no reluctivity law for mesh material {missing[0]!r}")
    coil_faces = [f"{c}{s}" for c in model.coils for s in ("_in", "_out")]
    fes = ng.HCurl(mesh, order=model.order, nograds=True,
                   dirichlet=_names(*coil_faces) + "|" + model.dirichlet)
    u = fes.TrialFunction()
    curl_u = ng.curl(u)
    nu0 = 1.0 / MU0

    condense = model.preconditioner == "bddc-condense"
    a = ng.BilinearForm(fes, condense=condense)
    for name in materials:
        law = model.laws[name]
        region = ng.dx(definedon=mesh.Materials(_names(name)))
        a += ng.Variation(energy_bspline(law)(ng.InnerProduct(curl_u, curl_u)) * region)
        a += ng.Variation(REGULARISATION * nu0 * ng.InnerProduct(u, u) * region)
    j = sum((coil_current_density(mesh, c, ampere_turns[c], model.order) for c in model.coils),
            ng.CoefficientFunction((0, 0, 0)))
    a += ng.Variation(-ng.InnerProduct(j, u) * ng.dx(definedon=mesh.Materials(_names(*model.coils))))
    pre = ng.Preconditioner(a, "hcurlamg" if model.preconditioner == "hcurlamg" else "bddc")

    gf = ng.GridFunction(fes)
    if initial is not None:
        gf.vec.data = initial.vec
    free = fes.FreeDofs()
    fixed = np.array([not f for f in free])
    res, du = gf.vec.CreateVector(), gf.vec.CreateVector()
    tmp, rhs = gf.vec.CreateVector(), gf.vec.CreateVector()

    def residual_norm() -> float:
        a.Apply(gf.vec, res)
        res.FV().NumPy()[fixed] = 0.0
        return float(np.linalg.norm(res.FV().NumPy()))

    base = gf.vec.CreateVector()
    base.data = gf.vec
    gf.vec[:] = 0
    reference = residual_norm()      # at A = 0 the gradient is minus the load
    gf.vec.data = base
    residuals: list[float] = []
    converged, iterations = False, 0
    for _ in range(max_iter):
        a.AssembleLinearization(gf.vec)
        pre.Update()
        r = residual_norm()
        residuals.append(r)
        if condense:
            rhs.data = res + a.harmonic_extension_trans * res
            du.data = CGSolver(a.mat, pre.mat, tol=LINEAR_TOL, maxiter=2000, printrates=False) * rhs
            du.data += a.harmonic_extension * du
            du.data += a.inner_solve * res
        else:
            du.data = CGSolver(a.mat, pre.mat, tol=LINEAR_TOL, maxiter=2000, printrates=False) * res
        tmp.data = a.mat * du
        du_norm = float(ng.sqrt(abs(ng.InnerProduct(du, tmp))))
        tmp.data = a.mat * gf.vec
        u_norm = float(ng.sqrt(abs(ng.InnerProduct(gf.vec, tmp))))
        if r <= NEWTON_TOL * reference and du_norm <= NEWTON_TOL * u_norm:
            converged = True
            break
        e0, t = a.Energy(gf.vec), 1.0
        base.data = gf.vec
        for _ in range(LINE_SEARCH_HALVINGS + 1):
            gf.vec.data = base - t * du
            if a.Energy(gf.vec) <= e0 + 1e-12 * abs(e0):
                break
            t *= 0.5
        else:
            gf.vec.data = base      # no step lowers the energy
            break
        iterations += 1
    if not converged:
        residuals.append(residual_norm())
    return Solution3D(gf, converged, iterations, tuple(residuals), fes.ndof,
                      time.perf_counter() - t0, _peak_rss_bytes())
