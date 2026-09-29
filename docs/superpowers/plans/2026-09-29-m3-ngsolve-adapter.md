# M3 NGSolve Adapter Go/No-Go Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide whether NGSolve becomes the primary solver, by building an NGSolve adapter at parity with `skfem_reference`, adding nodal-force (virtual-work) torque, running a band-pitch convergence study, and checking TEAM Problem 24 is feasible.

**Architecture:** `solvers/ngsolve_adapter.py` implements the same `SolverAdapter` protocol as `skfem_reference` and receives the same `Magnetostatic2D`. NGSolve does the assembly and the direct solve. The Newton driver and material evaluation stay in numpy, using the shared `physics` code. Virtual-work torque is solver-independent and lives in `post/`. The M3 spike (throwaway) already showed agreement with skfem to about 1e-11 on the 8/6 `screening` mesh.

**Tech Stack:** NGSolve 6.2.2607 (`netgen-mesher` comes with it), scikit-fem (unchanged), numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` §6 (adapter contract), §7.3 (Arkkio vs nodal-force within 1 % of peak torque), §8 test 3 and 5, §9 row M3 and its go/no-go rule, §11 (decision log).

## Global Constraints

- Element order 1 (P1) and quadrature order 2 in every adapter (`solvers/settings.py`: `ELEMENT_ORDER`, `QUADRATURE_ORDER`).
- Newton tolerances pinned in `NewtonSettings`: residual and ΔA both below 1e-8; fallback chain damped, then current ramp, then `NONCONVERGED`. An adapter never raises for non-convergence.
- `skfem_reference.py` stays unchanged. Its independence is the cross-check.
- Only `solvers/` may import `ngsolve` or `netgen`. `tests/test_import_rules.py` enforces it. Layers exchange plain numpy data; never pass NGSolve objects out of `solvers/`.
- Everything in SI units. Python >= 3.12, numpy >= 2.0.
- Cross-solver agreement (same mesh, order, quadrature, tolerances and B-H): relative difference <= 1e-4.
- Arkkio vs nodal-force torque within 1 % of peak torque.
- Test file basenames must be unique (`tests/` has no `__init__.py`). Fast suite stays under 10 minutes; long tests get `@pytest.mark.slow`.
- Comments explain the code as it is now; no task or plan history in comments.
- Go/no-go (spec §9): if NGSolve cannot reach cross-solver agreement and TEAM 24 behaviour within 2 weeks of M3 start, skfem stays primary. The owner makes the call and records it in spec §11.
- Commit only after the owner approves. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

Failure modes the spec implies but no task would otherwise exercise, most likely first:

1. A `Magnetostatic2D` whose triangles are clockwise: the adapter must give the same answer as with counter-clockwise ones (test in Task 2).
2. One adapter instance solving two different meshes in a row (cache keyed on the mesh): the second answer must equal a fresh adapter's (Task 2).
3. Zero current and a wrong-shaped or non-finite initial guess: same behaviour as skfem, i.e. OK with 0 iterations, and `ValueError` (Task 2).
4. Non-convergence: status `NONCONVERGED`, no exception (Task 2).
5. Torque at an angle between band grid positions, and after wrapping past 2π: parity must still hold (Task 3).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/srmcore/post/quantities.py` (modify) | add `virtual_work_torque` |
| `src/srmcore/solvers/ngsolve_adapter.py` (create) | `NgsolveAdapter` |
| `pyproject.toml`, `.github/workflows/ci.yml`, `requirements.txt` | `ngsolve` optional extra, CI install, pinned freeze |
| `tests/post/test_virtual_work_torque.py` (create) | nodal-force torque vs Arkkio |
| `tests/solvers/test_ngsolve_adapter.py` (create) | adapter unit tests |
| `tests/solvers/test_cross_solver.py` (create) | NGSolve vs skfem on toroid and 8/6, several angles |
| `examples/band_pitch_convergence.py`, `tests/mesh/test_band_pitch_convergence.py` (create) | band-pitch study |
| `tests/team24_fixture.py`, `examples/team24_check.py`, `docs/team24-feasibility.md` (create) | TEAM 24 feasibility |
| Spec §9/§10/§11, `CLAUDE.md` (modify) | record the decision |

