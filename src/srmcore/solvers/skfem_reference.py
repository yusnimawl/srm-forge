"""Reference solver: scikit-fem assembly, Newton with the consistent Jacobian ν·I + 2·dν/d(B²)·B⊗B,
backtracking line search, and the fallback chain damped → current ramp → NONCONVERGED (spec §6)."""
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from skfem import Basis, BilinearForm, ElementTriP1, LinearForm, MeshTri, asm
from skfem.helpers import dot, grad

from ..fields.solution import FieldSolution, SolveStatus
from ..materials.laws import LinearLaw
from ..physics.energy import field_energies
from ..physics.fem import element_flux_density
from ..physics.problem import Magnetostatic2D
from .settings import QUADRATURE_ORDER, NewtonSettings

# Below this relative residual the damped fallback stops capping the Newton step.
_FULL_STEP_RESIDUAL = 1e-2


@BilinearForm
def _secant(u, v, w):
    return w["nu"] * dot(grad(u), grad(v))


@BilinearForm
def _tangent(u, v, w):
    ga = w["ga"]
    return w["nu"] * dot(grad(u), grad(v)) + 2 * w["dnu"] * dot(grad(u), ga) * dot(grad(v), ga)


@LinearForm
def _load(v, w):
    return w["j"] * v


class _System:
    """One problem bound to its (cached) scikit-fem basis."""

    def __init__(self, problem: Magnetostatic2D, basis: Basis | None = None):
        if basis is None:
            mesh = MeshTri(np.ascontiguousarray(problem.nodes.T, dtype=float),
                           np.ascontiguousarray(problem.triangles.T, dtype=np.int64))
            basis = Basis(mesh, ElementTriP1(), intorder=QUADRATURE_ORDER)
        self.basis = basis
        self.problem = problem
        self.nq = basis.X.shape[1]
        self.free = np.setdiff1d(np.arange(basis.N), problem.dirichlet_nodes)
        self.groups = [(law, np.flatnonzero(problem.element_law == k)) for k, law in enumerate(problem.laws)]
        self.linear = all(isinstance(law, LinearLaw) for law in problem.laws)

    def _q(self, per_element: np.ndarray) -> np.ndarray:
        return np.repeat(per_element[:, None], self.nq, axis=1)

    def load(self) -> np.ndarray:
        return asm(_load, self.basis, j=self._q(self.problem.current_density()))

    def material(self, a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        b = element_flux_density(self.problem.nodes, self.problem.triangles, a)
        b2 = b[:, 0] ** 2 + b[:, 1] ** 2
        nu, dnu = np.empty_like(b2), np.empty_like(b2)
        for law, idx in self.groups:
            nu[idx], dnu[idx] = law.nu_dnu(b2[idx])
        return b, nu, dnu

    def residual(self, a: np.ndarray, f: np.ndarray):
        b, nu, dnu = self.material(a)
        return asm(_secant, self.basis, nu=self._q(nu)) @ a - f, nu, dnu

    def tangent(self, a: np.ndarray, nu: np.ndarray, dnu: np.ndarray) -> sp.csr_matrix:
        return asm(_tangent, self.basis, nu=self._q(nu), dnu=self._q(dnu), ga=self.basis.interpolate(a).grad)

    def solve_free(self, matrix: sp.spmatrix, rhs: np.ndarray) -> np.ndarray:
        out = np.zeros(self.basis.N)
        out[self.free] = spla.spsolve(matrix[self.free][:, self.free].tocsc(), rhs[self.free])
        return out


@dataclass
class _Outcome:
    a: np.ndarray
    converged: bool
    iterations: int
    residual: float
    delta: float


def _newton(system: _System, f: np.ndarray, a0: np.ndarray, settings: NewtonSettings,
            max_step: float, max_iterations: int) -> _Outcome:
    free = system.free
    f_norm = np.linalg.norm(f[free])
    a = a0.copy()
    a[system.problem.dirichlet_nodes] = 0.0
    r, nu, dnu = system.residual(a, f)
    res, delta = np.linalg.norm(r[free]) / f_norm, np.inf
    for it in range(1, max_iterations + 1):
        da = system.solve_free(system.tangent(a, nu, dnu), -r)
        step = max_step if res > _FULL_STEP_RESIDUAL else 1.0
        for _ in range(settings.max_halvings):
            trial = a + step * da
            r_t, nu_t, dnu_t = system.residual(trial, f)
            res_t = np.linalg.norm(r_t[free]) / f_norm
            # Below tolerance the residual sits at round-off and may not decrease further.
            if res_t < res or res_t < settings.residual_tol:
                break
            step /= 2
        else:
            # No step reduced the residual: stalled. Keep the last accepted iterate.
            return _Outcome(a, False, it, res, delta)
        a, r, nu, dnu, res = trial, r_t, nu_t, dnu_t, res_t
        delta = step * np.linalg.norm(da) / max(np.linalg.norm(a), np.finfo(float).tiny)
        if res < settings.residual_tol and delta < settings.delta_tol:
            return _Outcome(a, True, it, res, delta)
    return _Outcome(a, False, max_iterations, res, delta)


class SkfemReference:
    name = "skfem_reference"

    def __init__(self, settings: NewtonSettings = NewtonSettings()):
        self.settings = settings
        self._cache: tuple[np.ndarray, np.ndarray, Basis] | None = None

    def sensitivity(self, problem: Magnetostatic2D, a: np.ndarray) -> np.ndarray:
        system = self._bind(problem)
        a = np.asarray(a, float)
        _, nu, dnu = system.material(a)
        lu = spla.splu(system.tangent(a, nu, dnu)[system.free][:, system.free].tocsc())
        m = len(problem.winding.circuits)
        out = np.zeros((system.basis.N, m))
        for k in range(m):
            unit = problem.with_currents(np.eye(m)[k])
            rhs = asm(_load, system.basis, j=system._q(unit.current_density()))
            out[system.free, k] = lu.solve(rhs[system.free])
        return out

    def _bind(self, problem: Magnetostatic2D) -> _System:
        """Reuse the basis while the mesh arrays are the same objects (a current sweep on one mesh)."""
        c = self._cache
        basis = c[2] if c is not None and c[0] is problem.nodes and c[1] is problem.triangles else None
        system = _System(problem, basis)
        self._cache = (problem.nodes, problem.triangles, system.basis)
        return system

    def linearize(self, problem: Magnetostatic2D, a: np.ndarray) -> tuple[np.ndarray, sp.csr_matrix]:
        """Residual r(A) = K(ν(A))·A - f and the consistent tangent ∂r/∂A, over all nodes."""
        system = self._bind(problem)
        r, nu, dnu = system.residual(np.asarray(a, float), system.load())
        return r, system.tangent(np.asarray(a, float), nu, dnu)

    def solve(self, problem: Magnetostatic2D, initial: np.ndarray | None = None) -> FieldSolution:
        system = self._bind(problem)
        n = system.basis.N
        if initial is not None and np.shape(initial) != (n,):
            raise ValueError(f"initial guess has shape {np.shape(initial)}, expected ({n},) for this mesh")
        if initial is not None and not np.all(np.isfinite(initial)):
            raise ValueError("initial guess contains non-finite values")
        cfg = self.settings
        f = system.load()
        zero = np.zeros(n)
        if not np.any(f[system.free]):
            return self._result(system, _Outcome(zero, True, 0, 0.0, 0.0), SolveStatus.OK, ())
        if system.linear:
            _, nu, dnu = system.residual(zero, f)
            a = system.solve_free(system.tangent(zero, nu, dnu), f)
            r, _, _ = system.residual(a, f)
            res = float(np.linalg.norm(r[system.free]) / np.linalg.norm(f[system.free]))
            return self._result(system, _Outcome(a, True, 1, res, 0.0), SolveStatus.OK, ())
        a0 = zero if initial is None else np.asarray(initial, float)
        out = _newton(system, f, a0, cfg, 1.0, cfg.max_iterations)
        if out.converged:
            return self._result(system, out, SolveStatus.OK, ())
        out = _newton(system, f, a0, cfg, cfg.damped_max_step, 2 * cfg.max_iterations)
        if out.converged:
            return self._result(system, out, SolveStatus.OK_WITH_FALLBACK, ("damped",))
        a, total = a0, 0
        for k in range(1, cfg.ramp_steps + 1):
            fraction = k / cfg.ramp_steps
            out = _newton(system, f * fraction, a, cfg, cfg.damped_max_step, 2 * cfg.max_iterations)
            a, total = out.a, total + out.iterations
            if not out.converged:
                break
        status = SolveStatus.OK_WITH_FALLBACK if out.converged else SolveStatus.NONCONVERGED
        return self._result(system, _Outcome(out.a, out.converged, total, out.residual, out.delta), status,
                            ("damped", "ramp"), fraction)

    @staticmethod
    def _result(system: _System, out: _Outcome, status: SolveStatus, fallbacks: tuple[str, ...],
                load_fraction: float = 1.0) -> FieldSolution:
        b, nu, dnu = system.material(out.a)
        w, wc = field_energies(system.problem, b)
        return FieldSolution(a=out.a, b=b, nu=nu, dnu_db2=dnu, energy=w, coenergy=wc, status=status,
                             iterations=out.iterations, residual=float(out.residual), delta_a=float(out.delta),
                             fallbacks=fallbacks, load_fraction=load_fraction)
