"""NGSolve adapter: the tangent and load are assembled in NGSolve, the secant residual is
`physics.fem.secant_residual` (numpy), and the solves use umfpack. Newton with the consistent Jacobian
ν·I + 2·dν/d(B²)·B⊗B, backtracking line search, and the fallback chain damped → current ramp →
NONCONVERGED (spec §6).

Material laws, flux density and energies come from the shared physics code. The Newton driver is a
separate implementation from skfem_reference on purpose: the two adapters cross-check each other."""
from dataclasses import dataclass

import ngsolve as ng
import numpy as np
from netgen.meshing import Element2D, FaceDescriptor, MeshPoint, Pnt
from netgen.meshing import Mesh as NetgenMesh

from ..fields.solution import FieldSolution, SolveStatus
from ..materials.laws import LinearLaw
from ..physics.energy import field_energies
from ..physics.fem import element_flux_density, p1_gradients, secant_residual
from ..physics.problem import Magnetostatic2D
from .settings import ELEMENT_ORDER, QUADRATURE_ORDER, NewtonSettings

# Below this relative residual the damped fallback stops capping the Newton step.
_FULL_STEP_RESIDUAL = 1e-2


def _netgen_mesh(nodes: np.ndarray, triangles: np.ndarray) -> ng.Mesh:
    """Points and elements are added in array order, so NGSolve vertex i is node i and element k is
    triangle k. Clockwise triangles are reversed (NGSolve needs a positive orientation)."""
    x, y = nodes[triangles, 0], nodes[triangles, 1]
    det = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0]) - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0])
    oriented = np.where((det < 0)[:, None], triangles[:, [0, 2, 1]], triangles)
    mesh = NetgenMesh(dim=2)
    points = [mesh.Add(MeshPoint(Pnt(float(px), float(py), 0.0))) for px, py in nodes]
    face = mesh.Add(FaceDescriptor(surfnr=1, domin=1, bc=1))
    for tri in oriented:
        mesh.Add(Element2D(face, [points[i] for i in tri]))
    return ng.Mesh(mesh)


class _Discretisation:
    """NGSolve spaces and forms for one mesh. The triangle rule is pinned to QUADRATURE_ORDER, the same as
    the scikit-fem reference. ν, dν/dB² and J are element-constant (order-0 L2) and P1 gradients are
    constant, so the integrals are exact at that order anyway. Only the tangent is assembled in NGSolve;
    the secant residual is `physics.fem.secant_residual`."""

    def __init__(self, nodes: np.ndarray, triangles: np.ndarray):
        self.nodes, self.triangles = nodes, triangles
        self.grads, self.areas = p1_gradients(nodes, triangles)
        mesh = _netgen_mesh(nodes, triangles)
        space = ng.H1(mesh, order=ELEMENT_ORDER)
        if space.ndof != len(nodes):
            raise RuntimeError(f"NGSolve has {space.ndof} dofs for {len(nodes)} nodes")
        constants = ng.L2(mesh, order=0)
        self.nu, self.dnu, self.j = (ng.GridFunction(constants) for _ in range(3))
        self.u = ng.GridFunction(space)
        trial, test = space.TnT()
        grad_a = ng.grad(self.u)
        dx = ng.dx(intrules={ng.TRIG: ng.IntegrationRule(ng.TRIG, QUADRATURE_ORDER)})
        self.tangent = ng.BilinearForm(space)
        self.tangent += (self.nu * ng.grad(trial) * ng.grad(test)
                         + 2 * self.dnu * (ng.grad(trial) * grad_a) * (ng.grad(test) * grad_a)) * dx
        self.load = ng.LinearForm(space)
        self.load += self.j * test * dx

    def matches(self, problem: Magnetostatic2D) -> bool:
        return (problem.nodes is self.nodes or np.array_equal(problem.nodes, self.nodes)) and (
            problem.triangles is self.triangles or np.array_equal(problem.triangles, self.triangles))