---

### Task 1: Virtual-work (nodal-force) torque

**Files:**
- Modify: `src/srmcore/post/quantities.py`
- Test: `tests/post/test_virtual_work_torque.py`

**Interfaces:**
- Consumes: `Magnetostatic2D` (`nodes`, `triangles`, `element_law`, `laws`, `depth`, `band: BandInfo(elements, inner_radius, outer_radius)`), `FieldSolution.a`, `physics.fem.element_flux_density`, `physics.fem.triangle_areas`, `arkkio_torque`.
- Produces: `virtual_work_torque(problem: Magnetostatic2D, solution: FieldSolution, delta: float = 1e-6) -> float`, in N·m, positive counter-clockwise on the rotor.

**Method.** With A held fixed, the discrete functional Π = depth·Σ area·w(|B|) − ∫J·A. At the solution, W′ = −Π, so T = ∂W′/∂θ = −∂Π/∂θ. Rotating the rotor rigidly changes Π only in the band elements. Their nodes move by a rotation φ(r)·δ, where φ = 1 on the rotor side (r ≤ inner radius) and 0 on the stator side (r ≥ outer radius), linear between. The band is air with no current, so the J·A term is constant and dropped. A central difference on ±δ gives the derivative.

- [ ] **Step 1: Write the failing test**

```python
"""Nodal-force (virtual-work) torque: agrees with Arkkio on the 8/6 screening mesh (spec §7.3)."""
import math

import pytest

from conftest import make_8_6
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, virtual_work_torque
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def solved():
    static = build_machine_mesh(DESIGN)
    problem = machine_problem(mesh_at_angle(static, math.radians(10.0)), DESIGN, {"A": 20.0})
    return problem, SkfemReference().solve(problem)


def test_virtual_work_matches_arkkio_within_one_percent(solved):
    problem, solution = solved
    arkkio = arkkio_torque(problem, solution)
    assert arkkio < 0                                   # counter-clockwise motoring sign at this angle
    assert virtual_work_torque(problem, solution) == pytest.approx(arkkio, abs=0.01 * abs(arkkio))


def test_virtual_work_needs_a_band(solved):
    import dataclasses
    problem, solution = solved
    with pytest.raises(ValueError, match="band"):
        virtual_work_torque(dataclasses.replace(problem, band=None), solution)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/post/test_virtual_work_torque.py -v`
Expected: FAIL, `ImportError: cannot import name 'virtual_work_torque'`.

- [ ] **Step 3: Implement**

In `src/srmcore/post/quantities.py`, change the import `from ..physics.fem import triangle_areas` to `from ..physics.fem import element_flux_density, triangle_areas`, then add after `arkkio_torque`:

```python
def virtual_work_torque(problem: Magnetostatic2D, solution: FieldSolution, delta: float = 1e-6) -> float:
    """Nodal-force torque T = -dΠ/dθ at fixed A, N·m, positive counter-clockwise on the rotor.

    Π = L·Σ area·w(|B|) - ∫J·A is the discrete energy functional, so W' = -Π at the solution. A virtual
    rotation of the rotor moves the band nodes by φ(r)·δ (φ = 1 at the rotor side, 0 at the stator side,
    linear between); every other element rotates rigidly or not at all and keeps its energy. The band is
    air without current, so only the field energy of the band elements varies. Central difference in δ."""
    if problem.band is None:
        raise ValueError("Virtual-work torque needs a moving band (problem.band is None)")
    band = problem.band
    el = band.elements
    tri = problem.triangles[el]
    a = solution.a[tri].reshape(-1)
    corners = problem.nodes[tri]                                       # (n, 3, 2)
    radius = np.hypot(corners[..., 0], corners[..., 1])
    phi = np.clip((band.outer_radius - radius) / (band.outer_radius - band.inner_radius), 0.0, 1.0)
    local_tri = np.arange(3 * len(el)).reshape(-1, 3)
    groups = [(law, np.flatnonzero(problem.element_law[el] == k)) for k, law in enumerate(problem.laws)]

    def band_energy(angle: float) -> float:
        c, s = np.cos(angle * phi), np.sin(angle * phi)
        moved = np.stack([corners[..., 0] * c - corners[..., 1] * s,
                          corners[..., 0] * s + corners[..., 1] * c], axis=-1).reshape(-1, 2)
        b = element_flux_density(moved, local_tri, a)
        bm = np.hypot(b[:, 0], b[:, 1])
        area = triangle_areas(moved, local_tri)
        return problem.depth * sum(float(law.energy_density(bm[idx]) @ area[idx]) for law, idx in groups if len(idx))

    return -(band_energy(delta) - band_energy(-delta)) / (2 * delta)
```

