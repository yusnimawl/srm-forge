# M4a Operating Point, Phase Order, Speed and L_inc Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the engine a single-point entry (`solve_point`), relabel phases so counter-clockwise motoring reads A→B→C→D, bring a cold `screening` solve to ≤ 4 s, and add the incremental inductance matrix L_inc.

**Architecture:** `maps/point.py` chains `mesh_at_angle → machine_problem → solver.solve → post` and returns a frozen `PointResult`. Speed comes from moving the secant residual out of NGSolve into a numpy scatter in `physics/fem.py` (the profile below shows it is 45 % of a solve), then a measured spike on a current-continuation predictor. L_inc = ∂ψ/∂i comes from one extra linear solve per circuit on the converged tangent, added to both adapters.

**Tech Stack:** numpy, scipy, NGSolve (primary), scikit-fem (reference), pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` §7.1 (L_inc), §7.2 (speed budget), §10 (items "[M4] Operating-point module", "[M2→M4] Phase labelling", "[M2→M4] Solve speed"), §11 (decision log). Handoff: `docs/m4-handoff.md`.

## Decisions from the grilling round (owner-approved 2026-09-29)

- M4 is split into M4a (this plan), M4b (grids, HDF5, worker pool, cache, error policy) and M4c (inverse tables, overlap map, exports, §7.3 checks, fidelity check). Each ships as its own PR. M4a has 5 tasks.
- Speed spike sits inside M4a because it sets the grid sizes.
- Phases are relabelled now, before any map data exists.
- Speed gate: a single cold solve on the `screening` preset, 20 A, θ = 0, must take ≤ 4 s. Amortised cost across a sweep is reported, not gated.
- Task order changed from the summary the owner saw: L_inc (sensitivity solve) is Task 4 and the predictor is Task 5, because the predictor reuses the sensitivity.

## Global Constraints

- Element order 1 (P1) and quadrature order 2 in every adapter (`solvers/settings.py`: `ELEMENT_ORDER`, `QUADRATURE_ORDER`).
- Newton tolerances pinned in `NewtonSettings`: residual and ΔA both below 1e-8; fallback chain damped, then current ramp, then `NONCONVERGED`. An adapter never raises for non-convergence.
- Cross-solver agreement (same mesh, order, quadrature, tolerances, B-H): relative difference ≤ 1e-4 (`tests/solvers/test_cross_solver.py` must stay green).
- `skfem_reference.py`: additive changes only (new method `sensitivity`). No edit to `solve`, `linearize` or the Newton driver; its independence is the cross-check.
- Import rules (`tests/test_import_rules.py`): `maps` may import model, materials, mesh, physics, solvers, post, fields. Only `solvers/` imports `ngsolve`, `netgen`, `skfem`. Only `geometry/` and `mesh/` import `gmsh`.
- SI units everywhere. Frozen dataclasses or Pydantic models across layers; never pass solver objects out of `solvers/`.
- Python >= 3.12, numpy >= 2.0. Test file basenames unique (`tests/` has no `__init__.py`). Fast suite < 10 min; long tests get `@pytest.mark.slow`. No wall-clock assertions in tests.
- Comments explain the code as it is now; no task or plan history in comments.
- Leave the open owner decisions (`self_starting` rule, `MIN_WEB_WIDTH`) unchanged.
- Commit only after the owner approves. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

Failure modes the spec implies but no task would otherwise exercise, most likely first:

1. `solve_point` on a solve that does not converge: returns a `PointResult` with status `NONCONVERGED` and `l_inc = None`, never raises (Tasks 1, 4).
2. Negative angle, angle ≥ 2π, and an unknown circuit name or wrong-length current vector: wrapped angle equals the direct one; `ValueError` naming the circuits (Task 1).
3. Zero current: ψ = 0, torque = 0, 0 iterations, and L_inc still defined (the linear inductance at ν(0)) (Tasks 1, 4).
4. One solver instance reused across different angles (mesh changes) after the speed refactor gives the same answer as a fresh instance (Task 3).
5. Relabelled phases on a 3-phase design (12/8), not only the 8/6 (Task 2).

## Measured baseline (NGSolve, 8/6 `screening`, 42 935 nodes, 20 A, θ = 0, cold)

9 s and 11 Newton iterations (5 A: 9 iterations). Profile of one solve: residual 4.1 s over 28 calls (11 iterations plus 17 line-search halvings), `solve_tangent` 5.0 s over 11 calls of which `Inverse` (umfpack) is 1.7 s, material laws 0.3 s. Mesh build 8.4 s once. Gate: ≤ 4 s.

---

## File Structure

- Create: `src/srmcore/maps/point.py` (`PointResult`, `solve_point`)
- Create: `tests/maps/test_point.py`, `tests/physics/test_p1_kernels.py`, `tests/post/test_incremental_inductance.py`, `tests/maps/test_predictor.py`
- Create: `examples/solve_speed.py` (benchmark; not a test)
- Modify: `src/srmcore/topology/radial.py` (phase order)
- Modify: `src/srmcore/physics/fem.py` (`p1_gradients`, `secant_residual`)
- Modify: `src/srmcore/solvers/ngsolve_adapter.py` (numpy residual; `sensitivity`)
- Modify: `src/srmcore/solvers/skfem_reference.py` (add `sensitivity` only)
- Modify: `src/srmcore/solvers/settings.py` (`SolverAdapter.sensitivity`)
- Modify: `src/srmcore/post/quantities.py` (`incremental_inductance`)
- Modify (Task 5, only if the predictor is kept): `src/srmcore/maps/point.py`
- Modify: `CLAUDE.md`, spec §10/§11, `docs/m4-handoff.md`

---

### Task 1: `solve_point` and `PointResult`

**Files:**
- Create: `src/srmcore/maps/point.py`
- Test: `tests/maps/test_point.py`

**Interfaces:**
- Consumes: `build_machine_mesh(design) -> StaticMesh`, `mesh_at_angle(static, theta) -> MachineMesh`, `machine_problem(mesh, design, currents: Mapping[str, float]) -> Magnetostatic2D`, `SolverAdapter.solve(problem, initial) -> FieldSolution`, `flux_linkage`, `arkkio_torque`, `virtual_work_torque`.
- Produces: `PointResult` and `solve_point(static, design, angle, currents, solver, initial=None, keep_field=False) -> PointResult` (Tasks 4 and 5 extend it).

- [ ] **Step 1: Write the failing tests**

Create `tests/maps/test_point.py`:

```python
"""solve_point: one operating point, the chain every map point repeats (spec §7.2, §10)."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.fields.solution import FieldSolution, SolveStatus
from srmcore.maps.point import PointResult, solve_point
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from srmcore.solvers.settings import NewtonSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


def test_matches_the_manual_chain(static):
    theta, solver = math.radians(10.0), SkfemReference()
    result = solve_point(static, DESIGN, theta, {"A": 5.0}, solver)
    problem = machine_problem(mesh_at_angle(static, theta), DESIGN, {"A": 5.0})
    solution = solver.solve(problem)
    assert isinstance(result, PointResult)
    assert result.circuits == ("A", "B", "C", "D")
    assert np.array_equal(result.currents, [5.0, 0.0, 0.0, 0.0])
    assert result.angle == pytest.approx(theta)
    assert np.allclose(result.psi, flux_linkage(problem, solution), rtol=1e-12, atol=1e-15)
    assert result.torque_arkkio == pytest.approx(arkkio_torque(problem, solution), rel=1e-12)
    assert result.torque_virtual_work == pytest.approx(virtual_work_torque(problem, solution), rel=1e-12)
    assert result.energy == solution.energy and result.coenergy == solution.coenergy
    assert result.status is SolveStatus.OK and result.iterations == solution.iterations
    assert result.field is None


def test_keep_field_returns_the_field(static):
    result = solve_point(static, DESIGN, 0.0, {"A": 5.0}, SkfemReference(), keep_field=True)
    assert isinstance(result.field, FieldSolution)
    assert result.field.a.shape == (len(mesh_at_angle(static, 0.0).nodes),)


def test_zero_current_point(static):
    result = solve_point(static, DESIGN, 0.0, {}, SkfemReference())
    assert result.iterations == 0 and result.status is SolveStatus.OK
    assert np.all(result.psi == 0.0) and result.torque_arkkio == 0.0


def test_angle_wraps_like_mesh_at_angle(static):
    solver = SkfemReference()
    direct = solve_point(static, DESIGN, math.radians(3.0), {"A": 5.0}, solver)
    wrapped = solve_point(static, DESIGN, math.radians(3.0) + 2 * math.pi, {"A": 5.0}, solver)
    negative = solve_point(static, DESIGN, math.radians(3.0) - 2 * math.pi, {"A": 5.0}, solver)
    for other in (wrapped, negative):
        assert other.angle == pytest.approx(direct.angle)
        assert np.allclose(other.psi, direct.psi, rtol=1e-9)


def test_unknown_circuit_is_rejected(static):
    with pytest.raises(ValueError, match="circuits are"):
        solve_point(static, DESIGN, 0.0, {"Z": 1.0}, SkfemReference())


def test_nonconvergence_is_reported_not_raised(static):
    stingy = SkfemReference(NewtonSettings(max_iterations=1, ramp_steps=1))
    result = solve_point(static, DESIGN, 0.0, {"A": 20.0}, stingy)
    assert result.status is SolveStatus.NONCONVERGED
    assert result.load_fraction <= 1.0


def test_ngsolve_agrees_with_skfem(static):
    pytest.importorskip("ngsolve")
    from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
    theta = math.radians(10.0)
    ref = solve_point(static, DESIGN, theta, {"A": 5.0}, SkfemReference())
    ngs = solve_point(static, DESIGN, theta, {"A": 5.0}, NgsolveAdapter())
    assert np.allclose(ngs.psi, ref.psi, rtol=1e-4, atol=1e-4 * np.abs(ref.psi).max())
    scale = max(abs(ref.torque_arkkio), abs(ref.coenergy))
    assert abs(ngs.torque_arkkio - ref.torque_arkkio) <= 1e-4 * scale
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/maps/test_point.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'srmcore.maps.point'`.

- [ ] **Step 3: Implement**

Create `src/srmcore/maps/point.py`:

```python
"""One operating point of a machine: mesh at an angle, solve, post-process (spec §7.2)."""
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ..fields.solution import FieldSolution, SolveStatus
from ..mesh.machine import mesh_at_angle
from ..mesh.static import StaticMesh
from ..model.design import Design
from ..physics.build import machine_problem
from ..post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from ..solvers.settings import SolverAdapter


@dataclass(frozen=True, eq=False)
class PointResult:
    """Everything a map needs from one solve. With status NONCONVERGED the numbers belong to the last
    iterate at `load_fraction` of the requested currents and must not enter a map."""
    angle: float                       # wrapped rotor angle in [0, 2π), rad
    circuits: tuple[str, ...]
    currents: np.ndarray               # A, one per circuit
    psi: np.ndarray                    # flux linkage per circuit, Wb-turns
    torque_arkkio: float               # N·m, positive counter-clockwise
    torque_virtual_work: float         # N·m
    energy: float                      # W, J
    coenergy: float                    # W', J
    status: SolveStatus
    iterations: int
    fallbacks: tuple[str, ...]
    load_fraction: float
    field: FieldSolution | None = None


def solve_point(static: StaticMesh, design: Design, angle: float, currents: Mapping[str, float],
                solver: SolverAdapter, initial: np.ndarray | None = None,
                keep_field: bool = False) -> PointResult:
    """Solve `design` with the rotor at `angle` and the given circuit currents. `initial` is a node
    vector A from a neighbouring point on the same static mesh. The field is kept only on request."""
    mesh = mesh_at_angle(static, angle)
    problem = machine_problem(mesh, design, currents)
    solution = solver.solve(problem, initial=initial)
    return PointResult(
        angle=mesh.rotor_angle, circuits=problem.winding.circuits, currents=problem.currents,
        psi=flux_linkage(problem, solution),
        torque_arkkio=arkkio_torque(problem, solution),
        torque_virtual_work=virtual_work_torque(problem, solution),
        energy=solution.energy, coenergy=solution.coenergy, status=solution.status,
        iterations=solution.iterations, fallbacks=solution.fallbacks, load_fraction=solution.load_fraction,
        field=solution if keep_field else None,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/maps/test_point.py tests/test_import_rules.py -v`
Expected: PASS (the ngsolve test skips when the extra is absent).

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/maps/point.py tests/maps/test_point.py
git commit -m "feat(maps): solve_point returns a PointResult for one angle and current set"
```

---

### Task 2: Relabel phases so counter-clockwise motoring reads A→B→C→D

The geometry does not change. Only the letter given to each stator pole does: with more stator than rotor poles, the next pole to pull the rotor counter-clockwise is the one before it in pole order, so poles are lettered in reverse (`A, D, C, B, …` for 4 phases). Pole polarity stays tied to `k // n_phases`, so every field is unchanged.

**Files:**
- Modify: `src/srmcore/topology/radial.py:181` (`_coil_sides`)
- Modify: `tests/post/test_machine_8_6.py` (`test_phase_sequence_for_counter_clockwise_motoring`), and any test the run shows depends on letters
- Test: `tests/topology/test_coils.py`

**Interfaces:**
- Consumes: `RadialSRMParams.n_stator_poles`, `n_rotor_poles`, `n_phases`.
- Produces: coil-side phase letters. For `Ns > Nr` pole `k` gets phase index `(-k) % n_phases`; otherwise `k % n_phases`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/topology/test_coils.py` (read the file first and reuse its helper for getting coil sides and its imports; the geometry below is what the test pins):

```python
import math

import pytest

from conftest import make_8_6, make_12_8, make_24_16
from srmcore.topology.radial import _coil_sides


@pytest.mark.parametrize("make", [make_8_6, make_12_8, make_24_16])
def test_phases_follow_the_counter_clockwise_motoring_order(make):
    """At rotor angle 0 pole 0 (phase A) is aligned. The phase whose pole leads the rotor pole by the
    smallest positive angle pulls counter-clockwise next, so letters must advance B, C, D in that order."""
    p = make()
    tau_s, tau_r = 2 * math.pi / p.n_stator_poles, 2 * math.pi / p.n_rotor_poles
    phase_of_pole = {s.pole: s.phase for s in _coil_sides(p)}
    lead = {k: (k * tau_s) % tau_r for k in range(p.n_phases)}
    order = sorted(range(p.n_phases), key=lambda k: lead[k] if k else tau_r)   # pole 0 (A) counts as last
    assert [phase_of_pole[k] for k in order] == list(range(1, p.n_phases)) + [0]
```

If `CoilSide` has different attribute names, use the ones in `topology/radial.py` (`CoilSide(name, pole, phase, sign, boundary)`).

Rewrite the existing phase-sequence test in `tests/post/test_machine_8_6.py`:

```python
def test_phase_sequence_for_counter_clockwise_motoring(solve):
    """At θ = 0 (A aligned), B pulls the rotor counter-clockwise and D clockwise, so counter-clockwise
    motoring excites A → B → C → D. The drive side (sub-project #4) relies on this convention."""
    t_b = arkkio_torque(*solve(0, 10.0, phase="B"))
    t_d = arkkio_torque(*solve(0, 10.0, phase="D"))
    assert t_b > 0 > t_d
    assert t_b == pytest.approx(-t_d, rel=0.02)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/topology/test_coils.py tests/post/test_machine_8_6.py::test_phase_sequence_for_counter_clockwise_motoring -v`
Expected: FAIL (the new test sees phases `0,3,2,1`; the 8/6 torque test sees D positive).

- [ ] **Step 3: Implement**

In `src/srmcore/topology/radial.py`, `_coil_sides`, replace the phase line:

```python
    # More stator than rotor poles: the pole that pulls the rotor counter-clockwise next is the one
    # before it in pole order, so lettering runs against the pole order and reads A → B → C → D in motoring.
    direction = -1 if p.n_stator_poles > p.n_rotor_poles else 1
    ...
    for k in range(p.n_stator_poles):
        phase, group = (direction * k) % p.n_phases, k // p.n_phases
```

(Keep the rest of the loop as it is; move the comment and `direction` above the loop.)

- [ ] **Step 4: Fix everything that named a letter**

Run: `python -m pytest -m "not slow" -x -q`
Expected: failures only where a test assumed the old lettering (coil names such as `coil_B1+`, per-phase current maps, `psi[1] == -psi[3]` style checks). Update each to the new mapping (old B ↔ new D, old D ↔ new B; A and C unchanged for 4 phases). Do not loosen a tolerance to make a test pass; if a physical check fails, stop and report.
Then: `python -m pytest -m "not slow" -q` — Expected: all pass.

- [ ] **Step 5: Update the docs that state the old order**

In `CLAUDE.md` ("Solve pipeline" item 4) replace "counter-clockwise motoring excites A → D → C → B" with "counter-clockwise motoring excites A → B → C → D". In the spec §10 delete the "[M2→M4] Phase labelling" item and add a §11 row: date 2026-09-29, "Phases relabelled so counter-clockwise motoring reads A→B→C→D (M4a Task 2); lettering runs against pole order when Ns > Nr", reason "drive-side commutation tables assume alphabetical order".

- [ ] **Step 6: Commit**

```bash
git add -A src tests CLAUDE.md docs
git commit -m "feat(topology): letter phases so counter-clockwise motoring reads A-B-C-D"
```

---

### Task 3: Speed spike part 1: numpy secant residual in the NGSolve adapter

Moves the residual K(ν)·A − f out of NGSolve assembly (0.145 s per call) into a numpy scatter. The tangent stays in NGSolve. The cross-solver test still cross-checks: Newton now converges the numpy residual using the NGSolve tangent, and must land on skfem's answer.

**Files:**
- Modify: `src/srmcore/physics/fem.py`
- Modify: `src/srmcore/solvers/ngsolve_adapter.py` (`_Discretisation`, `_System.residual`)
- Create: `examples/solve_speed.py`
- Test: `tests/physics/test_p1_kernels.py`, existing `tests/solvers/test_cross_solver.py`

**Interfaces:**
- Consumes: `element_flux_density`, `triangle_areas`.
- Produces: `p1_gradients(nodes, triangles) -> (grads (n_el, 3, 2), areas (n_el,))`; `secant_residual(grads, areas, triangles, nu, a) -> (n_nodes,)` = K(ν)·A per unit depth, without the load.

- [ ] **Step 1: Write the failing tests**

Create `tests/physics/test_p1_kernels.py`:

```python
import numpy as np
from scipy.spatial import Delaunay

from srmcore.physics.fem import element_flux_density, p1_gradients, secant_residual


def _mesh():
    rng = np.random.default_rng(0)
    pts = rng.random((40, 2))
    return pts, Delaunay(pts).simplices


def test_gradients_of_a_linear_field_and_agreement_with_flux_density():
    pts, tri = _mesh()
    grads, areas = p1_gradients(pts, tri)
    a = 3.0 * pts[:, 0] - 5.0 * pts[:, 1]
    ga = np.einsum("eik,ei->ek", grads, a[tri])
    assert np.allclose(ga, [3.0, -5.0])
    assert np.allclose(element_flux_density(pts, tri, a), np.column_stack([ga[:, 1], -ga[:, 0]]))
    assert np.all(areas > 0)


def test_secant_residual_equals_the_dense_stiffness_product():
    pts, tri = _mesh()
    rng = np.random.default_rng(1)
    nu, a = rng.random(len(tri)) + 0.5, rng.random(len(pts))
    k = np.zeros((len(pts), len(pts)))
    for e, t in enumerate(tri):
        g, area = p1_gradients(pts, t[None])
        k[np.ix_(t, t)] += nu[e] * area[0] * g[0] @ g[0].T
    grads, areas = p1_gradients(pts, tri)
    assert np.allclose(secant_residual(grads, areas, tri, nu, a), k @ a, rtol=1e-12, atol=1e-13)
```

Add to `tests/solvers/test_cross_solver.py` (Review Focus 4):

```python
def test_reused_adapter_matches_a_fresh_one_after_the_mesh_changes(static):
    reused = NgsolveAdapter()
    for degrees in (10.0, 20.0):
        p = machine_problem(mesh_at_angle(static, math.radians(degrees)), DESIGN, {"A": 5.0})
        fresh = NgsolveAdapter().solve(p)
        again = reused.solve(p)
        assert np.abs(again.a - fresh.a).max() <= 1e-9 * np.abs(fresh.a).max()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/physics/test_p1_kernels.py -v`
Expected: FAIL (`ImportError: cannot import name 'p1_gradients'`).

- [ ] **Step 3: Add the kernels** to `src/srmcore/physics/fem.py`:

```python
def p1_gradients(nodes: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Shape-function gradients (n_elements, 3, 2) and areas (n_elements,) of P1 triangles, either orientation."""
    x, y = nodes[triangles, 0], nodes[triangles, 1]
    det = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0]) - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0])
    gx = np.stack([y[:, 1] - y[:, 2], y[:, 2] - y[:, 0], y[:, 0] - y[:, 1]], axis=1) / det[:, None]
    gy = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], axis=1) / det[:, None]
    return np.stack([gx, gy], axis=2), 0.5 * np.abs(det)


def secant_residual(grads: np.ndarray, areas: np.ndarray, triangles: np.ndarray, nu: np.ndarray,
                    a: np.ndarray) -> np.ndarray:
    """K(ν)·A per unit depth for element-constant ν: Σ_e ν_e·area_e·(∇φ_i · ∇A_e), scattered to the nodes."""
    ga = np.einsum("eik,ei->ek", grads, a[triangles])
    contribution = (nu * areas)[:, None] * np.einsum("eik,ek->ei", grads, ga)
    return np.bincount(triangles.ravel(), weights=contribution.ravel(), minlength=len(a))
```

- [ ] **Step 4: Use it in the adapter.** In `ngsolve_adapter.py`:
  - import `p1_gradients, secant_residual` from `..physics.fem`;
  - in `_Discretisation.__init__` add `self.grads, self.areas = p1_gradients(nodes, triangles)` and delete the `self.secant` BilinearForm (now unused);
  - update the class docstring: "Only the tangent is assembled in NGSolve; the secant residual is `physics.fem.secant_residual`.";
  - replace `_System.residual` with:

```python
    def residual(self, a: np.ndarray, f: np.ndarray):
        _, nu, dnu = self.material(a)
        r = secant_residual(self.disc.grads, self.disc.areas, self.problem.triangles, nu, a)
        return r - f, nu, dnu
```

- [ ] **Step 5: Run the correctness tests**

Run: `python -m pytest tests/physics/test_p1_kernels.py tests/solvers -q -m "not slow"`
Expected: PASS, including the 1e-4 cross-solver checks. If a cross-solver check fails, stop; do not loosen it.

- [ ] **Step 6: Write the benchmark script and measure**

Create `examples/solve_speed.py` (a script, like the other examples; run from the repo root):

```python
"""Time cold and warm solves of the 8/6 on the screening preset with each solver.

Run:  .venv\\Scripts\\python examples\\solve_speed.py [screening|full]
"""
import math
import sys
import time

from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.physics.build import machine_problem
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
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
preset = sys.argv[1] if len(sys.argv) > 1 else "screening"
design = Design(machine=machine, mesh=MeshSettings(preset=preset))
start = time.perf_counter()
static = build_machine_mesh(design)
print(f"mesh build {time.perf_counter() - start:.1f} s")
problem = machine_problem(mesh_at_angle(static, 0.0), design)
print(f"{len(problem.nodes)} nodes")

for solver in (NgsolveAdapter(), SkfemReference()):
    print(f"--- {solver.name}")
    for amps in (20.0, 20.0):     # the first call also builds the discretisation
        start = time.perf_counter()
        s = solver.solve(problem.with_currents([amps, 0, 0, 0]))
        print(f"  cold {amps:4.0f} A  {s.status.value:<16} it={s.iterations:2d}  {time.perf_counter() - start:5.2f} s")
    total_it, start = 0, time.perf_counter()
    a = None
    for amps in (5.0, 10.0, 20.0):
        s = solver.solve(problem.with_currents([amps, 0, 0, 0]), initial=a)
        a, total_it = s.a, total_it + s.iterations
    print(f"  sweep 5-10-20 A (warm start)  it={total_it}  {time.perf_counter() - start:5.2f} s")
```

Run: `python examples\solve_speed.py`
Record the NGSolve second-call cold time, iterations and the sweep line in the plan's baseline section of `docs/m4-handoff.md` (a table: before 9 s / 11 it; after). Expected after: about 5 s. If ≤ 4 s the speed gate is already met; still do Tasks 4 and 5.

- [ ] **Step 7: Commit**

```bash
git add src/srmcore/physics/fem.py src/srmcore/solvers/ngsolve_adapter.py tests/physics/test_p1_kernels.py tests/solvers/test_cross_solver.py examples/solve_speed.py docs/m4-handoff.md
git commit -m "perf(solvers): NGSolve adapter evaluates the secant residual in numpy"
```

---

### Task 4: L_inc = ∂ψ/∂i from the converged tangent

At a converged state `K_T·(dA/di_k) = ∂f/∂i_k`. One factorisation, one back-substitution per circuit. ψ is linear in A, so `L_inc[k, j]` is the flux linkage of the response `dA/di_j`.

**Files:**
- Modify: `src/srmcore/solvers/settings.py` (`SolverAdapter.sensitivity`)
- Modify: `src/srmcore/solvers/ngsolve_adapter.py`, `src/srmcore/solvers/skfem_reference.py` (add `sensitivity`; no other change to skfem)
- Modify: `src/srmcore/post/quantities.py`, `src/srmcore/maps/point.py`
- Test: `tests/post/test_incremental_inductance.py`

**Interfaces:**
- Consumes: converged `FieldSolution.a`, `Winding.matrix`, `Magnetostatic2D.with_currents`.
- Produces:
  - `SolverAdapter.sensitivity(problem, a) -> np.ndarray` shape `(n_nodes, n_circuits)`, zero on Dirichlet nodes.
  - `incremental_inductance(problem, sensitivity) -> np.ndarray` shape `(n_circuits, n_circuits)`, H.
  - `PointResult.l_inc: np.ndarray | None` and `solve_point(..., with_l_inc=False)`. `l_inc` is `None` when `with_l_inc` is False, or when status is `NONCONVERGED` or `load_fraction < 1`.

- [ ] **Step 1: Write the failing tests**

Create `tests/post/test_incremental_inductance.py`:

```python
"""L_inc = ∂ψ/∂i (spec §7.1): finite differences, symmetry, the linear limit, and both adapters."""
import dataclasses
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.point import solve_point
from srmcore.materials.laws import VACUUM, LinearLaw
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import flux_linkage, incremental_inductance
from srmcore.solvers.settings import NewtonSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
THETA = math.radians(10.0)


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


def _l_inc(solver, problem):
    s = solver.solve(problem)
    return incremental_inductance(problem, solver.sensitivity(problem, s.a)), s


def test_linear_machine_l_inc_is_psi_over_i(static):
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {"A": 5.0})
    p = dataclasses.replace(p, laws=tuple(law if law is VACUUM else LinearLaw(1000.0) for law in p.laws))
    l_inc, s = _l_inc(SkfemReference(), p)
    assert l_inc[0, 0] == pytest.approx(flux_linkage(p, s)[0] / 5.0, rel=1e-8)


def test_matches_central_differences_in_the_saturating_range(static):
    solver, base = SkfemReference(), 15.0
    mesh = mesh_at_angle(static, THETA)
    p = machine_problem(mesh, DESIGN, {"A": base})
    l_inc, _ = _l_inc(solver, p)
    h = 0.25
    hi = flux_linkage(p.with_currents([base + h, 0, 0, 0]), solver.solve(p.with_currents([base + h, 0, 0, 0])))
    lo = flux_linkage(p.with_currents([base - h, 0, 0, 0]), solver.solve(p.with_currents([base - h, 0, 0, 0])))
    assert np.allclose(l_inc[:, 0], (hi - lo) / (2 * h), rtol=1e-3, atol=1e-9)


def test_l_inc_is_symmetric_and_positive_definite(static):
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {"A": 15.0})
    l_inc, _ = _l_inc(SkfemReference(), p)
    assert np.allclose(l_inc, l_inc.T, rtol=1e-6, atol=1e-12)
    assert np.all(np.linalg.eigvalsh(l_inc) > 0)


def test_l_inc_at_zero_current_is_defined(static):
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {})
    solver = SkfemReference()
    l_inc = incremental_inductance(p, solver.sensitivity(p, np.zeros(len(p.nodes))))
    assert np.all(np.isfinite(l_inc)) and l_inc[0, 0] > 0


def test_ngsolve_sensitivity_agrees_with_skfem(static):
    pytest.importorskip("ngsolve")
    from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {"A": 15.0})
    ref, _ = _l_inc(SkfemReference(), p)
    ngs, _ = _l_inc(NgsolveAdapter(), p)
    assert np.allclose(ngs, ref, rtol=1e-4, atol=1e-4 * np.abs(ref).max())


def test_solve_point_l_inc_flag(static):
    solver = SkfemReference()
    assert solve_point(static, DESIGN, THETA, {"A": 5.0}, solver).l_inc is None
    result = solve_point(static, DESIGN, THETA, {"A": 5.0}, solver, with_l_inc=True)
    assert result.l_inc.shape == (4, 4)


def test_solve_point_withholds_l_inc_when_not_converged(static):
    stingy = SkfemReference(NewtonSettings(max_iterations=1, ramp_steps=1))
    result = solve_point(static, DESIGN, 0.0, {"A": 20.0}, stingy, with_l_inc=True)
    assert result.l_inc is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/post/test_incremental_inductance.py -v`
Expected: FAIL (`ImportError: cannot import name 'incremental_inductance'`).

- [ ] **Step 3: Implement**

`solvers/settings.py`: add to `SolverAdapter`:

```python
    def sensitivity(self, problem: Magnetostatic2D, a: np.ndarray) -> np.ndarray:
        """dA/di_k = K_T(A)⁻¹·∂f/∂i_k for every circuit k at the converged field `a`: shape
        (n_nodes, n_circuits), zero on the Dirichlet nodes."""
        ...
```

`solvers/skfem_reference.py`, method on `SkfemReference` (additive):

```python
    def sensitivity(self, problem: Magnetostatic2D, a: np.ndarray) -> np.ndarray:
        system = self._bind(problem)
        a = np.asarray(a, float)
        _, nu, dnu = system.residual(a, np.zeros(system.basis.N))
        lu = spla.splu(system.tangent(a, nu, dnu)[system.free][:, system.free].tocsc())
        m = len(problem.winding.circuits)
        out = np.zeros((system.basis.N, m))
        for k in range(m):
            unit = problem.with_currents(np.eye(m)[k])
            rhs = asm(_load, system.basis, j=system._q(unit.current_density()))
            out[system.free, k] = lu.solve(rhs[system.free])
        return out
```

`solvers/ngsolve_adapter.py`, method on `NgsolveAdapter`:

```python
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
```

`post/quantities.py`: split the body of `flux_linkage` into `_linkage(problem, a)` and add:

```python
def _linkage(problem: Magnetostatic2D, a: np.ndarray) -> np.ndarray:
    in_coil = np.flatnonzero(problem.element_coil >= 0)
    tri = problem.triangles[in_coil]
    integral = triangle_areas(problem.nodes, tri) * a[tri].mean(axis=1)
    per_side = np.bincount(problem.element_coil[in_coil], weights=integral,
                           minlength=len(problem.winding.coil_sides))
    return problem.depth * problem.winding.matrix.T @ per_side


def flux_linkage(problem: Magnetostatic2D, solution: FieldSolution) -> np.ndarray:
    """ψ_k = L·Σ_s C_sk·∫_s A dA per circuit, Wb-turns. ∫A dA on a P1 triangle = area × mean nodal A."""
    return _linkage(problem, solution.a)


def incremental_inductance(problem: Magnetostatic2D, sensitivity: np.ndarray) -> np.ndarray:
    """L_inc[k, j] = ∂ψ_k/∂i_j, H. ψ is linear in A, so column j is the flux linkage of the response dA/di_j."""
    return np.column_stack([_linkage(problem, sensitivity[:, j]) for j in range(sensitivity.shape[1])])
```

`maps/point.py`: add `l_inc: np.ndarray | None = None` to `PointResult` (comment: "H; only when requested and the solve converged at full load"), add parameter `with_l_inc: bool = False` to `solve_point`, import `incremental_inductance`, and before the return:

```python
    l_inc = None
    if with_l_inc and solution.status is not SolveStatus.NONCONVERGED and solution.load_fraction == 1.0:
        l_inc = incremental_inductance(problem, solver.sensitivity(problem, solution.a))
```

passing `l_inc=l_inc` into `PointResult(...)`.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/post tests/maps tests/solvers tests/test_import_rules.py -q -m "not slow"`
Expected: PASS. If the finite-difference test misses 1e-3, first check the step h against the 1e-8 Newton tolerance before touching the tolerance.

- [ ] **Step 5: Commit**

```bash
git add -A src tests
git commit -m "feat(post): incremental inductance matrix from the converged tangent"
```

---

### Task 5: Continuation predictor spike, speed verdict, docs

Time-boxed experiment with a keep-or-delete rule. Predictor: given a converged point at currents `i0` and a target `i1`, `a_pred = a0 + S·(i1 − i0)` with `S` from `sensitivity`. Cold start uses `n_sub` Euler sub-steps from zero (a single step from A = 0 overshoots, per the M2 finding).

**Files:**
- Modify: `src/srmcore/maps/point.py` (`euler_initial`)
- Test: `tests/maps/test_predictor.py`
- Modify: `examples/solve_speed.py`, `CLAUDE.md`, spec §10/§11, `docs/m4-handoff.md`

**Interfaces:**
- Consumes: `SolverAdapter.sensitivity`, `Magnetostatic2D.with_currents`.
- Produces: `euler_initial(solver, problem, a0, i0, i1, n_sub=1) -> np.ndarray`: node vector to pass as `initial` for the problem at currents `i1`, marched from `(a0, i0)` in `n_sub` equal steps.

- [ ] **Step 1: Write the failing test** (`tests/maps/test_predictor.py`)

```python
"""Euler current predictor: a first-order estimate of A at a nearby current."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.point import euler_initial
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def setup():
    static = build_machine_mesh(DESIGN)
    p = machine_problem(mesh_at_angle(static, math.radians(10.0)), DESIGN, {"A": 10.0})
    solver = SkfemReference()
    return solver, p, solver.solve(p)


def test_predictor_beats_the_unscaled_previous_solution(setup):
    solver, p, s10 = setup
    target = p.with_currents([11.0, 0, 0, 0])
    exact = solver.solve(target).a
    guess = euler_initial(solver, p, s10.a, np.array([10.0, 0, 0, 0]), np.array([11.0, 0, 0, 0]))
    assert np.linalg.norm(guess - exact) < 0.1 * np.linalg.norm(s10.a - exact)


def test_zero_step_returns_the_start(setup):
    solver, p, s10 = setup
    i = np.array([10.0, 0, 0, 0])
    assert np.allclose(euler_initial(solver, p, s10.a, i, i), s10.a)
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/maps/test_predictor.py -v`; Expected: FAIL (`ImportError: cannot import name 'euler_initial'`).

- [ ] **Step 3: Implement** in `maps/point.py`:

```python
def euler_initial(solver: SolverAdapter, problem: Magnetostatic2D, a0: np.ndarray, i0: np.ndarray,
                  i1: np.ndarray, n_sub: int = 1) -> np.ndarray:
    """Marches A from (a0, i0) to the currents i1 in n_sub explicit Euler steps along the equilibrium
    path, using the tangent sensitivity dA/di at each step's start. `problem` supplies the mesh."""
    a, i0, i1 = np.array(a0, float), np.asarray(i0, float), np.asarray(i1, float)
    for k in range(n_sub):
        di = (i1 - i0) / n_sub
        a = a + solver.sensitivity(problem, a) @ di
        i0 = i0 + di
    return a
```

(add `from ..physics.problem import Magnetostatic2D`). Run the test again; Expected: PASS.

- [ ] **Step 4: Measure**

Extend `examples/solve_speed.py`: after the warm sweep add (a) the same sweep with `initial=euler_initial(solver, problem, a, i_prev, i_next)` in place of `initial=a`, and (b) a cold 20 A solve with `initial=euler_initial(solver, problem, zeros, zeros, i20, n_sub=n)` for `n` in 1, 3, 6, printing iterations and time including the predictor cost. Run it on NGSolve.

- [ ] **Step 5: Apply the keep-or-delete rule**

- **Keep** `euler_initial` and have `examples/solve_speed.py` show it only if it cuts Newton iterations by ≥ 25 % on the warm sweep or the cold start *including* its own cost in seconds.
- **Otherwise delete** `euler_initial`, its test and the script lines, and record the negative result (numbers) in spec §10 under "[M2→M4] Solve speed".

Either way: `sensitivity` and L_inc stay.

- [ ] **Step 6: Speed verdict**

Write the final table (baseline 9 s / 11 it; after Task 3; after Task 5) into `docs/m4-handoff.md`. If a cold `screening` solve at 20 A, θ = 0 is still above 4 s, the gate is missed: do not add more speed work here. Report the numbers and the remaining options (structured air-gap meshing to cut DOF, scipy/umfpack tangent assembly at 0.3 s per iteration, parallel points) to the owner, who decides whether M4b starts with them.

- [ ] **Step 7: Docs**

`CLAUDE.md`: "Current state" (M4a done: `maps/point.py`, phase order, L_inc, speed result), "Solve pipeline" (add `maps/point.py`, `sensitivity`, `incremental_inductance`), "Commands" (`examples\solve_speed.py`). Spec §10: delete "[M4] Operating-point module" and update "Solve speed" with the measured numbers; §11: add a row for the M4a outcome (date, speed result, predictor kept or dropped and why). Update `docs/m4-handoff.md` state line: M4a done, M4b next.

- [ ] **Step 8: Full check and commit**

Run: `python -m pytest -m "not slow" -q` — Expected: all pass, under 10 minutes.

```bash
git add -A src tests examples CLAUDE.md docs
git commit -m "feat(maps): Euler current predictor spike and M4a docs"
```

---

## Self-review

- **Spec coverage:** §10 "[M4] Operating-point module" → Task 1; "Phase labelling" → Task 2; "Solve speed" → Tasks 3, 5 (vectorised assembly partial: residual only; parallel points deferred to M4b, energy line search not taken because the cheap residual removes the halving cost); L_inc with finite-difference verification → Task 4 (§7.1). Deferred M2 minors, per-region stacking factor, air-gap structured meshing: not in M4a, listed in `docs/m4-handoff.md` for M4b.
- **Placeholders:** none; Task 2 Step 1 tells the executor to reuse the existing helper in `tests/topology/test_coils.py` because that file was not read while planning.
- **Types:** `sensitivity(problem, a)` is identical in the protocol and both adapters; `PointResult.l_inc` and `with_l_inc` are defined in Task 4 and used in Task 4 tests only; `euler_initial` uses `sensitivity` from Task 4.