class _System:
    """One problem bound to its (cached) discretisation."""

    def __init__(self, problem: Magnetostatic2D, disc: _Discretisation):
        self.problem, self.disc = problem, disc
        self.n = len(problem.nodes)
        self.free = np.setdiff1d(np.arange(self.n), problem.dirichlet_nodes)
        self.freedofs = ng.BitArray(self.n)
        self.freedofs.Clear()
        for i in self.free:
            self.freedofs.Set(int(i))
        self.groups = [(law, np.flatnonzero(problem.element_law == k)) for k, law in enumerate(problem.laws)]
        self.linear = all(isinstance(law, LinearLaw) for law in problem.laws)

    def load(self) -> np.ndarray:
        self.disc.j.vec.FV().NumPy()[:] = self.problem.current_density()
        self.disc.load.Assemble()
        return self.disc.load.vec.FV().NumPy().copy()

    def material(self, a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        b = element_flux_density(self.problem.nodes, self.problem.triangles, a)
        b2 = b[:, 0] ** 2 + b[:, 1] ** 2
        nu, dnu = np.empty_like(b2), np.empty_like(b2)
        for law, idx in self.groups:
            nu[idx], dnu[idx] = law.nu_dnu(b2[idx])
        return b, nu, dnu

    def _bind(self, a: np.ndarray, nu: np.ndarray, dnu: np.ndarray) -> None:
        self.disc.nu.vec.FV().NumPy()[:] = nu
        self.disc.dnu.vec.FV().NumPy()[:] = dnu
        self.disc.u.vec.FV().NumPy()[:] = a

    def residual(self, a: np.ndarray, f: np.ndarray):
        _, nu, dnu = self.material(a)
        r = secant_residual(self.disc.grads, self.disc.areas, self.disc.triangles, nu, a)
        return r - f, nu, dnu

    def solve_tangent(self, a: np.ndarray, nu: np.ndarray, dnu: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        self._bind(a, nu, dnu)
        self.disc.tangent.Assemble()
        inverse = self.disc.tangent.mat.Inverse(self.freedofs, inverse="umfpack")
        b = ng.BaseVector(self.n)
        b.FV().NumPy()[:] = rhs
        x = b.CreateVector()
        x.data = inverse * b
        out = x.FV().NumPy().copy()
        out[self.problem.dirichlet_nodes] = 0.0
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
        da = system.solve_tangent(a, nu, dnu, -r)
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


class NgsolveAdapter:
    name = "ngsolve"
    version = ng.__version__

    def __init__(self, settings: NewtonSettings = NewtonSettings()):
        self.settings = settings
        self._disc: _Discretisation | None = None

    def sensitivity(self, problem: Magnetostatic2D, a: np.ndarray) -> np.ndarray:
        system = self._bind(problem)
        a = np.asarray(a, float)
        _, nu, dnu = system.material(a)
        system._bind(a, nu, dnu)
        system.disc.tangent.Assemble()
        inverse = system.disc.tangent.mat.Inverse(system.freedofs, inverse="umfpack")
        m = len(problem.winding.circuits)
        out = np.zeros((system.n, m))
        for k in range(m):
            system.disc.j.vec.FV().NumPy()[:] = problem.with_currents(np.eye(m)[k]).current_density()
            system.disc.load.Assemble()
            rhs = ng.BaseVector(system.n)
            rhs.FV().NumPy()[:] = system.disc.load.vec.FV().NumPy()
            x = rhs.CreateVector()
            x.data = inverse * rhs
            out[:, k] = x.FV().NumPy()
        out[problem.dirichlet_nodes] = 0.0
        return out

    def _bind(self, problem: Magnetostatic2D) -> _System:
        """Reuse the discretisation while the mesh is unchanged (a current sweep on one mesh)."""
        if self._disc is None or not self._disc.matches(problem):
            self._disc = _Discretisation(problem.nodes, problem.triangles)
        return _System(problem, self._disc)

    def solve(self, problem: Magnetostatic2D, initial: np.ndarray | None = None) -> FieldSolution:
        n = len(problem.nodes)
        if initial is not None and np.shape(initial) != (n,):
            raise ValueError(f"initial guess has shape {np.shape(initial)}, expected ({n},) for this mesh")
        if initial is not None and not np.all(np.isfinite(initial)):
            raise ValueError("initial guess contains non-finite values")
        system = self._bind(problem)
        cfg = self.settings
        f = system.load()
        zero = np.zeros(n)
        if not np.any(f[system.free]):
            return self._result(system, _Outcome(zero, True, 0, 0.0, 0.0), SolveStatus.OK, ())
        if system.linear:
            r, nu, dnu = system.residual(zero, f)
            a = system.solve_tangent(zero, nu, dnu, f)
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