Note: `element_flux_density` indexes `a[triangles]`, so pass `a` flattened in the same node order as `local_tri` (as above).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/post/test_virtual_work_torque.py -v`
Expected: PASS. If the 1 % check fails, do not loosen the tolerance: report the measured values (virtual work, Arkkio, ratio) as a finding and stop; the owner decides.

- [ ] **Step 5: Slow scan over angles**

Append to the same test file:

```python
@pytest.mark.slow
def test_virtual_work_tracks_arkkio_over_a_stroke():
    static = build_machine_mesh(DESIGN)
    solver = SkfemReference()
    pairs = []
    for deg in (2.0, 6.0, 10.0, 14.0, 18.0, 22.0):
        p = machine_problem(mesh_at_angle(static, math.radians(deg)), DESIGN, {"A": 20.0})
        s = solver.solve(p)
        pairs.append((arkkio_torque(p, s), virtual_work_torque(p, s)))
    peak = max(abs(a) for a, _ in pairs)
    assert all(abs(a - v) <= 0.01 * peak for a, v in pairs), pairs
```

Run: `.venv\Scripts\python -m pytest tests/post/test_virtual_work_torque.py -m slow -v`. Same rule on failure.

- [ ] **Step 6: Commit** (after owner approval)

```bash
git add src/srmcore/post/quantities.py tests/post/test_virtual_work_torque.py
git commit -m "feat(post): virtual-work nodal-force torque, checked against Arkkio"
```

---

### Task 2: NGSolve adapter

**Files:**
- Create: `src/srmcore/solvers/ngsolve_adapter.py`
- Create: `tests/solvers/test_ngsolve_adapter.py`
- Modify: `pyproject.toml`, `.github/workflows/ci.yml`
- Add: `requirements.txt` (already generated from `pip freeze`; check it lists `ngsolve==6.2.2607`)

**Interfaces:**
- Consumes: `Magnetostatic2D`, `FieldSolution`, `SolveStatus`, `NewtonSettings`, `ELEMENT_ORDER`, `QUADRATURE_ORDER`, `physics.fem.element_flux_density`, `physics.energy.field_energies`, `materials.laws.LinearLaw`.
- Produces: `NgsolveAdapter(settings: NewtonSettings = NewtonSettings())` with `name = "ngsolve"` and `solve(problem, initial=None) -> FieldSolution`, satisfying `SolverAdapter`.

**Design notes (from the spike).**
- The netgen mesh is built from `problem.nodes` and `problem.triangles` with points added in order and elements added in order. Vertex and element numbering then match the arrays (checked in the spike), so NGSolve degree-of-freedom `i` is node `i` and an order-0 L2 dof is element `k`.
- ν, dν/dB² and J are element-constant. They are kept in order-0 `L2` `GridFunction`s and filled from numpy each iteration. This is the same discretisation as skfem (P1, constant coefficients per element), so the integrals are exact at any quadrature order.
- The tangent is `ν ∇u·∇v + 2 dν (∇u·∇A)(∇v·∇A)`. The solver is NGSolve's `umfpack` (the spike measured 0.13–0.17 s against 0.22–0.31 s for scipy at 43k DOF).
- Assembly is single-threaded unless inside an `ng.TaskManager()`, which this adapter never enters (parallelism is by process, spec §7.2).
- The Newton driver is deliberately a separate copy of the skfem one; `skfem_reference.py` must not change and the two must not share code paths that could hide a bug.

- [ ] **Step 1: Packaging**

`pyproject.toml`: add under `[project.optional-dependencies]`:

```toml
ngsolve = ["ngsolve>=6.2.2601"]
```

`.github/workflows/ci.yml`: change the install line to `python -m pip install -e ".[dev,ngsolve]"`.

- [ ] **Step 2: Write the failing tests**

```python
"""NgsolveAdapter behaviour: same contract as SkfemReference (spec §6)."""
import dataclasses

import numpy as np
import pytest

pytest.importorskip("ngsolve")

from fem_fixtures import toroid_problem
from srmcore.fields.solution import SolveStatus
from srmcore.materials.laws import LinearLaw, library_law
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
from srmcore.solvers.settings import NewtonSettings

M19 = library_law("M19")


def _small(law, current):
    return toroid_problem(law, current, n_theta=48, layers_per_mm=1)


def test_zero_current_gives_zero_field_without_iterating():
    p = _small(M19, 0.0)
    s = NgsolveAdapter().solve(p, initial=np.ones(len(p.nodes)))
    assert s.status is SolveStatus.OK and s.iterations == 0
    assert not np.any(s.a) and s.energy == 0.0 and s.coenergy == 0.0


def test_linear_problem_is_one_solve_with_equal_energies():
    s = NgsolveAdapter().solve(_small(LinearLaw(1000.0), 100.0))
    assert s.status is SolveStatus.OK and s.iterations == 1 and s.residual < 1e-10
    assert s.energy == pytest.approx(s.coenergy, rel=1e-12)


def test_nonlinear_solve_meets_both_tolerances():
    s = NgsolveAdapter().solve(_small(M19, 3000.0))
    assert s.status in (SolveStatus.OK, SolveStatus.OK_WITH_FALLBACK)
    assert s.residual < 1e-8 and s.delta_a < 1e-8


def test_bad_initial_guess_is_rejected():
    p = _small(M19, 100.0)
    with pytest.raises(ValueError, match="shape"):
        NgsolveAdapter().solve(p, initial=np.zeros(3))
    with pytest.raises(ValueError, match="finite"):
        NgsolveAdapter().solve(p, initial=np.full(len(p.nodes), np.nan))


def test_nonconvergence_is_a_status_not_an_exception():
    s = NgsolveAdapter(NewtonSettings(max_iterations=1)).solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.NONCONVERGED


def test_clockwise_triangles_give_the_same_field():
    p = _small(M19, 3000.0)
    flipped = dataclasses.replace(p, triangles=np.ascontiguousarray(p.triangles[:, [0, 2, 1]]))
    a, b = NgsolveAdapter().solve(p).a, NgsolveAdapter().solve(flipped).a
    assert np.abs(a - b).max() <= 1e-9 * np.abs(a).max()


def test_one_adapter_solving_two_meshes_matches_fresh_adapters():
    p1, p2 = _small(M19, 3000.0), toroid_problem(M19, 3000.0, n_theta=64, layers_per_mm=1)
    shared = NgsolveAdapter()
    shared.solve(p1)
    a2 = shared.solve(p2).a
    assert np.abs(a2 - NgsolveAdapter().solve(p2).a).max() <= 1e-9 * np.abs(a2).max()
    assert np.abs(shared.solve(p1).a - NgsolveAdapter().solve(p1).a).max() <= 1e-9 * np.abs(a2).max()
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv\Scripts\python -m pip install -e ".[dev,ngsolve]"` then `.venv\Scripts\python -m pytest tests/solvers/test_ngsolve_adapter.py -v`
Expected: FAIL, `ModuleNotFoundError: srmcore.solvers.ngsolve_adapter`.

- [ ] **Step 4: Implement**

Create `src/srmcore/solvers/ngsolve_adapter.py`:

```python
"""NGSolve adapter: P1 assembly and direct solves in NGSolve, Newton with the consistent Jacobian
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
from ..physics.fem import element_flux_density
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
    """NGSolve spaces and forms for one mesh. ν, dν/dB² and J are element-constant (order-0 L2), so the
    integrals are exact at the pinned quadrature order."""

    def __init__(self, nodes: np.ndarray, triangles: np.ndarray):
        self.nodes, self.triangles = nodes, triangles
        mesh = _netgen_mesh(nodes, triangles)
        space = ng.H1(mesh, order=ELEMENT_ORDER)
        if space.ndof != len(nodes):
            raise RuntimeError(f"NGSolve has {space.ndof} dofs for {len(nodes)} nodes")
        constants = ng.L2(mesh, order=0)
        self.nu, self.dnu, self.j = (ng.GridFunction(constants) for _ in range(3))
        self.u = ng.GridFunction(space)
        trial, test = space.TnT()
        grad_a = ng.grad(self.u)
        dx = ng.dx(intorder=QUADRATURE_ORDER)
        self.secant = ng.BilinearForm(space)
        self.secant += self.nu * ng.grad(trial) * ng.grad(test) * dx
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
        self._bind(a, nu, dnu)
        self.disc.secant.Assemble()
        r = self.disc.secant.mat.CreateColVector()
        r.data = self.disc.secant.mat * self.disc.u.vec
        return r.FV().NumPy() - f, nu, dnu

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

    def __init__(self, settings: NewtonSettings = NewtonSettings()):
        self.settings = settings
        self._disc: _Discretisation | None = None

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
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/solvers/test_ngsolve_adapter.py tests/test_import_rules.py -v`
Expected: PASS. If `inverse="umfpack"` is unavailable on a platform, report it; do not silently switch solvers (CI on Linux will show it).

- [ ] **Step 6: Commit** (after owner approval)

```bash
git add src/srmcore/solvers/ngsolve_adapter.py tests/solvers/test_ngsolve_adapter.py pyproject.toml .github/workflows/ci.yml requirements.txt
git commit -m "feat(solvers): NGSolve adapter with the skfem Newton scheme; ngsolve optional extra"
```

---

### Task 3: Cross-solver parity, including band rotation

**Files:**
- Create: `tests/solvers/test_cross_solver.py`

**Interfaces:**
- Consumes: `NgsolveAdapter`, `SkfemReference`, `machine_problem`, `mesh_at_angle`, `flux_linkage`, `arkkio_torque`, `virtual_work_torque`, `toroid_problem`, `make_8_6`.
- Produces: the spec §8 test-3 evidence (agreement <= 1e-4).

- [ ] **Step 1: Write the tests**

```python
"""Cross-solver check (spec §8 test 3): NGSolve vs scikit-fem on the same problem, order, quadrature,
Newton tolerances and B-H. Required agreement is 1e-4."""
import math

import numpy as np
import pytest

pytest.importorskip("ngsolve")

from conftest import make_8_6
from fem_fixtures import toroid_problem
from srmcore.materials.laws import library_law
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
from srmcore.solvers.skfem_reference import SkfemReference

TOL = 1e-4
DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


def _rel(x, y):
    return abs(x - y) / max(abs(y), 1e-30)


def _agree(problem, check_torque=True):
    ref, ngs = SkfemReference().solve(problem), NgsolveAdapter().solve(problem)
    assert ref.status == ngs.status
    assert np.abs(ngs.a - ref.a).max() <= TOL * np.abs(ref.a).max()
    assert _rel(ngs.energy, ref.energy) <= TOL and _rel(ngs.coenergy, ref.coenergy) <= TOL
    psi_ref, psi_ngs = flux_linkage(problem, ref), flux_linkage(problem, ngs)
    assert np.allclose(psi_ngs, psi_ref, rtol=TOL, atol=TOL * np.abs(psi_ref).max())
    if check_torque:
        t_ref = arkkio_torque(problem, ref)
        assert abs(arkkio_torque(problem, ngs) - t_ref) <= TOL * abs(t_ref)
        v_ref = virtual_work_torque(problem, ref)
        assert abs(virtual_work_torque(problem, ngs) - v_ref) <= TOL * abs(v_ref)


def test_nonlinear_toroid_agrees():
    _agree(toroid_problem(library_law("M19"), 3000.0, n_theta=48, layers_per_mm=1), check_torque=False)


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


def test_8_6_agrees_at_ten_degrees(static):
    _agree(machine_problem(mesh_at_angle(static, math.radians(10.0)), DESIGN, {"A": 20.0}))


@pytest.mark.slow
@pytest.mark.parametrize("theta", [0.0, math.radians(7.3), math.radians(30.0), -math.radians(4.0), 2 * math.pi + 0.1])
@pytest.mark.parametrize("amps", [5.0, 20.0])
def test_8_6_agrees_across_angles_and_currents(static, theta, amps):
    """Includes angles between band grid positions and angles that wrap past 2π."""
    _agree(machine_problem(mesh_at_angle(static, theta), DESIGN, {"A": amps}))
```

- [ ] **Step 2: Run**

Run: `.venv\Scripts\python -m pytest tests/solvers/test_cross_solver.py -v` then `... -m slow -v` (one directory at a time; the machine is low on memory).
Expected: PASS at about 1e-9 or better. If any case exceeds 1e-4, stop and report the case and the numbers.

- [ ] **Step 3: Commit** (after owner approval)

```bash
git add tests/solvers/test_cross_solver.py
git commit -m "test(solvers): NGSolve vs scikit-fem cross-check on toroid and 8/6 across angles and currents"
```

---

### Task 4: Band-pitch convergence

**Files:**
- Create: `examples/band_pitch_convergence.py`
- Create: `tests/mesh/test_band_pitch_convergence.py`

**Interfaces:**
- Consumes: `resolve_mesh_settings`, `MeshSettings.airgap_circumferential_divisions`, `build_machine_mesh`, `mesh_at_angle`, `machine_problem`, `SkfemReference`, `arkkio_torque`, `virtual_work_torque`, `flux_linkage`.
- Produces: a printed table of ψ_A, Arkkio torque and nodal torque for band divisions D, 2D, 4D, at θ = 10° and at 10° + half a band pitch (D is the preset's default). The results go into spec §10 in Task 6.

- [ ] **Step 1: Write the script**

```python
"""Band-pitch convergence on the 8/6 `screening` mesh: ψ_A, Arkkio torque and nodal-force torque at 20 A
for band divisions D, 2D and 4D, at 10° and half a band pitch later.

Run from the repo root:  .venv\\Scripts\\python examples\\band_pitch_convergence.py
"""
import math

from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from srmcore.solvers.skfem_reference import SkfemReference

machine = RadialSRMParams(
    n_stator_poles=8, n_rotor_poles=6, n_phases=4,
    stator_outer_diameter=0.160, rotor_outer_diameter=0.080, air_gap=0.0004,
    stack_length=0.100, shaft_diameter=0.020,
    stator_pole_arc=math.radians(20.0), rotor_pole_arc=math.radians(22.0),
    stator_yoke_thickness=0.012, rotor_yoke_thickness=0.012,
    stator_fillet_radius=0.001, rotor_fillet_radius=0.001,
    turns_per_pole=60, fill_factor=0.5,
    slot_liner_thickness=0.0005, coil_inner_clearance=0.001,
)
base = resolve_mesh_settings(machine, MeshSettings(preset="screening")).band_divisions
solver = SkfemReference()
print(f"default band divisions D = {base}")
print(f"{'divisions':>9} {'offset':>10} {'psi_A [Wb]':>12} {'T_arkkio [Nm]':>14} {'T_nodal [Nm]':>13}")
for factor in (1, 2, 4):
    design = Design(machine=machine, mesh=MeshSettings(preset="screening", airgap_circumferential_divisions=base * factor))
    static = build_machine_mesh(design)
    for label, extra in (("0", 0.0), ("half pitch", static.settings.band_pitch / 2)):
        problem = machine_problem(mesh_at_angle(static, math.radians(10.0) + extra), design, {"A": 20.0})
        s = solver.solve(problem)
        print(f"{base * factor:>9} {label:>10} {flux_linkage(problem, s)[0]:12.6f} "
              f"{arkkio_torque(problem, s):14.5f} {virtual_work_torque(problem, s):13.5f}")
```

- [ ] **Step 2: Run and read**

Run: `.venv\Scripts\python examples\band_pitch_convergence.py`
Expected: a 6-row table; torque and ψ vary less from 2D to 4D than from D to 2D. Paste the table into the task report.

- [ ] **Step 3: Slow test**

`tests/mesh/test_band_pitch_convergence.py`:

```python
"""Refining the band pitch shrinks the change in Arkkio torque (spec §9 M3: band-pitch convergence)."""
import math

import pytest

from conftest import make_8_6
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque
from srmcore.solvers.skfem_reference import SkfemReference


@pytest.mark.slow
def test_arkkio_torque_converges_with_band_divisions():
    machine = make_8_6()
    base = resolve_mesh_settings(machine, MeshSettings(preset="screening")).band_divisions
    torques = []
    for factor in (1, 2, 4):
        design = Design(machine=machine, mesh=MeshSettings(preset="screening", airgap_circumferential_divisions=base * factor))
        problem = machine_problem(mesh_at_angle(build_machine_mesh(design), math.radians(10.0)), design, {"A": 20.0})
        torques.append(arkkio_torque(problem, SkfemReference().solve(problem)))
    assert abs(torques[2] - torques[1]) < abs(torques[1] - torques[0])
```

Run: `.venv\Scripts\python -m pytest tests/mesh/test_band_pitch_convergence.py -m slow -v`. If it fails, report the three torques; do not adjust the assertion.

- [ ] **Step 4: Commit** (after owner approval)

```bash
git add examples/band_pitch_convergence.py tests/mesh/test_band_pitch_convergence.py
git commit -m "test(mesh): band-pitch convergence study on the 8/6 screening mesh"
```

---

### Task 5: TEAM Problem 24 feasibility (time-boxed)

The deliverable is a finding, not shipped library code. Time box: 3 working days. If it is not resolved by then, stop and report what blocks it.

**Files:**
- Create: `tests/team24_fixture.py`, `examples/team24_check.py`, `docs/team24-feasibility.md`

**Interfaces:**
- Consumes: `Magnetostatic2D`, `BandInfo`, `Winding`, `NgsolveAdapter`, `SkfemReference`, `flux_linkage`, `arkkio_torque`, `virtual_work_torque`, `materials` B-H tools (`process_bh` in `srmcore/materials/bh.py`).
- Produces: `team24_problem(current: float) -> Magnetostatic2D` in `tests/team24_fixture.py`, and a written finding.

- [ ] **Step 1: Gather data.** The TEAM 24 problem definition, the measured data (23.1 V step, torque, current, flux) and its B-H table (Table I, 21 points) are described in `docs/reference-machines.md` (row "TEAM Problem 24"). The geometry is Fig. 1–2: stator Ø209.0 mm, rotor Ø102.1 mm, shaft Ø50.8 mm, rotor pole height 12.7 mm, axial length 25.4 mm, two coils of 350 turns, 3.09 Ω total, locked rotor at 22°. Download the TEAM 24 report (link on `https://ngsolve.github.io/TEAM-problems/TEAM-24/team24.html`) and read the NGSolve reference implementation on that page for the geometry and torque convention. Save the numbers you use (with figure/table numbers) at the top of `docs/team24-feasibility.md`.

- [ ] **Step 2: Build the fixture.** In `tests/team24_fixture.py`, mesh the rig with gmsh directly (test code may import gmsh; the import rule covers only `src/`), including an annular air band across the gap so `problem.band` is set (`BandInfo(elements, inner_radius, outer_radius)`). Region kinds must be the existing ones (`stator_iron`, `rotor_iron`, `coil`, `air`). Build the B-H law from Table I with `process_bh`, stacking factor 1 (solid steel). Build a `Winding` with the two coil sides as one circuit. Set the outer boundary Dirichlet.

- [ ] **Step 3: Solve with both adapters** at the final steady-state current of the measured test, and compare the two solvers (must agree to 1e-4 as in Task 3). Then compute torque with Arkkio and virtual work.

- [ ] **Step 4: Compare with measurement.** Static torque at the final current against the measured value (radius 0.268 m force link, so torque = force × 0.268 m), and the current rise by integrating dψ/dt = V − R·i on the locked-rotor ψ(i) map (V = 23.1 V, R = 3.09 Ω, eddy currents neglected, per spec §2.3). The rig has 3D end effects that a 2D model cannot capture (spec lists them in the uncertainty budget). Report the deviation; do not tune the model to hit the measurement.

- [ ] **Step 5: Write `docs/team24-feasibility.md`** with: the inputs used, the solver agreement, torque and current-rise deviations, the NGSolve-reference comparison if that page publishes numbers, what blocked or surprised, and the answer to "is TEAM 24 behaviour reached?". Proposed criterion for the owner to accept or change in Task 6: static torque within 10 % of measured and a current-rise curve that follows the measured shape. This threshold is provisional; the owner sets it.

- [ ] **Step 6: Commit** (after owner approval)

```bash
git add tests/team24_fixture.py examples/team24_check.py docs/team24-feasibility.md
git commit -m "docs: TEAM 24 feasibility check for the 2D magnetostatic engine"
```

---

### Task 6: Evidence summary and go/no-go record

**Files:**
- Modify: `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` (§9 row M3 status, §10 findings, §11 decision), `CLAUDE.md` (current state, commands, solve pipeline, tests)

- [ ] **Step 1: Collect the evidence** into one short table for the owner: cross-solver agreement (Task 3), nodal vs Arkkio (Task 1), band-pitch convergence (Task 4), TEAM 24 result (Task 5), and the per-iteration timing from the M3 spike (NGSolve about 0.40 s assembly + 0.13–0.17 s umfpack solve vs skfem about 0.43 s + 0.22–0.31 s at 43k DOF, no single-thread speed win). Also run the full fast suite and the slow suite one directory at a time.

- [ ] **Step 2: Ask the owner for the decision.** Options: (a) NGSolve accepted as primary (skfem stays as the reference cross-check), (b) skfem stays primary and NGSolve is re-evaluated when 3D/thermal work begins. Do not decide for the owner.

- [ ] **Step 3: Record it.** Add a row to spec §11 with the date, the decision and the reason. Add the band-pitch and TEAM 24 findings to §10 if they leave open items. Update `CLAUDE.md`: current state (M3 done), the NGSolve adapter in "Solve pipeline", the `[ngsolve]` extra in "Commands", and the new test files. Note that speed work (umfpack for skfem, vectorised assembly) is an M4 item that applies to both adapters.

- [ ] **Step 4: Commit** (after owner approval)

```bash
git add docs/superpowers/specs/2026-09-28-srm-core-engine-design.md CLAUDE.md
git commit -m "docs: record the M3 go/no-go decision and findings"
```

---

## Notes and risks

- **Nodal-force accuracy.** A one-layer band is a coarse virtual-work sample. If Task 1 misses 1 % on `screening`, that is a finding to report, not a tolerance to loosen (options for the owner: measure it on `full`, or widen the virtual-displacement layer).
- **`umfpack` availability.** The spike used it on Windows only. CI on Linux is the first check of the Linux wheel.
- **TEAM 24 is not an SRM in `RadialSRMParams`.** No mapping exists (see `docs/reference-machines.md`); the fixture builds its own mesh and problem.
- **Out of scope:** the deferred M2 minors (`ramp_steps=0` crash, iterations counted only for the last attempt, basis cache keyed by array identity, pole-tip group missing from the saturation report), solve speed (M4), maps (M4), FEMM and measured-machine validation (M5).
