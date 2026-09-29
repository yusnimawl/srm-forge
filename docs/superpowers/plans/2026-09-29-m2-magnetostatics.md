# M2 — Materials & Nonlinear Magnetostatics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Solve the nonlinear 2D magnetostatic field of a meshed radial SRM at one rotor angle, starting from real B-H data, and report flux linkage per circuit, stored energy and co-energy, Arkkio torque and a saturation report. Everything is checked against analytic solutions.

**Architecture:** `materials/` holds Pydantic material records, a JSON library and the B-H pipeline. The pipeline covers unit checks, the origin point, the stacking factor, a monotone H(B) interpolant and a C¹ polarisation tail, and it produces a `ReluctivityLaw`. `physics/` turns a `MachineMesh` into a solver-neutral `Magnetostatic2D`: nodes, triangles, a law per element, the winding connection matrix, currents, Dirichlet nodes and band info. It reads only the mesh's `region_kind`, `coils` and `outer_edges`. `solvers/skfem_reference.py` assembles with scikit-fem (P1, quadrature order 2) and runs Newton with the consistent Jacobian, a line search and the fallback chain damped → current ramp → `NONCONVERGED`. It returns a plain-numpy `FieldSolution` (`fields/`). `post/` computes ψ per circuit, Arkkio torque (band radii from the mesh) and the saturation report.

**Tech Stack:** Python ≥ 3.12 (local venv 3.14), numpy ≥ 2, scipy (PCHIP/Hermite splines, SuperLU), scikit-fem ≥ 12, pydantic 2, gmsh (unchanged), pytest, hypothesis.

**Spec:** `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md`. This plan covers the M2 row of §9; details are in §3.2, §4.3, §5.1–5.3, §6, §7.1, §8.1–8.2.

**Scope of this plan:** M2 only. The NGSolve adapter, nodal-force torque and TEAM 24 belong to M3. Maps, L_inc, worker pools and speed belong to M4. FEMM fixtures, measured data and the ±2 % Js sensitivity check belong to M5.

## Trial-solve findings (checked before this plan was written)

Before any task was written, the whole milestone was prototyped on the real 8/6 screening mesh (43k nodes). The prototype covered the B-H pipeline on the real FEMM curves, the problem builder, the scikit-fem Newton solver, post-processing and every test in this plan. All 78 new tests passed, and so did the existing fast suite with the Task 1 changes. The code in this plan is that prototype code. After the expert panel's fixes, every touched test file was re-run one file at a time in the prototype and passes (fast and slow tests, including the 8/6 machine tests and the physics, mesh and import-rule suites). The trial and the panel found these defects and facts, and the plan handles each one:

1. **`MachineMesh.region_part` has no `moving_band` entry.** Any `region_part[name]` lookup over all regions raises `KeyError`. Task 1 adds `"moving_band": "band"` and updates the existing test that compared it with `StaticMesh.region_part`.
2. **numpy ≥ 2 rejects `np.cross` on 2-vectors.** Triangle areas use an explicit 2D cross product (`physics/fem.py`).
3. **Co-energy computed as `B·H − w` makes the energy identity a tautology.** The identity W + W′ = Σψ·i is only a real test when ψ comes from ∫J·A. `flux_linkage` integrates A over the coil sides, and the energies come from the material law's own `energy_density` and `coenergy_density`. On the machine the identity holds to about 1e-12 J out of about 16 J.
4. **B-H data needs care in the tail.** A curve typed in from memory had dB/dH < μ0 above 2.1 T, which is unphysical. The library uses FEMM 4.2's own `matlib.dat` (`github.com/cenit/FEMM`, `bin/matlib.dat`). In that data, M-19 polarisation rises to 2.006 T at 2.3 T. The 1010 Steel data is flat at J = 2.0731 T (dB/dH = 1.00003·μ0). The tail law `J = Js − d/(1 + s·(H−Hn)/d)` stays well-conditioned as s → 0, and its inverse and energies are closed-form. The pipeline rejects any table whose polarisation decreases (rule `polarisation`).
5. **The M1 band biased torque by about 1 % of peak.** At angles on the band grid the two band rings coincide, so every band cell is a quad, and the zipper split all of them along the same diagonal. At 10 A, T(aligned) was 0.69 % of |T(10°)| and T(+10°) + T(−10°) was 1.11 %. Mirroring the diagonal flipped the sign of both, which pinned down the cause (Motor-CAD panelist). Task 1 alternates the diagonal from quad to quad, which makes the band mirror-symmetric: the errors become 0.023 % and 0.017 %, with no new nodes.
6. **Linear Arkkio vs dW′/dθ:** the difference was 0.90 % with the old band and is 0.26 % with the symmetric band. The test tolerance is 1 %.
7. **The test files have no `__init__.py`.** Under pytest's default import mode every test basename must be unique, and `tests/geometry/test_build.py` already exists. The new files are named `test_machine_problem.py`, `test_machine_8_6.py` and so on.
8. **Speed (M2 has no speed target; this is recorded for M3/M4).** One Newton iteration at 43k DOF takes 0.65–1.0 s, depending on the machine; about 0.43 s of that is scikit-fem assembly and 0.22–0.31 s is `spsolve`. A cold nonlinear solve takes 5–13 iterations (3–16 s). Starting from the previous current's solution, or from that solution scaled by the current ratio, does not help. See "Notes and risks".
9. **Newton line-search bug (JMAG panelist, confirmed by the EM panelist).** When all halvings failed, the loop accepted an iterate that had not reduced the residual, and computed ΔA from a step half the one actually used. Fix: a stall now ends that Newton attempt as not converged, so the fallback chain takes over, and a residual already below tolerance counts as a decrease, because round-off can stop it from falling further. With the fix, 12 halvings were too few from A = 0 at 200 kA, so `max_halvings` is 20; that case then converges in 8 plain iterations.

## Expert panel rulings (2026-09-29)

The owner asked a panel of five to resolve every open item: a PM, an EM engineer, a power-electronics engineer, a JMAG expert and a Motor-CAD expert. Their reports are in `.superpowers/sdd/2026-09-29-m2-magnetostatics/panel-*.md`. This plan implements these rulings:

- **Accepted by all five (logged in spec §11 by Task 2):** the monotone Hermite fit of H(B); the C¹ tail law; MU0 = 4π×10⁻⁷ exactly; and `outer_air_thickness` in `MeshSettings` with default 0 (A = 0 on the stator OD, as in Motor-CAD). Whether to default to a ring waits for the M5 convergence study.
- **No invented numbers ship looking sourced (Task 2):** `cost_per_kg` is optional and left unset. Every density has a `density_source`. Placeholder values are listed in `provisional_fields`, and their `*_source` strings say PROVISIONAL; a validator and a library test keep the two in sync. The FEMM M-19 provenance now states that its points above about 2.0 T are FEMM's own extrapolation, and that the curve is a validation curve, not traction steel.
- **Mirror-symmetric band (Task 1),** the line-search fix and `max_halvings = 20` (Task 5); see findings 5 and 9.
- **`FieldSolution.load_fraction` (Task 5, power-electronics panelist):** a `NONCONVERGED` result from an early-stopped ramp holds a field for only part of the requested current, and callers must be able to see that.
- **Phase-sequence convention pinned by a test (Task 7):** at θ = 0, D gives positive torque and B negative, so counter-clockwise motoring excites A → D → C → B. Whether to relabel the phases before M4 is an owner item in spec §10.
- **CI budget (PM):** the M2 tests measured 154 s on the PM's machine. The 12/8 winding test and the outer-ring machine solve move to `slow`, and a deep-saturation sweep up to 160 A is added as `slow`. `ci.yml` gets `timeout-minutes: 20` and `--durations=15` (Task 5).
- **Commit before branching:** `CLAUDE.md` and this plan are committed to `main` before `m2-magnetostatics` is created (Execution, step 0).
- **Deferred with owners, recorded in spec §10 by Task 2:** solve speed (M4: vectorised assembly, parallel map points, tangent predictor; not in `skfem_reference`, whose independence makes it the M3 cross-check); an energy (Armijo) line search, which saved only 5–30 % of residual evaluations (M4); per-region stacking-factor overrides (M4); the M5 FEMM fixtures, which must feed FEMM the raw curve plus LamFill so the stacking factor is not applied twice.
- **Rejected:** integrating Arkkio over the whole air-gap annulus (JMAG and EM panelists). It cut the old-band errors 1.5–3×, but the symmetric band cuts them about 50×, so band-only Arkkio stays as the spec states.

## Global Constraints

- Package `srmcore` in `src/srmcore`; tests in `tests/`. `requires-python = ">=3.12"`; local venv is Python 3.14 at `.venv`; CI runs Windows + Linux on Python 3.12 and 3.14 (`.github/workflows/ci.yml` already exists, so no CI task).
- SI units internally everywhere (T, A/m, m, rad, A, J, N·m); conversion only at UI/import edges.
- Allowed internal imports (spec §3.2, enforced by `tests/test_import_rules.py`): `model`: none · `materials`: model · `fields`: model · `topology`: model · `geometry`: model, topology · `mesh`: model, geometry · `physics`: model, materials, mesh · `solvers`: model, materials, physics, fields · `post`: model, materials, physics, fields · `maps`: all of the above · `project`: model, maps.
- Only `solvers/` imports `skfem`, `ngsolve` or `netgen`; only `geometry/` and `mesh/` import `gmsh`.
- Layers exchange plain data: numpy arrays, Pydantic models and frozen dataclasses. Never pass scikit-fem or Gmsh objects across a layer boundary.
- Physics reads regions only through `MachineMesh.region_kind`, `region_part` and `coils` (`CoilInfo`). **It never parses region names.**
- The Dirichlet boundary is whatever `MachineMesh.outer_edges` is (A = 0). With the optional `stator_outer_air` ring, that boundary moves to the ring's outer circle. Physics code does not change.
- Arkkio torque uses the band radii the mesh carries (`MachineMesh.band_inner_radius` and `band_outer_radius`, passed through `BandInfo`).
- Element order P1 and quadrature order 2 are pinned in `solvers/settings.py` (spec §6: identical across adapters).
- Newton converges only when **both** the relative residual < 1e-8 and the relative ΔA < 1e-8. Non-convergence never raises; it returns status `NONCONVERGED`.
- `MU0 = 4e-7·π` exactly (FEMM's value), from `srmcore.model.constants`.
- Validator and material errors raise `InputError` naming the parameter and rule.
- Test file basenames must be unique across `tests/` (there are no `__init__.py` files). Shared test helpers live in `tests/fem_fixtures.py` and `tests/conftest.py` (`pythonpath = ["tests"]`).
- Comments describe the code as it is. Don't write task or plan history into comments.
- The fast suite (`python -m pytest -m "not slow"`) stays under 10 minutes on the GitHub runners, which are slower than local machines. Any test that builds more than one extra mesh or solves the machine more than about five times is marked `@pytest.mark.slow`.
- Every commit message ends with a blank line and then the two attribution trailers the controller gives in its dispatch (`Co-Authored-By: <the model that wrote the commit> <noreply@anthropic.com>` and `Claude-Session: <session URL>`).
- The Windows checkout uses `core.autocrlf=true`. Write files with the Write/Edit tools, not with scripts that force LF, so diffs stay minimal.

## Review Focus

These are the five failure modes most likely to hit a user that no happy-path test exercises, most likely first. Each one has a pinning test in the task named.

1. **A B-H table entered in the wrong units** (mT, gauss, kA/m, Oe) → `InputError` with rule `units`, never a silently wrong curve. Pinned in Task 3 (`test_unit_mixups_are_rejected`).
2. **Fields beyond the last B-H point** (pole tips at 2.4–2.6 T on the 8/6; M19 data ends at 2.3 T) → a C¹ tail with finite, positive ν and converged Newton, not NaN or extrapolation blow-up. Pinned in Task 3 (`test_tail_joins_c1_and_approaches_js`) and Task 6 (the 5 T toroid case).
3. **Newton does not converge** → status `NONCONVERGED` with a finite A and the fallbacks listed, never an exception into the caller. Pinned in Task 5 (`test_nonconvergence_is_a_status_not_an_exception`, `test_fallback_chain_order`).
4. **`RegionMaterials` names a material the library lacks** (for example `"M270"`) → `KeyError` listing the available materials, raised when the problem is built and before any solve. Pinned in Task 4 (`test_unknown_circuit_and_material_are_rejected`).
5. **An initial guess from another mesh or rotor angle passed to `solve`** → a clear `ValueError`, not a shape error deep inside SciPy. Pinned in Task 5 (`test_initial_guess_from_another_mesh_is_rejected`).

## File Structure

```
pyproject.toml                                  + scikit-fem dependency (Task 5)
.github/workflows/ci.yml                        timeout-minutes, --durations (Task 5)
src/srmcore/mesh/band.py                        alternating quad diagonals: mirror-symmetric band (Task 1)
tests/mesh/test_band_symmetry.py                (Task 1)
src/srmcore/model/constants.py                  MU0 (Task 3)
src/srmcore/model/design.py                     + MeshSettings.outer_air_thickness (Task 1)
src/srmcore/model/validator.py                  + outer_air_thickness rules (Task 1)
src/srmcore/geometry/build.py                   + stator_outer_air ring, GeometryModel.outer_boundary_curve (Task 1)
src/srmcore/mesh/static.py                      outer_edges from outer_boundary_curve (Task 1)
src/srmcore/mesh/machine.py                     region_part["moving_band"] = "band" (Task 1)
src/srmcore/materials/schema.py                 Provenance, BHTable, SoftMagneticMaterial, ConductorMaterial, Material (Task 2)
src/srmcore/materials/library.py                load_material(), available_materials() (Task 2)
src/srmcore/materials/data/{M19,steel_1010,copper}.json   built-in library (Task 2)
src/srmcore/materials/bh.py                     check_bh_units(), repair_monotone(), BHCurve, BHReport, process_bh() (Task 3)
src/srmcore/materials/laws.py                   ReluctivityLaw, LinearLaw, VACUUM, law_for_material(), library_law() (Task 3)
src/srmcore/physics/fem.py                      triangle_areas(), element_flux_density() (Task 4)
src/srmcore/physics/winding.py                  Winding, phase_winding() (Task 4)
src/srmcore/physics/problem.py                  BandInfo, Magnetostatic2D (Task 4)
src/srmcore/physics/build.py                    machine_problem() (Task 4)
src/srmcore/physics/energy.py                   field_energies() (Task 5)
src/srmcore/fields/solution.py                  SolveStatus, FieldSolution (Task 5)
src/srmcore/solvers/settings.py                 ELEMENT_ORDER, QUADRATURE_ORDER, NewtonSettings, SolverAdapter (Task 5)
src/srmcore/solvers/skfem_reference.py          SkfemReference (Task 5)
src/srmcore/post/quantities.py                  flux_linkage() (Task 6); arkkio_torque(), SaturationStats, saturation_report() (Task 7)
examples/solve_8_6.py                           runnable demo (Task 7)
tests/mesh/test_outer_air.py, tests/mesh/test_machine.py (edit)        (Task 1)
tests/materials/test_material_library.py                                (Task 2)
tests/materials/test_bh.py                                              (Task 3)
tests/physics/test_winding.py, tests/physics/test_machine_problem.py    (Task 4)
tests/fem_fixtures.py, tests/solvers/test_newton.py, tests/solvers/test_mms.py, tests/test_import_rules.py (edit)   (Task 5)
tests/post/test_toroid.py                                               (Task 6)
tests/post/test_machine_8_6.py                                          (Task 7)
docs/superpowers/specs/2026-09-28-srm-core-engine-design.md  §10 open item (Task 2)
CLAUDE.md                                                     current state + M2 pipeline (Task 7)
```

## Execution (subagent-driven)

- Put the artifacts in `.superpowers/sdd/2026-09-29-m2-magnetostatics/`. That directory is git-ignored through `.superpowers/sdd/.gitignore`. Write `implementer-common.md` and `reviewer-common.md` there first, adapted from the M1 files in `.superpowers/sdd/2026-09-28-m1-geometry-and-mesh/`, with this plan's Global Constraints. Then write `task-N-brief.md`, which is the task text copied verbatim from this plan. Implementers write `task-N-report.md` and reviewers read `review-<base>..<head>.diff`.
- Keep dispatch prompts short: the role, the paths of the common file, the brief and the report, the branch, and the trailers. Everything else goes in files.
- **Models:** Sonnet for every implementer and for small re-reviews after fixes. Opus for the per-task reviews of Tasks 3, 5 and 7 (B-H tail maths, Newton and fallback chain, Arkkio and the machine checks) and for the final whole-branch review. Tasks 1, 2, 4 and 6 are reviewed by Sonnet.
- **Step 0 (controller, before any task):** commit the untracked `CLAUDE.md` and this plan to `main` (`docs: CLAUDE.md and M2 plan`), then create the branch `m2-magnetostatics` from `main`. Task 7 edits `CLAUDE.md`, so the file must already be tracked; otherwise the whole file lands in a feature commit.

---

### Task 1: Mesh inputs for physics — mirror-symmetric band, complete `region_part` and the optional outer air ring

**Review:** Sonnet.

**Files:**
- Modify: `src/srmcore/model/design.py` (`MeshSettings`)
- Modify: `src/srmcore/model/validator.py` (`validate_mesh_settings`)
- Modify: `src/srmcore/geometry/build.py`
- Modify: `src/srmcore/mesh/static.py` (`build_static_mesh`)
- Modify: `src/srmcore/mesh/machine.py` (`mesh_at_angle`)
- Modify: `src/srmcore/mesh/band.py` (`zipper_band`)
- Modify: `tests/mesh/test_machine.py` (`test_machine_mesh_exposes_region_metadata_and_band_radii`)
- Create: `tests/mesh/test_outer_air.py`
- Create: `tests/mesh/test_band_symmetry.py`

**Interfaces:**
- Consumes: M1 `build_outline`, `build_geometry`, `build_static_mesh`, `mesh_at_angle`, `validate_mesh_settings`.
- Produces:
  - `MeshSettings.outer_air_thickness: float = 0.0`. This is the radial thickness in metres of an air ring outside the stator OD; 0 means no ring. Validator rules: `finite`, `non_negative`, and `units` when it is larger than the stator outer radius.
  - `build_geometry(outline, feature_step, outer_air_radius: float | None = None) -> GeometryModel`, and `build_machine_geometry(p, feature_step, outer_air_thickness: float = 0.0)`.
  - `GeometryModel.outer_boundary_curve: int`. This is the ring's outer circle when there is a ring, otherwise it equals `stator_outer_curve`. There is also a new physical group `"outer_boundary"`.
  - Region `stator_outer_air` has kind `"air"`, part `"stator"` and size key `"slot_air"`. It exists only when the ring is on.
  - `StaticMesh.outer_edges` and `MachineMesh.outer_edges` are the edges of `outer_boundary_curve`.
  - `MachineMesh.region_part` has an entry for every region, including `"moving_band": "band"`.
  - `zipper_band` keeps its signature. Where an inner and an outer node coincide in angle, the diagonal of each band quad now alternates, which makes the band mirror-symmetric about every node. This removes a torque bias of about 1 % of peak (trial finding 5), and Task 7's tolerances depend on it.

- [ ] **Step 1: Write the failing tests**

Create `tests/mesh/test_band_symmetry.py`:

```python
import math

import numpy as np

from srmcore.mesh.band import zipper_band


def _labelled(tris: np.ndarray, n: int) -> set[frozenset]:
    label = lambda v: ("in", v) if v < n else ("out", v - n)  # noqa: E731
    return {frozenset(map(label, t)) for t in tris.tolist()}


def test_coinciding_rings_give_a_mirror_symmetric_band():
    """With both rings on the same angles every band cell is a quad. Its diagonal alternates, so the band
    is mirror-symmetric about each node; one fixed diagonal biased torque by ~1 % of peak."""
    n = 24
    angles = np.arange(n) * 2 * math.pi / n
    tris = _labelled(zipper_band(angles, angles.copy()), n)
    assert len(tris) == 2 * n
    mirrored = {frozenset((ring, (-k) % n) for ring, k in t) for t in tris}
    assert mirrored == tris
    rising = sum(frozenset({("in", k), ("out", (k + 1) % n)}) <= t for t in tris for k in range(n))
    falling = sum(frozenset({("in", (k + 1) % n), ("out", k)}) <= t for t in tris for k in range(n))
    assert rising == falling == n  # each diagonal lies in two triangles, n/2 quads per direction
```

Create `tests/mesh/test_outer_air.py`:

```python
import math

import gmsh
import numpy as np
import pytest

from conftest import make_8_6
from srmcore.geometry.build import build_geometry
from srmcore.geometry.session import gmsh_model
from srmcore.mesh import build_machine_mesh, mesh_at_angle, quality_report
from srmcore.model.design import Design, MeshSettings
from srmcore.model.validator import validate_mesh_settings
from srmcore.topology.radial import build_outline

RING = 0.004


def test_geometry_outer_air_ring(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4, outer_air_radius=o.stator_outer_radius + RING)
        area = sum(gmsh.model.occ.getMass(2, t) for t in g.region_surfaces["stator_outer_air"])
        assert area == pytest.approx(math.pi * ((o.stator_outer_radius + RING) ** 2 - o.stator_outer_radius**2), rel=1e-6)
        assert g.region_kind["stator_outer_air"] == "air" and g.region_part["stator_outer_air"] == "stator"
        assert g.region_size_key["stator_outer_air"] == "slot_air"
        assert g.outer_boundary_curve != g.stator_outer_curve
        xmin, *_ = gmsh.model.getBoundingBox(1, g.outer_boundary_curve)
        assert -xmin == pytest.approx(o.stator_outer_radius + RING, rel=1e-4)


def test_without_ring_outer_boundary_is_stator_od(srm_8_6):
    with gmsh_model():
        g = build_geometry(build_outline(srm_8_6), feature_step=1e-4)
        assert "stator_outer_air" not in g.region_surfaces
        assert g.outer_boundary_curve == g.stator_outer_curve


def test_mesh_outer_edges_move_to_the_ring():
    p = make_8_6()
    static = build_machine_mesh(Design(machine=p, mesh=MeshSettings(preset="screening", outer_air_thickness=RING)))
    xy = static.stator.nodes[static.outer_edges.ravel()]
    assert np.allclose(np.hypot(xy[:, 0], xy[:, 1]), p.stator_outer_radius + RING, rtol=1e-9)
    m = mesh_at_angle(static, 0.0)
    assert quality_report(m).triangles_per_region["stator_outer_air"] > 0


def test_outer_air_thickness_validation(srm_8_6):
    errors = lambda t: {(i.parameter, i.rule) for i in validate_mesh_settings(  # noqa: E731
        MeshSettings(outer_air_thickness=t), srm_8_6) if i.severity == "error"}
    assert errors(0.0) == set() and errors(0.005) == set()
    assert ("outer_air_thickness", "non_negative") in errors(-0.001)
    assert ("outer_air_thickness", "units") in errors(5.0)
    assert ("outer_air_thickness", "finite") in errors(float("nan"))
```

In `tests/mesh/test_machine.py`, in `test_machine_mesh_exposes_region_metadata_and_band_radii`, replace

```python
    assert m.region_part == static_8_6.region_part
```

with

```python
    assert m.region_part == {**static_8_6.region_part, "moving_band": "band"}
    assert set(m.region_part) == set(m.region_names)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/mesh/test_band_symmetry.py tests/mesh/test_outer_air.py tests/mesh/test_machine.py -q`
Expected: FAIL. The failures include `assert mirrored == tris` in the band test, `TypeError: build_geometry() got an unexpected keyword argument 'outer_air_radius'`, a pydantic `ValidationError` ("Extra inputs are not permitted") for `outer_air_thickness`, and the `region_part` assertion ("Left contains 1 more item").

- [ ] **Step 3: Implement**

`src/srmcore/mesh/band.py`, in `zipper_band`: directly after the `events = sorted(...)` statement, insert

```python
    # Where an inner and an outer node coincide in angle, the band cell between this tie and the
    # previous one is a quad, and the event order picks its diagonal. Alternating the diagonal from
    # tie to tie (outer-first on even ties, like the closing quad) makes the band mirror-symmetric
    # about every tie; one fixed diagonal biases the torque by ~1 % of peak with a sign set by it.
    ties = 0
    for k in range(len(events) - 1):
        if events[k][0] == events[k + 1][0] and events[k][1] != events[k + 1][1]:
            ties += 1
            if ties % 2 == 0 and events[k][1] == 0:
                events[k], events[k + 1] = events[k + 1], events[k]
```

The first tie sits one pitch after the start node, so odd ties keep the inner-first order and even ties go outer-first. That matches the closing quad, whose diagonal runs from the last inner node to the first outer node, and the band always has an even number of divisions (a multiple of lcm(Ns, 2Nr)).

`src/srmcore/model/design.py`: in `MeshSettings`, after `max_aspect_ratio: float = 12.0`, add

```python
    # Radial thickness of an air ring outside the stator OD (spec §4.3); 0 = none. A = 0 then sits on the
    # ring's outer circle instead of the stator OD, which admits yoke-saturation leakage flux.
    outer_air_thickness: float = 0.0
```

`src/srmcore/model/validator.py`, in `validate_mesh_settings`: change the finiteness loop header to

```python
    for name in ("min_angle_deg", "band_min_angle_deg", "max_aspect_ratio", "outer_air_thickness"):
```

and, after the `max_aspect_ratio` range check and just before `return issues`, add

```python
    if s.outer_air_thickness < 0:
        issues.append(_err("outer_air_thickness", "non_negative", "must be >= 0 (0 = no outer air ring)"))
    elif s.outer_air_thickness > p.stator_outer_radius:
        issues.append(_err("outer_air_thickness", "units",
                           f"{s.outer_air_thickness} m is larger than the stator outer radius; lengths are in metres"))
```

`src/srmcore/geometry/build.py`. This is the full resulting file; the changed parts are the `outer_boundary_curve` field, `_size_key`, the `build_geometry` signature, the ring creation, the `named` list, the `outer_boundary` lookup and physical group, the constructor call and `build_machine_geometry`:

```python
"""Outline -> Gmsh OCC surfaces with named regions. Call inside geometry.session.gmsh_model()."""
from dataclasses import dataclass

import gmsh
import numpy as np

from ..model.design import RadialSRMParams
from ..model.regions import CoilInfo
from ..topology.primitives import Line, Point, Segment, sample_segment
from ..topology.radial import RadialOutline, build_outline

STATOR_REGIONS = ("stator_iron", "slot_air", "airgap_stator")
ROTOR_REGIONS = ("rotor_iron", "shaft", "airgap_rotor", "rotor_slot_air")


@dataclass(frozen=True)
class GeometryModel:
    region_surfaces: dict[str, tuple[int, ...]]
    region_part: dict[str, str]
    region_size_key: dict[str, str]
    region_kind: dict[str, str]
    coils: dict[str, CoilInfo]
    stator_outer_curve: int
    outer_boundary_curve: int
    band_outer_curve: int
    band_inner_curve: int
    refinement_points: dict[str, np.ndarray]


class _Points:
    def __init__(self) -> None:
        self._tags: dict[tuple[float, float], int] = {}

    def get(self, q: Point) -> int:
        key = (round(q[0], 12), round(q[1], 12))
        if key not in self._tags:
            self._tags[key] = gmsh.model.occ.addPoint(q[0], q[1], 0.0)
        return self._tags[key]


def _curves(segments: tuple[Segment, ...], points: _Points, centres: list[int]) -> list[int]:
    occ = gmsh.model.occ
    curves = []
    for s in segments:
        a, b = points.get(s.start), points.get(s.end)
        if isinstance(s, Line):
            curves.append(occ.addLine(a, b))
        else:
            c = occ.addPoint(s.center[0], s.center[1], 0.0)
            centres.append(c)
            curves.append(occ.addCircleArc(a, c, b))
    return curves


def _full_circle_on_boundary(surfaces: tuple[int, ...], radius: float, tol: float) -> int:
    boundary = gmsh.model.getBoundary([(2, s) for s in surfaces], combined=False, oriented=False)
    for _, tag in boundary:
        xmin, ymin, _, xmax, ymax, _ = gmsh.model.getBoundingBox(1, abs(tag))
        if all(abs(v - w) < tol for v, w in ((xmax, radius), (xmin, -radius), (ymax, radius), (ymin, -radius))):
            return abs(tag)
    raise RuntimeError(f"no full circle of radius {radius} on the boundary")


def _size_key(region: str) -> str:
    if region.startswith("coil_"):
        return "coil"
    if region.startswith("airgap_"):
        return "airgap"
    if region in ("rotor_slot_air", "stator_outer_air"):
        return "slot_air"
    return region


def _region_kind(region: str) -> str:
    """The material role for a region name (spec §6): stator iron, rotor iron, shaft, coil, or air.

    slot_air, rotor_slot_air and both airgap_* layers are all "air".
    """
    if region.startswith("coil_"):
        return "coil"
    if region in ("stator_iron", "rotor_iron", "shaft"):
        return region
    return "air"


def _disk(radius: float) -> int:
    """A plane disk of the given radius, bounded by a true Circle curve.

    occ.addDisk's boundary is type "Ellipse" (an OCC quirk: equal-axis conic,
    not a Circle) even before any boolean op, and that quirk survives cut/fragment.
    Building the disk from occ.addCircle instead keeps the boundary a real Circle,
    which later boolean results (and getType/getBoundingBox checks) rely on.
    """
    occ = gmsh.model.occ
    loop = occ.addCurveLoop([occ.addCircle(0, 0, 0, radius)])
    return occ.addPlaneSurface([loop])


def build_geometry(outline: RadialOutline, feature_step: float,
                   outer_air_radius: float | None = None) -> GeometryModel:
    occ = gmsh.model.occ
    points = _Points()
    centres: list[int] = []

    # stator part
    outer_loop = occ.addCurveLoop([occ.addCircle(0, 0, 0, outline.stator_outer_radius)])
    bore_curves = _curves(outline.stator_inner_boundary, points, centres)
    stator_iron = occ.addPlaneSurface([outer_loop, occ.addCurveLoop(bore_curves)])
    inside_bore = occ.addPlaneSurface([occ.addCurveLoop(bore_curves)])
    coils = [(c.name, occ.addPlaneSurface([occ.addCurveLoop(_curves(c.boundary, points, centres))]))
             for c in outline.coil_sides]
    bore_disk = _disk(outline.bore_radius)
    band_out_disk = _disk(outline.band_outer_radius)
    slot_air, _ = occ.cut([(2, inside_bore)], [(2, bore_disk)] + [(2, t) for _, t in coils],
                          removeObject=True, removeTool=False)
    gap_stator, _ = occ.cut([(2, bore_disk)], [(2, band_out_disk)])
    outer_air = []
    if outer_air_radius is not None:
        outer_air, _ = occ.cut([(2, _disk(outer_air_radius))], [(2, _disk(outline.stator_outer_radius))])

    # rotor part
    rotor_area = occ.addPlaneSurface([occ.addCurveLoop(_curves(outline.rotor_outer_boundary, points, centres))])
    shaft = _disk(outline.shaft_radius)
    band_in_disk = _disk(outline.band_inner_radius)
    rotor_od_disk = _disk(outline.rotor_outer_radius)
    # airgap_rotor is just the thin physical gap between the rotor OD and the band; the interpolar
    # air down to the star-shaped rotor outline is its own region (rotor_slot_air), so it doesn't
    # inherit the airgap's very fine size class.
    airgap_rotor, _ = occ.cut([(2, band_in_disk)], [(2, rotor_od_disk)], removeObject=True, removeTool=False)
    rotor_slot_air, _ = occ.cut([(2, rotor_od_disk)], [(2, rotor_area)], removeObject=True, removeTool=False)
    rotor_iron, _ = occ.cut([(2, rotor_area)], [(2, shaft)], removeObject=True, removeTool=False)

    occ.remove([(0, c) for c in centres])

    named: list[tuple[str, list[tuple[int, int]]]] = (
        [("stator_iron", [(2, stator_iron)]), ("slot_air", slot_air), ("airgap_stator", gap_stator)]
        + ([("stator_outer_air", outer_air)] if outer_air else [])
        + [(name, [(2, tag)]) for name, tag in coils]
        + [("rotor_iron", rotor_iron), ("shaft", [(2, shaft)]),
           ("airgap_rotor", airgap_rotor), ("rotor_slot_air", rotor_slot_air)]
    )
    objects = [dt for _, dts in named for dt in dts]
    _, out_map = occ.fragment(objects, [])
    occ.synchronize()

    region_surfaces: dict[str, tuple[int, ...]] = {}
    index = 0
    for name, dts in named:
        tags: list[int] = []
        for _ in dts:
            tags.extend(t for d, t in out_map[index] if d == 2)
            index += 1
        region_surfaces[name] = tuple(sorted(set(tags)))
    all_tags = [t for tags in region_surfaces.values() for t in tags]
    if len(all_tags) != len(set(all_tags)):
        raise RuntimeError("a surface was assigned to two regions")

    region_part = {n: ("rotor" if n in ROTOR_REGIONS else "stator") for n in region_surfaces}
    tol = (outline.band_outer_radius - outline.band_inner_radius) / 4
    stator_outer = _full_circle_on_boundary(region_surfaces["stator_iron"], outline.stator_outer_radius, tol)
    outer_boundary = (stator_outer if outer_air_radius is None
                      else _full_circle_on_boundary(region_surfaces["stator_outer_air"], outer_air_radius, tol))
    band_outer = _full_circle_on_boundary(region_surfaces["airgap_stator"], outline.band_outer_radius, tol)
    band_inner = _full_circle_on_boundary(region_surfaces["airgap_rotor"], outline.band_inner_radius, tol)

    for name, tags in region_surfaces.items():
        gmsh.model.addPhysicalGroup(2, list(tags), name=name)
    gmsh.model.addPhysicalGroup(1, [stator_outer], name="stator_outer")
    gmsh.model.addPhysicalGroup(1, [outer_boundary], name="outer_boundary")
    gmsh.model.addPhysicalGroup(1, [band_outer], name="band_outer")
    gmsh.model.addPhysicalGroup(1, [band_inner], name="band_inner")

    refinement_points = {}
    for tag, features in outline.refinement_features.items():
        pts: list[Point] = []
        for f in features:
            pts.extend(sample_segment(f, feature_step) if not isinstance(f, tuple) else [f])
        refinement_points[tag] = np.asarray(pts, dtype=float).reshape(-1, 2)

    coils = {c.name: CoilInfo(pole=c.pole, phase=chr(ord("A") + c.phase), sign=c.sign)
             for c in outline.coil_sides}

    return GeometryModel(
        region_surfaces=region_surfaces, region_part=region_part,
        region_size_key={n: _size_key(n) for n in region_surfaces},
        region_kind={n: _region_kind(n) for n in region_surfaces},
        coils=coils,
        stator_outer_curve=stator_outer, outer_boundary_curve=outer_boundary,
        band_outer_curve=band_outer, band_inner_curve=band_inner,
        refinement_points=refinement_points,
    )


def build_machine_geometry(p: RadialSRMParams, feature_step: float,
                           outer_air_thickness: float = 0.0) -> GeometryModel:
    outer_air_radius = p.stator_outer_radius + outer_air_thickness if outer_air_thickness > 0 else None
    return build_geometry(build_outline(p), feature_step, outer_air_radius)
```

`src/srmcore/mesh/static.py`, in `build_static_mesh`: replace

```python
        geom = build_machine_geometry(p, feature_step=resolved.gap_size)
```

with

```python
        geom = build_machine_geometry(p, feature_step=resolved.gap_size,
                                      outer_air_thickness=design.mesh.outer_air_thickness)
```

and replace

```python
        outer_edges = _edges(geom.stator_outer_curve, stator_used)
```

with

```python
        outer_edges = _edges(geom.outer_boundary_curve, stator_used)
```

`src/srmcore/mesh/machine.py`, in `mesh_at_angle`: replace

```python
    region_kind = dict(static.region_kind)
    region_kind["moving_band"] = "air"
    return MachineMesh(
        nodes=nodes, triangles=triangles, region_ids=region_ids,
        region_names=static.region_names + ("moving_band",),
        region_part=dict(static.region_part), region_kind=region_kind, coils=dict(static.coils),
```

with

```python
    region_kind = dict(static.region_kind)
    region_kind["moving_band"] = "air"
    region_part = dict(static.region_part)
    region_part["moving_band"] = "band"
    return MachineMesh(
        nodes=nodes, triangles=triangles, region_ids=region_ids,
        region_names=static.region_names + ("moving_band",),
        region_part=region_part, region_kind=region_kind, coils=dict(static.coils),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/mesh/test_outer_air.py tests/mesh/test_machine.py tests/geometry tests/model -q`
Expected: PASS.
Then run: `.venv\Scripts\python -m pytest -m "not slow" -q`
Expected: all pass (about 150 tests, about 75 s).

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/model/design.py src/srmcore/model/validator.py src/srmcore/geometry/build.py src/srmcore/mesh/static.py src/srmcore/mesh/machine.py src/srmcore/mesh/band.py tests/mesh/test_machine.py tests/mesh/test_outer_air.py tests/mesh/test_band_symmetry.py
git commit -m "feat(mesh): mirror-symmetric band, optional stator_outer_air ring, region_part covers moving_band" -m "<trailers>"
```

---

### Task 2: Material schema and built-in library

**Review:** Sonnet.

**Files:**
- Create: `src/srmcore/materials/schema.py`
- Create: `src/srmcore/materials/library.py`
- Create: `src/srmcore/materials/data/M19.json`, `src/srmcore/materials/data/steel_1010.json`, `src/srmcore/materials/data/copper.json`
- Create: `tests/materials/test_material_library.py`
- Modify: `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` (§10)

**Interfaces:**
- Consumes: nothing internal (`materials` may import only `model`).
- Produces:
  - `Provenance`, `BHTable(h: tuple[float, ...], b: tuple[float, ...], temperature_c: float = 20.0)`. At least 3 paired points; this holds the bare steel, before the stacking factor is applied.
  - A shared base `_Sourced` holds `density` and `density_source` (both required), `cost_per_kg: float | None = None`, `cost_source: str | None = None` and `provisional_fields: tuple[str, ...] = ()`. Its validator requires every field listed in `provisional_fields` to have a `<field>_source` containing `PROVISIONAL`.
  - `SoftMagneticMaterial(_Sourced)` (`kind="soft_magnetic"`): `name`, `grade`, `variant`, `parent_grade`, `thickness`, `supplier`, `provenance`, `confidence: "A"|"B"|"C"`, `bh: BHTable`, `stacking_factor` (required, 0 < k ≤ 1, never defaulted per spec §5.1), `stacking_factor_source`, `saturation_polarisation` (T) and `saturation_polarisation_source`.
  - `ConductorMaterial(_Sourced)` (`kind="conductor"`): `name`, `provenance`, `resistivity` (Ω·m at `reference_temperature_c`), `temperature_coefficient`, `insulation_class`, `max_temperature_c`, and `resistivity_at(temperature_c) -> float`.
  - `Material`, a discriminated union on `kind`.
  - `load_material(name: str) -> SoftMagneticMaterial | ConductorMaterial`. It raises `KeyError` listing the available names, and `ValueError` if the file's `name` differs from its file name. Also `available_materials() -> tuple[str, ...]`.

The B-H tables are FEMM 4.2 `matlib.dat` blocks `"M-19 Steel"` (47 points) and `"1010 Steel"` (38 points), copied digit for digit. Source: `gh api repos/cenit/FEMM/contents/bin/matlib.dat -H "Accept: application/vnd.github.raw"`. M19's `stacking_factor` 0.98 is FEMM's `LamFill` for that block. The copper values are from IEC 60028. No costs ship: `cost_per_kg` stays unset until there are supplier quotes. The Js and density values of M19 and steel_1010 are typical handbook or datasheet values that have not been checked against the documents yet, so they are listed in `provisional_fields`. Step 5 records them, and the panel's deferred items, as spec open items.

- [ ] **Step 1: Write the failing tests**

Create `tests/materials/test_material_library.py`:

```python
import pytest
from pydantic import ValidationError

from srmcore.materials.library import available_materials, load_material
from srmcore.materials.schema import BHTable, ConductorMaterial, SoftMagneticMaterial
from srmcore.model.design import RegionMaterials


def test_library_covers_default_region_materials():
    defaults = RegionMaterials()
    for name in (defaults.stator, defaults.rotor, defaults.shaft, defaults.coil):
        assert name in available_materials()


def test_m19_record():
    m = load_material("M19")
    assert isinstance(m, SoftMagneticMaterial)
    assert m.confidence == "C"
    assert "FEMM" in m.provenance.source
    assert len(m.bh.h) == len(m.bh.b) == 47
    assert m.bh.b[-1] == pytest.approx(2.3) and m.bh.h[-1] == pytest.approx(234024.751347)
    assert m.stacking_factor == 0.98


def test_steel_1010_and_copper_records():
    s = load_material("steel_1010")
    assert isinstance(s, SoftMagneticMaterial) and len(s.bh.h) == 38 and s.stacking_factor == 1.0
    cu = load_material("copper")
    assert isinstance(cu, ConductorMaterial)
    assert cu.resistivity == pytest.approx(1.7241e-8)
    assert cu.resistivity_at(120.0) == pytest.approx(1.7241e-8 * (1 + 0.00393 * 100))


def test_unknown_material_lists_available():
    with pytest.raises(KeyError, match="M19"):
        load_material("M270")


def test_bh_table_rejects_unpaired_points():
    with pytest.raises(ValidationError):
        BHTable(h=(0.0, 1.0, 2.0), b=(0.0, 1.0))


@pytest.mark.parametrize("name", available_materials())
def test_provisional_fields_match_provisional_sources(name):
    """Nothing invented ships looking sourced: a *_source says PROVISIONAL exactly when its field is listed."""
    m = load_material(name)
    marked = {k[: -len("_source")] for k, v in m.model_dump().items()
              if k.endswith("_source") and isinstance(v, str) and "PROVISIONAL" in v}
    assert marked == set(m.provisional_fields)
    assert m.cost_per_kg is None                        # no supplier quotes yet


def test_provisional_field_without_provisional_source_is_rejected():
    data = load_material("copper").model_dump()
    data["provisional_fields"] = ("density",)
    with pytest.raises(ValidationError, match="PROVISIONAL"):
        ConductorMaterial.model_validate(data)


def test_stacking_factor_is_required():
    data = load_material("M19").model_dump()
    del data["stacking_factor"]
    with pytest.raises(ValidationError):
        SoftMagneticMaterial.model_validate(data)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/materials/test_material_library.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'srmcore.materials.library'`.

- [ ] **Step 3: Implement**

`src/srmcore/materials/schema.py`:

```python
"""Material records (spec §5.1). SI units: B in T, H in A/m, lengths in m, density in kg/m³,
resistivity in Ω·m, temperatures in °C."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Provenance(_Frozen):
    source: str
    page: str | None = None
    date: str | None = None
    method: str | None = None
    temperature_c: float | None = None
    annealed: bool | None = None
    anneal_recipe: str | None = None
    typical: bool | None = None


class BHTable(_Frozen):
    """Measured single-valued B-H points of the bare steel (no stacking factor applied)."""
    h: tuple[float, ...]
    b: tuple[float, ...]
    temperature_c: float = 20.0

    @model_validator(mode="after")
    def _paired(self) -> "BHTable":
        if len(self.h) != len(self.b):
            raise ValueError(f"h has {len(self.h)} points but b has {len(self.b)}")
        if len(self.h) < 3:
            raise ValueError("a B-H table needs at least 3 points")
        return self


class _Sourced(_Frozen):
    """Every numeric property carries a *_source string; placeholders are listed and say PROVISIONAL."""
    density: float = Field(gt=0)
    density_source: str
    # Unknown until a supplier quote exists; spec §5.1 needs it for the cost objective (sub-project #6).
    cost_per_kg: float | None = Field(default=None, ge=0)
    cost_source: str | None = None
    provisional_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _provisional_sources(self) -> "_Sourced":
        for field in self.provisional_fields:
            source = getattr(self, f"{field}_source", None)
            if source is None or "PROVISIONAL" not in source:
                raise ValueError(f"provisional field {field!r} needs a {field}_source containing 'PROVISIONAL'")
        return self


class SoftMagneticMaterial(_Sourced):
    kind: Literal["soft_magnetic"] = "soft_magnetic"
    name: str
    grade: str
    variant: str
    parent_grade: str | None = None
    thickness: float | None = Field(default=None, gt=0)
    supplier: str | None = None
    provenance: Provenance
    confidence: Literal["A", "B", "C"]
    bh: BHTable
    stacking_factor: float = Field(gt=0, le=1)
    stacking_factor_source: str
    saturation_polarisation: float = Field(gt=0)
    saturation_polarisation_source: str


class ConductorMaterial(_Sourced):
    kind: Literal["conductor"] = "conductor"
    name: str
    provenance: Provenance
    resistivity: float = Field(gt=0)
    reference_temperature_c: float = 20.0
    temperature_coefficient: float
    insulation_class: str | None = None
    max_temperature_c: float | None = None

    def resistivity_at(self, temperature_c: float) -> float:
        return self.resistivity * (1 + self.temperature_coefficient * (temperature_c - self.reference_temperature_c))


Material = Annotated[SoftMagneticMaterial | ConductorMaterial, Field(discriminator="kind")]
```

`src/srmcore/materials/library.py`:

```python
"""The built-in material library: one JSON file per material variant in materials/data/."""
from importlib import resources

from pydantic import TypeAdapter

from .schema import ConductorMaterial, Material, SoftMagneticMaterial

_ADAPTER: TypeAdapter[Material] = TypeAdapter(Material)


def _data_dir():
    return resources.files(__package__) / "data"


def available_materials() -> tuple[str, ...]:
    return tuple(sorted(p.name[:-5] for p in _data_dir().iterdir() if p.name.endswith(".json")))


def load_material(name: str) -> SoftMagneticMaterial | ConductorMaterial:
    path = _data_dir() / f"{name}.json"
    if not path.is_file():
        raise KeyError(f"unknown material {name!r}; available: {', '.join(available_materials())}")
    material = _ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    if material.name != name:
        raise ValueError(f"{name}.json declares name {material.name!r}")
    return material
```

`src/srmcore/materials/data/M19.json`:

```json
{
  "kind": "soft_magnetic",
  "name": "M19",
  "grade": "M19",
  "variant": "FEMM library curve",
  "thickness": 0.000635,
  "provenance": {
    "source": "FEMM 4.2 material library matlib.dat (github.com/cenit/FEMM, bin/matlib.dat), block \"M-19 Steel\" (47 BH points; d_lam 0.635 mm). Typical catalogue curve; points above about 2.0 T are FEMM's own extrapolation, not measurements. Validation curve, not representative of EV traction steel.",
    "typical": true
  },
  "confidence": "C",
  "bh": {
    "h": [0.0, 15.120714, 22.718292, 27.842733, 31.871434, 35.365044, 38.600588, 41.736202, 44.873979, 48.087807, 51.437236, 54.975221, 58.752993, 62.823644, 67.245285, 72.084406, 77.4201, 83.350021, 89.999612, 97.537353, 106.201406, 116.348464, 128.547329, 143.765431, 163.754169, 191.868158, 234.833507, 306.509769, 435.255202, 674.911968, 1108.325569, 1813.085468, 2801.217421, 4053.653117, 5591.10689, 7448.318413, 9708.81567, 12486.931615, 16041.483644, 21249.420624, 31313.495878, 53589.446877, 88477.484601, 124329.41054, 159968.5693, 197751.604272, 234024.751347],
    "b": [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.45, 1.5, 1.55, 1.6, 1.65, 1.7, 1.75, 1.8, 1.85, 1.9, 1.95, 2.0, 2.05, 2.1, 2.15, 2.2, 2.25, 2.3]
  },
  "stacking_factor": 0.98,
  "stacking_factor_source": "FEMM matlib \"M-19 Steel\" LamFill",
  "saturation_polarisation": 2.03,
  "saturation_polarisation_source": "PROVISIONAL: typical room-temperature value for Fe-3%Si non-oriented steel (Bozorth, Ferromagnetism, 1951); replace with the supplier value (spec §10)",
  "density": 7650.0,
  "density_source": "PROVISIONAL: typical M19 value from AK Steel (Cleveland-Cliffs) M-19 product data, not yet checked against the datasheet (spec §10)",
  "provisional_fields": ["saturation_polarisation", "density"]
}
```

`src/srmcore/materials/data/steel_1010.json`:

```json
{
  "kind": "soft_magnetic",
  "name": "steel_1010",
  "grade": "1010",
  "variant": "FEMM library curve",
  "provenance": {
    "source": "FEMM 4.2 material library matlib.dat (github.com/cenit/FEMM, bin/matlib.dat), block \"1010 Steel\" (38 BH points)",
    "typical": true
  },
  "confidence": "C",
  "bh": {
    "h": [0.0, 79.577472, 100.182101, 126.121793, 158.77793, 199.889571, 251.646061, 316.80362, 398.832128, 502.099901, 632.106325, 795.774715, 1001.821011, 1261.217929, 1587.779301, 1998.89571, 2516.460605, 3168.036204, 3988.321282, 5020.999013, 6321.06325, 7957.747155, 10018.210114, 12612.179293, 15877.79301, 19988.957103, 25164.606052, 31680.362037, 39883.212823, 50209.990127, 63210.632497, 79577.471546, 100182.101136, 126121.792926, 158777.930096, 199889.57103, 251646.060522, 316803.62037],
    "b": [0.0, 0.211862, 0.265665, 0.332377, 0.414377, 0.513811, 0.631899, 0.767784, 0.917018, 1.070353, 1.214255, 1.334637, 1.422981, 1.480634, 1.517214, 1.544515, 1.571296, 1.602049, 1.638404, 1.68049, 1.727311, 1.776659, 1.825401, 1.870557, 1.910809, 1.947222, 1.982328, 2.018252, 2.055398, 2.092545, 2.128095, 2.161612, 2.194644, 2.230339, 2.272386, 2.324282, 2.389356, 2.471238]
  },
  "stacking_factor": 1.0,
  "stacking_factor_source": "solid (not laminated) shaft steel",
  "saturation_polarisation": 2.1,
  "saturation_polarisation_source": "PROVISIONAL: low-carbon steel, somewhat below pure iron's 2.15 T (Bozorth, Ferromagnetism, 1951); the FEMM tail is flat at J = 2.073 T so the value barely matters (spec §10)",
  "density": 7870.0,
  "density_source": "PROVISIONAL: typical carbon-steel value (ASM Handbook), not yet checked (spec §10)",
  "provisional_fields": ["saturation_polarisation", "density"]
}
```

`src/srmcore/materials/data/copper.json`:

```json
{
  "kind": "conductor",
  "name": "copper",
  "provenance": {
    "source": "IEC 60028 International Annealed Copper Standard",
    "typical": true
  },
  "resistivity": 1.7241e-08,
  "reference_temperature_c": 20.0,
  "temperature_coefficient": 0.00393,
  "density": 8890.0,
  "density_source": "IEC 60028 International Annealed Copper Standard (8890 kg/m3)"
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/materials/test_material_library.py tests/test_import_rules.py -q`
Expected: PASS.

- [ ] **Step 5: Record the panel's rulings and the open items in the spec**

In `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md`, make three edits.

§5.2 step 4: replace "Fit a monotone PCHIP to B(H); derive reluctivity ν for Newton." with

```markdown
4. Fit a monotone cubic Hermite interpolant to H(B) through the stacked points (PCHIP knot derivatives; the end derivative equals the last secant); ν = H/B for Newton.
```

§5.2 step 6: replace "with a fitted law (e.g. `J = Js − a/H`) joined smoothly (C¹) to the data" with

```markdown
with the law `J = Js − d/(1 + s·(H − Hn)/d)`, d = Js − Jn and s the data's end slope of J, which joins the data C¹ and stays well-conditioned as s → 0
```

§10: append these bullets after the `[M1→M5]` minimum-web item:

```markdown
- **[M2→M5] Provisional material data in `src/srmcore/materials/data/`.** The M19 and steel_1010 B-H tables are FEMM 4.2 library curves (confidence C; FEMM's M-19 points above about 2.0 T are its own extrapolation). Their Js (M19 2.03 T, steel_1010 2.10 T) and densities (7650 and 7870 kg/m³) are typical handbook or datasheet values that have not been checked; each record lists them in `provisional_fields`. No `cost_per_kg` is set. Replace these with supplier values before M5. The §5.2 ±2 % Js sensitivity check runs in M5; steel_1010's tail is flat, so Js barely affects it.
- **[M2→M4] Phase labelling.** Counter-clockwise motoring excites A → D → C → B (pinned by a test). The owner decides whether to relabel phases so the sequence reads alphabetically before the drive work.
- **[M2→M4] Solve speed.** About 0.65–1.0 s per Newton iteration at 43k DOF and 5–13 iterations cold, against §7.2's ≤ 4 s per solve. M4 options: vectorised P1 assembly with a fixed sparsity pattern, parallel map points, a tangent (Euler) predictor for current continuation (a warm start or a scaled start does not help), and an energy (Armijo) line search. Keep `skfem_reference` as it is; its independence makes it the M3 cross-check.
- **[M2→M4] Per-region stacking factor.** Motor-CAD sets the stacking factor per stator and rotor component; srmcore sets it per material. Revisit when rotor and stator use different stacks.
- **[M2→M5] FEMM fixtures.** Give FEMM the raw curve plus its LamFill, not the stacked curve, so the stacking factor is not applied twice.
```

§11: append these rows to the decision-log table:

```markdown
| 2026-09-29 | B-H fit is a monotone Hermite interpolant of H(B), not a PCHIP of B(H) (§5.2 step 4); decided by the owner's expert panel |
| 2026-09-29 | Saturation tail J = Js − d/(1 + s·(H−Hn)/d), C¹ at the last point (§5.2 step 6) |
| 2026-09-29 | μ0 = 4π×10⁻⁷ exactly (FEMM parity) |
| 2026-09-29 | Outer air ring is `MeshSettings.outer_air_thickness`, default 0 (A = 0 on the stator OD); M5 decides whether to default to a ring |
| 2026-09-29 | Material costs stay unset until supplier quotes exist; placeholder values are listed in `provisional_fields` |
```

- [ ] **Step 6: Commit**

```bash
git add src/srmcore/materials tests/materials/test_material_library.py docs/superpowers/specs/2026-09-28-srm-core-engine-design.md
git commit -m "feat(materials): material schema and JSON library (M19, steel_1010, copper)" -m "<trailers>"
```

---

### Task 3: B-H processing and reluctivity laws

**Review:** Opus. Check the tail maths (C¹ join, closed-form inverse, energy integrals), the unit heuristics and the small-B limits.

**Files:**
- Create: `src/srmcore/model/constants.py`
- Create: `src/srmcore/materials/bh.py`
- Create: `src/srmcore/materials/laws.py`
- Create: `tests/materials/test_bh.py`

**Interfaces:**
- Consumes: `BHTable`, `SoftMagneticMaterial`, `ConductorMaterial`, `load_material` (Task 2); `InputError`, `ValidationIssue` (M1).
- Produces:
  - `srmcore.model.constants.MU0 = 4e-7 * math.pi`.
  - `check_bh_units(h, b) -> None`. It raises `InputError(parameter "bh", rule "units")` when max B > 3 T, or when H at 1 T lies outside [5, 5000] A/m.
  - `repair_monotone(h, b) -> (h, b, changes: list[str])`.
  - `process_bh(table: BHTable, stacking_factor: float, saturation_polarisation: float) -> tuple[BHCurve, BHReport]`. Its rules are `monotone`, `units`, `polarisation` and `saturation`, all with parameter `"bh"`.
  - `BHCurve` provides `h_of_b(b)`, `dh_db(b)`, `nu_dnu(b2) -> (ν, dν/d(B²))`, `energy_density(b)` = ∫0^B H dB and `coenergy_density(b)` = B·H − w. All take and return arrays; B is the effective (stacked) flux density.
  - `BHReport(added_origin, stacking_factor, initial_relative_permeability, join_b, join_h, tail_saturation_polarisation, tail_join_slope, knot_max_relative_error)`.
  - `ReluctivityLaw` Protocol (`nu_dnu`, `energy_density`, `coenergy_density`); `LinearLaw(relative_permeability)`; `VACUUM = LinearLaw(1.0)`; `law_for_material(material) -> ReluctivityLaw` (a conductor maps to `VACUUM`); `library_law(name) -> ReluctivityLaw`, which is cached with `lru_cache` so the same name returns the same object.

Method (spec §5.2): add the origin; require strictly increasing H and B; check units; apply the stacking factor at the knots, `B_eff = k·B + (1−k)·μ0·H`; require dB/dH ≥ μ0 on every segment (J non-decreasing). Then build a monotone cubic Hermite interpolant of **H(B)** through the stacked knots. It uses PCHIP knot derivatives, except that the end derivative equals the last secant. Beyond the last point, J = Js_eff − d/(1 + s·(H−Hn)/d), with Js_eff = k·Js, d = Js_eff − Jn and s = 1/H′(Bn) − μ0 ≥ 0. That tail is C¹ at the join and stable as s → 0. Its inverse is the stable root of a quadratic, and ∫B dH on it is closed-form (a `log1p` term).

- [ ] **Step 1: Write the failing tests**

Create `tests/materials/test_bh.py`:

```python
import numpy as np
import pytest

from srmcore.materials.bh import B_SMALL, process_bh, repair_monotone
from srmcore.materials.laws import VACUUM, LinearLaw, law_for_material, library_law
from srmcore.materials.library import load_material
from srmcore.materials.schema import BHTable
from srmcore.model.constants import MU0
from srmcore.model.errors import InputError

M19 = load_material("M19")


def _process(table, k=1.0, js=2.1):
    return process_bh(table, k, js)


def _table(h, b):
    return BHTable(h=tuple(float(x) for x in h), b=tuple(float(x) for x in b))


@pytest.mark.parametrize("h_scale,b_scale", [(1.0, 1000.0), (1.0, 10000.0), (1e-3, 1.0), (1 / 79.577, 1.0)],
                         ids=["B in mT", "B in gauss", "H in kA/m", "H in Oe"])
def test_unit_mixups_are_rejected(h_scale, b_scale):
    table = _table(np.array(M19.bh.h) * h_scale, np.array(M19.bh.b) * b_scale)
    with pytest.raises(InputError) as info:
        _process(table)
    assert info.value.issues[0].parameter == "bh" and info.value.issues[0].rule == "units"


def test_origin_is_added_and_reported():
    curve, report = _process(_table(M19.bh.h[1:], M19.bh.b[1:]), js=2.03)
    assert report.added_origin
    assert curve.h_of_b(np.array([0.0]))[0] == 0.0


def test_non_monotone_table_is_rejected_and_repair_reports_changes():
    h = [0.0, 50.0, 40.0, 100.0, 200.0, 1000.0]
    b = [0.0, 0.5, 0.6, 1.0, 1.2, 1.5]
    with pytest.raises(InputError) as info:
        _process(_table(h, b))
    assert info.value.issues[0].rule == "monotone"
    h2, b2, changes = repair_monotone(h, b)
    assert list(h2) == [0.0, 50.0, 100.0, 200.0, 1000.0]
    assert changes == ["dropped point 2 (H=40 A/m, B=0.6 T): not above point 1"]


def test_decreasing_polarisation_is_rejected():
    # dB/dH = 0.5·μ0 on the last segment: J = B - μ0·H would fall.
    h = [0.0, 100.0, 1000.0, 1e5, 2e5]
    b = [0.0, 1.0, 1.5, 2.0, 2.0 + 0.5 * MU0 * 1e5]
    with pytest.raises(InputError) as info:
        _process(_table(h, b), js=2.5)
    assert info.value.issues[0].rule == "polarisation"


def test_saturation_polarisation_must_exceed_last_point():
    with pytest.raises(InputError) as info:
        _process(M19.bh, k=1.0, js=1.9)
    assert info.value.issues[0].rule == "saturation"


def test_stacking_factor_applied_at_the_knots():
    k = 0.95
    curve, report = process_bh(M19.bh, k, M19.saturation_polarisation)
    h = np.array(M19.bh.h[1:])
    b_eff = k * np.array(M19.bh.b[1:]) + (1 - k) * MU0 * h
    assert np.allclose(curve.h_of_b(b_eff), h, rtol=1e-12)
    assert report.knot_max_relative_error < 1e-12
    assert report.tail_saturation_polarisation == pytest.approx(k * M19.saturation_polarisation)


@pytest.mark.parametrize("name", ["M19", "steel_1010"])
def test_tail_joins_c1_and_approaches_js(name):
    m = load_material(name)
    curve, report = process_bh(m.bh, m.stacking_factor, m.saturation_polarisation)
    bn, e = report.join_b, 1e-7
    below, above = curve.h_of_b(np.array([bn - e, bn + e]))
    assert above - below == pytest.approx(0.0, abs=1.0)                  # H ~ 2e5 A/m: C0
    d_below, d_above = curve.dh_db(np.array([bn - e, bn + e]))
    assert d_above == pytest.approx(d_below, rel=1e-6)                      # C1
    b = np.array([bn + 0.5, bn + 2.0, bn + 10.0])
    j = b - MU0 * curve.h_of_b(b)
    assert np.all(np.diff(j) >= 0) and np.all(j < report.tail_saturation_polarisation)
    assert np.all(curve.dh_db(b) <= 1 / MU0 * (1 + 1e-12))


@pytest.mark.parametrize("name", ["M19", "steel_1010"])
def test_energy_and_coenergy_densities_match_quadrature(name):
    m = load_material(name)
    curve, _ = process_bh(m.bh, m.stacking_factor, m.saturation_polarisation)
    for b_top in (0.3, 1.5, 2.2, 3.0):
        grid = np.linspace(0.0, b_top, 200_001)
        w_num = np.trapezoid(curve.h_of_b(grid), grid)
        assert curve.energy_density(np.array([b_top]))[0] == pytest.approx(w_num, rel=1e-6)
        h_top = curve.h_of_b(np.array([b_top]))[0]
        assert curve.coenergy_density(np.array([b_top]))[0] == pytest.approx(b_top * h_top - w_num, rel=1e-6)


def test_reluctivity_derivative_matches_finite_differences():
    curve = library_law("M19")
    b2 = np.array([0.3, 1.2, 1.9, 2.2, 2.5, 3.0, 4.0]) ** 2
    nu, dnu = curve.nu_dnu(b2)
    step = 1e-6 * b2
    fd = (curve.nu_dnu(b2 + step)[0] - curve.nu_dnu(b2 - step)[0]) / (2 * step)
    assert np.allclose(dnu, fd, rtol=1e-6)
    assert np.allclose(nu, curve.h_of_b(np.sqrt(b2)) / np.sqrt(b2))


def test_reluctivity_is_finite_at_zero_field():
    nu, dnu = library_law("M19").nu_dnu(np.array([0.0, 1e-14, (B_SMALL / 2) ** 2]))
    assert np.all(np.isfinite(nu)) and np.all(nu > 0) and np.all(dnu == 0)


def test_laws_for_materials():
    assert law_for_material(load_material("copper")) is VACUUM
    assert library_law("M19") is library_law("M19")
    lin = LinearLaw(1000.0)
    nu, dnu = lin.nu_dnu(np.array([1.0, 4.0]))
    assert np.allclose(nu, 1 / (1000 * MU0)) and np.all(dnu == 0)
    assert lin.energy_density(np.array([2.0]))[0] == pytest.approx(2.0 / (1000 * MU0))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/materials/test_bh.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'srmcore.materials.bh'`.

- [ ] **Step 3: Implement**

`src/srmcore/model/constants.py`:

```python
"""Physical constants shared by all layers."""
import math

# Exact pre-2019 value, as used by FEMM; keeps the M5 cross-tool comparison free of a 1e-10 offset.
MU0 = 4e-7 * math.pi
```

`src/srmcore/materials/bh.py`:

```python
"""B-H processing (spec §5.2): unit checks, origin, stacking factor, monotone H(B) interpolation and a
C¹ saturation tail. The result is the effective (stacked) single-valued law the solver uses."""
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicHermiteSpline, PchipInterpolator

from ..model.constants import MU0
from ..model.errors import InputError, ValidationIssue
from .schema import BHTable

# Below this |B| the reluctivity is taken as its B = 0 limit and dν/d(B²) as 0: the closed forms
# lose all precision to cancellation there, and the Jacobian term they feed scales with B².
B_SMALL = 1e-5
# At B = 1 T every soft-magnetic steel has H in this range; outside it the table is almost always
# in kA/m, Oe or mT rather than A/m / T.
H_AT_1T_RANGE = (5.0, 5000.0)
B_MAX_PLAUSIBLE = 3.0


def _error(rule: str, message: str) -> InputError:
    return InputError([ValidationIssue("bh", rule, message)])


def check_bh_units(h: np.ndarray, b: np.ndarray) -> None:
    if b.max() > B_MAX_PLAUSIBLE:
        raise _error("units", f"max B = {b.max():g} T is implausible; B must be in tesla (not mT or gauss)")
    if b.max() >= 1.0 and np.all(np.diff(b) > 0):
        h1 = float(np.interp(1.0, b, h))
        lo, hi = H_AT_1T_RANGE
        if not lo <= h1 <= hi:
            raise _error("units", f"H at 1 T = {h1:g} is outside {lo:g}..{hi:g}; H must be in A/m (not kA/m or Oe)")


def repair_monotone(h, b) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Drop every point that does not strictly increase both H and B over the last kept point.
    Returns the kept points and one line per dropped point, naming it exactly."""
    h, b = np.asarray(h, float), np.asarray(b, float)
    keep = [0]
    changes: list[str] = []
    for i in range(1, len(h)):
        if h[i] > h[keep[-1]] and b[i] > b[keep[-1]]:
            keep.append(i)
        else:
            changes.append(f"dropped point {i} (H={h[i]:g} A/m, B={b[i]:g} T): not above point {keep[-1]}")
    return h[keep], b[keep], changes


@dataclass(frozen=True)
class BHReport:
    added_origin: bool
    stacking_factor: float
    initial_relative_permeability: float
    join_b: float
    join_h: float
    tail_saturation_polarisation: float
    tail_join_slope: float
    knot_max_relative_error: float


class BHCurve:
    """Effective single-valued law H(B): monotone cubic Hermite through the stacked data points, then
    J = B - μ0·H approaching Js_eff as J = Js - d / (1 + s·(H - Hn)/d), joined C¹ at the last point."""

    def __init__(self, h: np.ndarray, b: np.ndarray, js_eff: float):
        slopes = np.diff(h) / np.diff(b)
        d = PchipInterpolator(b, h).derivative()(b)
        # End derivative = last secant, so the tail's join slope dB/dH is exactly the last secant's,
        # which the polarisation check guarantees is >= μ0.
        d[-1] = slopes[-1]
        self._spline = CubicHermiteSpline(b, h, d)
        self._dspline = self._spline.derivative()
        self._w = self._spline.antiderivative()
        self.bn, self.hn = float(b[-1]), float(h[-1])
        self.jn = self.bn - MU0 * self.hn
        self.js = float(js_eff)
        self.gap = self.js - self.jn
        self.s = max(1.0 / slopes[-1] - MU0, 0.0)
        self.k = self.s / self.gap
        self.nu0 = float(d[0])
        self._wn = float(self._w(self.bn))

    def _tail_x(self, b: np.ndarray) -> np.ndarray:
        """H - Hn for B >= Bn: the stable root of μ0·k·x² + (μ0 - c·k)·x - (B - Bn) = 0."""
        db = b - self.bn
        c = db - self.gap
        q = MU0 - c * self.k
        return 2 * db / (q + np.sqrt(q * q + 4 * MU0 * self.k * db))

    def _tail_coenergy_increment(self, x: np.ndarray) -> np.ndarray:
        """∫ B dH from Hn to Hn + x on the tail."""
        h = self.hn + x
        log_term = self.gap * x if self.k == 0 else self.gap / self.k * np.log1p(self.k * x)
        return MU0 * (h * h - self.hn * self.hn) / 2 + self.js * x - log_term

    def h_of_b(self, b) -> np.ndarray:
        b = np.asarray(b, float)
        out = np.empty_like(b)
        data = b <= self.bn
        out[data] = self._spline(b[data])
        out[~data] = self.hn + self._tail_x(b[~data])
        return out

    def dh_db(self, b) -> np.ndarray:
        b = np.asarray(b, float)
        out = np.empty_like(b)
        data = b <= self.bn
        out[data] = self._dspline(b[data])
        u = 1 + self.k * self._tail_x(b[~data])
        out[~data] = 1.0 / (MU0 + self.s / (u * u))
        return out

    def nu_dnu(self, b2) -> tuple[np.ndarray, np.ndarray]:
        """Reluctivity ν = H/B and dν/d(B²) at squared flux density b2."""
        b2 = np.asarray(b2, float)
        b = np.sqrt(b2)
        small = b < B_SMALL
        bs = np.where(small, B_SMALL, b)
        h = self.h_of_b(bs)
        nu = np.where(small, self.nu0, h / bs)
        dnu = np.where(small, 0.0, (self.dh_db(bs) * bs - h) / (2 * bs**3))
        return nu, dnu

    def energy_density(self, b) -> np.ndarray:
        """w(B) = ∫0^B H dB, J/m³."""
        b = np.asarray(b, float)
        out = np.empty_like(b)
        data = b <= self.bn
        out[data] = self._w(b[data])
        bt = b[~data]
        x = self._tail_x(bt)
        h = self.hn + x
        out[~data] = self._wn + (bt * h - self.bn * self.hn) - self._tail_coenergy_increment(x)
        return out

    def coenergy_density(self, b) -> np.ndarray:
        """w'(B) = B·H(B) - w(B) = ∫0^H B dH, J/m³."""
        b = np.asarray(b, float)
        return b * self.h_of_b(b) - self.energy_density(b)


def process_bh(table: BHTable, stacking_factor: float, saturation_polarisation: float) -> tuple[BHCurve, BHReport]:
    h = np.asarray(table.h, float)
    b = np.asarray(table.b, float)
    if np.any(h < 0) or np.any(b < 0):
        raise _error("monotone", "B-H points must be non-negative (first-quadrant magnetisation curve)")
    added_origin = not (h[0] == 0 and b[0] == 0)
    if added_origin:
        h, b = np.concatenate([[0.0], h]), np.concatenate([[0.0], b])
    if not (np.all(np.diff(h) > 0) and np.all(np.diff(b) > 0)):
        bad = int(np.argmin(np.minimum(np.diff(h), np.diff(b)))) + 1
        raise _error("monotone", f"B-H points must strictly increase in H and B; point {bad} does not "
                                 f"(use repair_monotone to drop offending points)")
    check_bh_units(h, b)
    k = stacking_factor
    b_eff = k * b + (1 - k) * MU0 * h
    secant = np.diff(b_eff) / np.diff(h)
    if np.any(secant < MU0 * (1 - 1e-9)):
        i = int(np.argmin(secant))
        raise _error("polarisation", f"dB/dH < μ0 between B = {b_eff[i]:g} and {b_eff[i + 1]:g} T: "
                                     f"polarisation J = B - μ0·H decreases, which no material does")
    js_eff = k * saturation_polarisation
    jn = b_eff[-1] - MU0 * h[-1]
    if js_eff <= jn:
        raise _error("saturation", f"saturation polarisation {saturation_polarisation:g} T is not above the "
                                   f"polarisation at the last data point ({jn / k:g} T)")
    curve = BHCurve(h, b_eff, js_eff)
    knot_err = np.abs(curve.h_of_b(b_eff[1:]) - h[1:]) / h[1:]
    report = BHReport(
        added_origin=added_origin, stacking_factor=k,
        initial_relative_permeability=1.0 / (MU0 * curve.nu0),
        join_b=curve.bn, join_h=curve.hn, tail_saturation_polarisation=js_eff, tail_join_slope=curve.s,
        knot_max_relative_error=float(knot_err.max()),
    )
    return curve, report
```

`src/srmcore/materials/laws.py`:

```python
"""Per-region magnetic laws the solver evaluates: a linear law, or a processed B-H curve."""
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import numpy as np

from ..model.constants import MU0
from .bh import process_bh
from .library import load_material
from .schema import ConductorMaterial, SoftMagneticMaterial


class ReluctivityLaw(Protocol):
    """ν(|B|) for one material. BHCurve and LinearLaw implement it."""

    def nu_dnu(self, b2: np.ndarray) -> tuple[np.ndarray, np.ndarray]: ...

    def energy_density(self, b: np.ndarray) -> np.ndarray: ...

    def coenergy_density(self, b: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class LinearLaw:
    relative_permeability: float = 1.0

    @property
    def nu(self) -> float:
        return 1.0 / (MU0 * self.relative_permeability)

    def nu_dnu(self, b2):
        b2 = np.asarray(b2, float)
        return np.full_like(b2, self.nu), np.zeros_like(b2)

    def energy_density(self, b):
        return 0.5 * self.nu * np.asarray(b, float) ** 2

    def coenergy_density(self, b):
        return self.energy_density(b)


VACUUM = LinearLaw(1.0)


def law_for_material(material: SoftMagneticMaterial | ConductorMaterial) -> ReluctivityLaw:
    if isinstance(material, ConductorMaterial):
        return VACUUM
    curve, _ = process_bh(material.bh, material.stacking_factor, material.saturation_polarisation)
    return curve


@lru_cache(maxsize=None)
def library_law(name: str) -> ReluctivityLaw:
    """The law for a library material, processed once per process."""
    return law_for_material(load_material(name))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/materials tests/test_import_rules.py -q`
Expected: PASS (in about 5 s).

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/model/constants.py src/srmcore/materials/bh.py src/srmcore/materials/laws.py tests/materials/test_bh.py
git commit -m "feat(materials): B-H pipeline with stacking factor, C1 polarisation tail and reluctivity laws" -m "<trailers>"
```

---

### Task 4: Winding, problem and machine-problem builder

**Review:** Sonnet. Check especially that nothing parses region names.

**Files:**
- Create: `src/srmcore/physics/fem.py`
- Create: `src/srmcore/physics/winding.py`
- Create: `src/srmcore/physics/problem.py`
- Create: `src/srmcore/physics/build.py`
- Create: `tests/physics/test_winding.py`
- Create: `tests/physics/test_machine_problem.py`

**Interfaces:**
- Consumes: `MachineMesh` with complete `region_part` (Task 1); `ReluctivityLaw`, `VACUUM`, `library_law` (Task 3); `Design`, `RegionMaterials`, `InputError` (M1).
- Produces:
  - `triangle_areas(nodes, triangles) -> ndarray` and `element_flux_density(nodes, triangles, a) -> ndarray (m, 2)`, where B = (∂A/∂y, −∂A/∂x).
  - `Winding(coil_sides: tuple[str, ...], circuits: tuple[str, ...], matrix: ndarray (sides × circuits), parallel_paths: int, equal_path_split_assumed: bool)`. Each matrix entry is sign × turns / (paths × side area), in 1/m².
  - `phase_winding(mesh: MachineMesh, turns_per_pole: int, parallel_paths: int = 1) -> Winding`. It builds one circuit per phase letter from `CoilInfo`, with sides sorted by name. It raises `InputError(parameter "parallel_paths", rule "winding")`.
  - `BandInfo(elements: ndarray, inner_radius: float, outer_radius: float)`.
  - `Magnetostatic2D(nodes, triangles, element_law, laws, element_region, region_names, region_kind, element_coil, winding, currents, dirichlet_nodes, depth, band=None)`, with `current_density() -> ndarray` (J per element) and `with_currents(currents) -> Magnetostatic2D` (which raises `ValueError` on a wrong length).
  - `machine_problem(mesh: MachineMesh, design: Design, currents: Mapping[str, float] | None = None, winding: Winding | None = None) -> Magnetostatic2D`. `laws[0]` is always `VACUUM`. A `ValueError` names an unknown circuit; a `KeyError` from `load_material` names an unknown material.

- [ ] **Step 1: Write the failing tests**

Create `tests/physics/test_winding.py`:

```python
import numpy as np
import pytest

from conftest import make_8_6, make_12_8
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError
from srmcore.physics.fem import element_flux_density, triangle_areas
from srmcore.physics.winding import phase_winding


@pytest.fixture(scope="module")
def mesh_8_6():
    return mesh_at_angle(build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))), 0.0)


def test_triangle_areas_and_flux_density_of_a_linear_field():
    nodes = np.array([[0.0, 0.0], [2.0, 0.0], [0.0, 1.0]])
    tris = np.array([[0, 1, 2]])
    assert triangle_areas(nodes, tris)[0] == pytest.approx(1.0)
    a = 3.0 * nodes[:, 0] - 5.0 * nodes[:, 1]            # A = 3x - 5y  ->  B = (∂A/∂y, -∂A/∂x) = (-5, -3)
    assert np.allclose(element_flux_density(nodes, tris, a), [[-5.0, -3.0]])


def test_phase_winding_8_6(mesh_8_6):
    w = phase_winding(mesh_8_6, turns_per_pole=60)
    assert w.circuits == ("A", "B", "C", "D")
    assert w.coil_sides == tuple(sorted(mesh_8_6.coils))
    assert not w.equal_path_split_assumed
    areas = triangle_areas(mesh_8_6.nodes, mesh_8_6.triangles)
    for s, name in enumerate(w.coil_sides):
        info = mesh_8_6.coils[name]
        k = w.circuits.index(info.phase)
        area = areas[mesh_8_6.region_ids == mesh_8_6.region_names.index(name)].sum()
        assert w.matrix[s, k] == pytest.approx(info.sign * 60 / area)
        assert np.count_nonzero(w.matrix[s]) == 1          # block-diagonal: one circuit per coil side
    # A conventional phase is a closed series loop: its + and - sides carry equal and opposite ampere-turns.
    for k in range(4):
        col = w.matrix[:, k]
        side_area = np.array([areas[mesh_8_6.region_ids == mesh_8_6.region_names.index(n)].sum() for n in w.coil_sides])
        assert (col * side_area).sum() == pytest.approx(0.0, abs=1e-9)
        assert np.abs(col * side_area).sum() == pytest.approx(4 * 60)


def test_parallel_paths(mesh_8_6):
    w = phase_winding(mesh_8_6, turns_per_pole=60, parallel_paths=2)
    assert w.equal_path_split_assumed
    assert np.allclose(w.matrix, phase_winding(mesh_8_6, 60).matrix / 2)
    with pytest.raises(InputError) as info:
        phase_winding(mesh_8_6, turns_per_pole=60, parallel_paths=3)
    assert info.value.issues[0].parameter == "parallel_paths"


@pytest.mark.slow
def test_phase_winding_12_8_has_three_circuits():
    m = mesh_at_angle(build_machine_mesh(Design(machine=make_12_8(), mesh=MeshSettings(preset="screening"))), 0.0)
    w = phase_winding(m, turns_per_pole=30)
    assert w.circuits == ("A", "B", "C")
    assert all(np.count_nonzero(w.matrix[:, k]) == 8 for k in range(3))
```

Create `tests/physics/test_machine_problem.py`:

```python
import dataclasses

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.materials.laws import VACUUM, library_law
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings, RegionMaterials
from srmcore.physics.build import machine_problem

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def mesh_8_6():
    return mesh_at_angle(build_machine_mesh(DESIGN), 0.0)


def test_laws_follow_region_kind(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN)
    kind = np.array([mesh_8_6.region_kind[n] for n in mesh_8_6.region_names])[mesh_8_6.region_ids]
    law = np.array(p.laws, dtype=object)[p.element_law]
    assert all(x is library_law("M19") for x in law[(kind == "stator_iron") | (kind == "rotor_iron")])
    assert all(x is library_law("steel_1010") for x in law[kind == "shaft"])
    assert all(x is VACUUM for x in law[(kind == "air") | (kind == "coil")])


def test_problem_geometry_boundary_and_band(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN, {"A": 10.0})
    assert p.nodes is mesh_8_6.nodes and p.triangles is mesh_8_6.triangles
    assert np.array_equal(p.dirichlet_nodes, np.unique(mesh_8_6.outer_edges))
    assert p.depth == DESIGN.machine.stack_length
    assert np.array_equal(p.band.elements, np.arange(len(p.triangles))[mesh_8_6.band_rows])
    assert (p.band.inner_radius, p.band.outer_radius) == (mesh_8_6.band_inner_radius, mesh_8_6.band_outer_radius)
    assert np.allclose(p.currents, [10.0, 0.0, 0.0, 0.0])


def test_current_density_only_in_excited_coils(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN, {"B": 5.0})
    j = p.current_density()
    for rid, name in enumerate(mesh_8_6.region_names):
        rows = mesh_8_6.region_ids == rid
        info = mesh_8_6.coils.get(name)
        if info is not None and info.phase == "B":
            assert np.all(np.sign(j[rows]) == info.sign) and np.all(j[rows] != 0)
        else:
            assert np.all(j[rows] == 0)


def test_region_names_are_never_parsed(mesh_8_6):
    """Opaque region names must give the same problem: the builder reads region_kind and coils only."""
    new = {n: f"r{i}" for i, n in enumerate(mesh_8_6.region_names)}
    renamed = dataclasses.replace(
        mesh_8_6, region_names=tuple(new[n] for n in mesh_8_6.region_names),
        region_kind={new[k]: v for k, v in mesh_8_6.region_kind.items()},
        region_part={new[k]: v for k, v in mesh_8_6.region_part.items()},
        coils={new[k]: v for k, v in mesh_8_6.coils.items()})
    p1 = machine_problem(mesh_8_6, DESIGN, {"A": 10.0})
    p2 = machine_problem(renamed, DESIGN, {"A": 10.0})
    assert np.allclose(p1.current_density(), p2.current_density())
    assert [p1.laws[i] for i in p1.element_law] == [p2.laws[i] for i in p2.element_law]


def test_unknown_circuit_and_material_are_rejected(mesh_8_6):
    with pytest.raises(ValueError, match="unknown circuit"):
        machine_problem(mesh_8_6, DESIGN, {"E": 1.0})
    bad = DESIGN.model_copy(update={"machine": make_8_6(materials=RegionMaterials(stator="M270"))})
    with pytest.raises(KeyError, match="M270"):
        machine_problem(mesh_8_6, bad)


def test_with_currents_checks_length(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN)
    assert np.allclose(p.with_currents([1.0, 2.0, 3.0, 4.0]).currents, [1, 2, 3, 4])
    with pytest.raises(ValueError, match="4 circuit currents"):
        p.with_currents([1.0])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/physics -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'srmcore.physics.fem'`.

- [ ] **Step 3: Implement**

`src/srmcore/physics/fem.py`:

```python
"""Linear-triangle (P1) kinematics shared by every solver adapter and by post-processing."""
import numpy as np


def triangle_areas(nodes: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    a, b, c = nodes[triangles[:, 0]], nodes[triangles[:, 1]], nodes[triangles[:, 2]]
    # Explicit 2D cross product: numpy >= 2 rejects np.cross on 2-vectors.
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))


def element_flux_density(nodes: np.ndarray, triangles: np.ndarray, a: np.ndarray) -> np.ndarray:
    """B = curl(A ẑ) = (∂A/∂y, -∂A/∂x), constant on each P1 triangle. Returns (n_elements, 2)."""
    x, y, av = nodes[triangles, 0], nodes[triangles, 1], a[triangles]
    det = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0]) - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0])
    dadx = ((y[:, 1] - y[:, 2]) * av[:, 0] + (y[:, 2] - y[:, 0]) * av[:, 1] + (y[:, 0] - y[:, 1]) * av[:, 2]) / det
    dady = ((x[:, 2] - x[:, 1]) * av[:, 0] + (x[:, 0] - x[:, 2]) * av[:, 1] + (x[:, 1] - x[:, 0]) * av[:, 2]) / det
    return np.column_stack([dady, -dadx])
```

`src/srmcore/physics/winding.py`:

```python
"""Winding as data (spec §6): the connection matrix from coil sides to circuits."""
from dataclasses import dataclass

import numpy as np

from ..mesh.machine import MachineMesh
from ..model.errors import InputError, ValidationIssue
from .fem import triangle_areas


@dataclass(frozen=True, eq=False)
class Winding:
    """matrix[s, k] = sign × turns / (parallel_paths × area of coil side s), in 1/m², so that the
    current density in side s is Σ_k matrix[s, k]·i_k and ψ_k = L·Σ_s matrix[s, k]·∫_s A dA."""
    coil_sides: tuple[str, ...]
    circuits: tuple[str, ...]
    matrix: np.ndarray
    parallel_paths: int
    # Spec §6: with more than one parallel path the circuit current is assumed to split equally.
    equal_path_split_assumed: bool


def phase_winding(mesh: MachineMesh, turns_per_pole: int, parallel_paths: int = 1) -> Winding:
    """Conventional SRM: one circuit per phase, every coil side of that phase in it."""
    phases = sorted({info.phase for info in mesh.coils.values()})
    for phase in phases:
        poles = {info.pole for info in mesh.coils.values() if info.phase == phase}
        if parallel_paths < 1 or len(poles) % parallel_paths:
            raise InputError([ValidationIssue(
                "parallel_paths", "winding",
                f"phase {phase} has {len(poles)} poles, which {parallel_paths} parallel paths cannot divide")])
    sides = tuple(sorted(mesh.coils))
    areas = triangle_areas(mesh.nodes, mesh.triangles)
    matrix = np.zeros((len(sides), len(phases)))
    for s, name in enumerate(sides):
        info = mesh.coils[name]
        area = areas[mesh.region_ids == mesh.region_names.index(name)].sum()
        matrix[s, phases.index(info.phase)] = info.sign * turns_per_pole / (parallel_paths * area)
    return Winding(sides, tuple(phases), matrix, parallel_paths, parallel_paths > 1)
```

`src/srmcore/physics/problem.py`:

```python
"""Solver-neutral 2D magnetostatic problem (spec §6): ∇·(ν(|B|)∇A_z) = -J_z, A = 0 on the Dirichlet
nodes, depth = stack length."""
import dataclasses
from dataclasses import dataclass

import numpy as np

from ..materials.laws import ReluctivityLaw
from .winding import Winding


@dataclass(frozen=True, eq=False)
class BandInfo:
    elements: np.ndarray
    inner_radius: float
    outer_radius: float


@dataclass(frozen=True, eq=False)
class Magnetostatic2D:
    nodes: np.ndarray
    triangles: np.ndarray
    element_law: np.ndarray
    laws: tuple[ReluctivityLaw, ...]
    element_region: np.ndarray
    region_names: tuple[str, ...]
    region_kind: dict[str, str]
    element_coil: np.ndarray
    winding: Winding
    currents: np.ndarray
    dirichlet_nodes: np.ndarray
    depth: float
    band: BandInfo | None = None

    def current_density(self) -> np.ndarray:
        """J_z per element, A/m²."""
        j = np.zeros(len(self.triangles))
        in_coil = self.element_coil >= 0
        j[in_coil] = self.winding.matrix[self.element_coil[in_coil]] @ self.currents
        return j

    def with_currents(self, currents) -> "Magnetostatic2D":
        currents = np.asarray(currents, float)
        if currents.shape != (len(self.winding.circuits),):
            raise ValueError(f"expected {len(self.winding.circuits)} circuit currents, got shape {currents.shape}")
        return dataclasses.replace(self, currents=currents)
```

`src/srmcore/physics/build.py`:

```python
"""Build a Magnetostatic2D from a machine mesh. Materials, coils and the boundary come from the mesh's
region_kind, coils (CoilInfo) and outer_edges, never from parsing region names."""
from collections.abc import Mapping

import numpy as np

from ..materials.laws import VACUUM, ReluctivityLaw, library_law
from ..mesh.machine import MachineMesh
from ..model.design import Design
from .problem import BandInfo, Magnetostatic2D
from .winding import Winding, phase_winding

# region_kind -> the RegionMaterials field naming that region's material; "air" is always vacuum.
KIND_ROLE = {"stator_iron": "stator", "rotor_iron": "rotor", "shaft": "shaft", "coil": "coil"}


def machine_problem(mesh: MachineMesh, design: Design, currents: Mapping[str, float] | None = None,
                    winding: Winding | None = None) -> Magnetostatic2D:
    p = design.machine
    winding = winding if winding is not None else phase_winding(mesh, p.turns_per_pole)
    laws: list[ReluctivityLaw] = [VACUUM]
    law_of_region = np.zeros(len(mesh.region_names), dtype=np.int64)
    for rid, name in enumerate(mesh.region_names):
        kind = mesh.region_kind[name]
        if kind == "air":
            continue
        if kind not in KIND_ROLE:
            raise ValueError(f"region {name!r} has unknown kind {kind!r}")
        law = library_law(getattr(p.materials, KIND_ROLE[kind]))
        if law not in laws:
            laws.append(law)
        law_of_region[rid] = laws.index(law)
    coil_index = np.full(len(mesh.region_names), -1, dtype=np.int64)
    for s, name in enumerate(winding.coil_sides):
        coil_index[mesh.region_names.index(name)] = s
    i = np.zeros(len(winding.circuits))
    for circuit, value in (currents or {}).items():
        if circuit not in winding.circuits:
            raise ValueError(f"unknown circuit {circuit!r}; circuits are {winding.circuits}")
        i[winding.circuits.index(circuit)] = value
    band = BandInfo(np.arange(mesh.band_rows.start, mesh.band_rows.stop), mesh.band_inner_radius,
                    mesh.band_outer_radius)
    return Magnetostatic2D(
        nodes=mesh.nodes, triangles=mesh.triangles,
        element_law=law_of_region[mesh.region_ids], laws=tuple(laws),
        element_region=mesh.region_ids.astype(np.int64), region_names=mesh.region_names,
        region_kind=dict(mesh.region_kind), element_coil=coil_index[mesh.region_ids],
        winding=winding, currents=i,
        # outer_edges is the mesh's outermost boundary; a future stator_outer_air ring moves it
        # outward in the mesh layer and this code does not change.
        dirichlet_nodes=np.unique(mesh.outer_edges), depth=p.stack_length, band=band,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/physics tests/test_import_rules.py -q`
Expected: PASS (in about 30 s; each module builds one screening mesh).

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/physics tests/physics
git commit -m "feat(physics): winding connection matrix and Magnetostatic2D built from region_kind/coils/outer_edges" -m "<trailers>"
```

---

### Task 5: scikit-fem reference solver

**Review:** Opus. Check the consistent Jacobian, the dual convergence criterion, the line search, the fallback chain and the no-raise contract.

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Modify: `.github/workflows/ci.yml` (timeout, durations)
- Modify: `tests/test_import_rules.py` (`THIRD_PARTY_OWNERS`)
- Create: `src/srmcore/fields/solution.py`
- Create: `src/srmcore/physics/energy.py`
- Create: `src/srmcore/solvers/settings.py`
- Create: `src/srmcore/solvers/skfem_reference.py`
- Create: `tests/fem_fixtures.py`
- Create: `tests/solvers/test_newton.py`
- Create: `tests/solvers/test_mms.py`

**Interfaces:**
- Consumes: `Magnetostatic2D`, `Winding`, `element_flux_density`, `triangle_areas` (Task 4); `LinearLaw`, `VACUUM`, `library_law` (Task 3).
- Produces:
  - `SolveStatus` (str Enum: `OK`, `OK_WITH_FALLBACK`, `NONCONVERGED`).
  - `FieldSolution(a, b, nu, dnu_db2, energy, coenergy, status, iterations, residual, delta_a, fallbacks=(), load_fraction=1.0)`. Here `b` is (n_elements, 2) in the stator (global) frame; `energy` = W and `coenergy` = W′, in joules, depth included. `load_fraction` is below 1 only when the current ramp stopped early (status `NONCONVERGED`).
  - `field_energies(problem, b) -> (W, W′)`.
  - `ELEMENT_ORDER = 1`, `QUADRATURE_ORDER = 2`, `NewtonSettings(residual_tol=1e-8, delta_tol=1e-8, max_iterations=50, max_halvings=20, damped_max_step=0.5, ramp_steps=4)`. A line search that runs out of halvings without reducing the residual ends that Newton attempt as not converged, keeping the last accepted iterate; a trial residual already below `residual_tol` counts as a decrease., and the `SolverAdapter` Protocol (`name`, `solve(problem, initial=None) -> FieldSolution`).
  - `SkfemReference(settings=NewtonSettings())`. `.solve(problem, initial: ndarray | None = None) -> FieldSolution` never raises for non-convergence, and raises `ValueError` for a wrongly shaped `initial`. `.linearize(problem, a) -> (residual, tangent_csr)`, which M4 will use for L_inc. The fallback order is: full Newton; then damped (step ≤ 0.5 while the residual > 1e-2, twice the iterations), giving `("damped",)`; then a 4-step current ramp from `initial` with damped steps, giving `("damped", "ramp")`.
  - Test helpers in `tests/fem_fixtures.py`: `polar_mesh`, `toroid_problem`, `exact_toroid_b`, the `SHEET_IN`/`IRON`/`SHEET_OUT`/`R_OUTER`/`DEPTH` constants, `QuadraticLaw`, `mms_exact`, `mms_source`, `mms_problem`.

- [ ] **Step 1: Add the dependency and the ownership rule**

`pyproject.toml`: in `[project] dependencies`, add `"scikit-fem>=12,<13",` after `"scipy>=1.12",`. The upper bound is there because the reference solver's numbers are compared across solvers in M3. Then run `.venv\Scripts\python -m pip install -e ".[dev]"`.

`.github/workflows/ci.yml`: add `timeout-minutes: 20` to the `fast` job (at the same level as `runs-on`), and change the last step to `- run: python -m pytest -m "not slow" --durations=15`, so the slowest tests show in every CI log.

`tests/test_import_rules.py`: add `"skfem": {"solvers"},` to `THIRD_PARTY_OWNERS` after the `"gmsh"` entry.

- [ ] **Step 2: Write the failing tests**

Create `tests/fem_fixtures.py`:

```python
"""Small analytic FEM problems for solver tests: a structured polar mesh (current-sheet toroid) and a
unit-square MMS problem. Plain numpy; no Gmsh."""
import math

import numpy as np

from srmcore.materials.laws import VACUUM
from srmcore.physics.problem import Magnetostatic2D
from srmcore.physics.winding import Winding


def polar_mesh(radii: np.ndarray, n_theta: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rings of n_theta nodes at radii[1:] around a centre node (radii[0] must be 0). Returns nodes,
    CCW triangles and each triangle's annulus index i (between radii[i] and radii[i+1])."""
    assert radii[0] == 0.0
    t = np.arange(n_theta) * 2 * math.pi / n_theta
    nodes = [np.zeros((1, 2))]
    for r in radii[1:]:
        nodes.append(np.column_stack([r * np.cos(t), r * np.sin(t)]))
    nodes = np.vstack(nodes)
    ring = lambda i: 1 + (i - 1) * n_theta + np.arange(n_theta)  # noqa: E731  node ids of radii[i]
    tris, layer = [], []
    first = ring(1)
    tris.append(np.column_stack([np.zeros(n_theta, int), first, np.roll(first, -1)]))
    layer.append(np.zeros(n_theta, int))
    for i in range(1, len(radii) - 1):
        a, b = ring(i), ring(i + 1)
        a1, b1 = np.roll(a, -1), np.roll(b, -1)
        tris += [np.column_stack([a, b, b1]), np.column_stack([a, b1, a1])]
        layer += [np.full(n_theta, i), np.full(n_theta, i)]
    return nodes, np.vstack(tris), np.concatenate(layer)


def triangle_area(nodes, tris):
    a, b, c = nodes[tris[:, 0]], nodes[tris[:, 1]], nodes[tris[:, 2]]
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))


# Current-sheet toroid: +I in the inner sheet, -I in the outer sheet, iron ring in between. Between the
# sheets H = I / (2πr) exactly, whatever the material; outside them the field is zero.
SHEET_IN = (0.010, 0.011)
IRON = (0.012, 0.020)
SHEET_OUT = (0.021, 0.022)
R_OUTER = 0.030
DEPTH = 0.05


def toroid_problem(iron_law, current: float, n_theta: int = 256, layers_per_mm: int = 4) -> Magnetostatic2D:
    edges = [0.0, 0.005, *SHEET_IN, *IRON, *SHEET_OUT, R_OUTER]
    radii = [0.0]
    for lo, hi in zip(edges[:-1], edges[1:]):
        n = max(2, round((hi - lo) * 1000 * layers_per_mm)) if lo > 0 else 1
        radii += list(np.linspace(lo, hi, n + 1)[1:])
    radii = np.array(radii)
    nodes, tris, layer = polar_mesh(radii, n_theta)
    rmid = 0.5 * (radii[layer] + radii[layer + 1])
    in_sheet = (rmid > SHEET_IN[0]) & (rmid < SHEET_IN[1])
    out_sheet = (rmid > SHEET_OUT[0]) & (rmid < SHEET_OUT[1])
    iron = (rmid > IRON[0]) & (rmid < IRON[1])
    area = triangle_area(nodes, tris)
    region = np.where(in_sheet, 1, np.where(out_sheet, 2, np.where(iron, 3, 0)))
    coil = np.where(in_sheet, 0, np.where(out_sheet, 1, -1))
    winding = Winding(("sheet_in", "sheet_out"), ("c",),
                      np.array([[1.0 / area[in_sheet].sum()], [-1.0 / area[out_sheet].sum()]]), 1, False)
    outer = np.flatnonzero(np.isclose(np.hypot(nodes[:, 0], nodes[:, 1]), R_OUTER))
    return Magnetostatic2D(
        nodes=nodes, triangles=tris, element_law=iron.astype(np.int64), laws=(VACUUM, iron_law),
        element_region=region, region_names=("air", "sheet_in", "sheet_out", "iron"),
        region_kind={"air": "air", "sheet_in": "coil", "sheet_out": "coil", "iron": "stator_iron"},
        element_coil=coil, winding=winding, currents=np.array([current]), dirichlet_nodes=outer, depth=DEPTH,
    )


def exact_toroid_b(curve, current: float, r: np.ndarray) -> np.ndarray:
    """|B| in the iron ring at radius r: B such that H(B) = I / (2πr)."""
    grid = np.linspace(0.0, 5.0, 200_001)
    return np.interp(current / (2 * math.pi * r), curve.h_of_b(grid), grid)


class QuadraticLaw:
    """ν = ν0·(1 + α·B²): a smooth nonlinear law with closed-form energies, for MMS."""

    def __init__(self, nu0: float, alpha: float):
        self.nu0, self.alpha = nu0, alpha

    def nu_dnu(self, b2):
        b2 = np.asarray(b2, float)
        return self.nu0 * (1 + self.alpha * b2), np.full_like(b2, self.nu0 * self.alpha)

    def energy_density(self, b):
        b = np.asarray(b, float)
        return self.nu0 * (b**2 / 2 + self.alpha * b**4 / 4)

    def coenergy_density(self, b):
        b = np.asarray(b, float)
        return self.nu0 * (b**2 / 2 + 3 * self.alpha * b**4 / 4)


def mms_exact(x, y):
    return np.sin(math.pi * x) * np.sin(math.pi * y)


def mms_source(law: QuadraticLaw, x, y):
    """J = -∇·(ν(|∇A|²)∇A) for A = sin(πx)·sin(πy)."""
    p = math.pi
    sx, cx, sy, cy = np.sin(p * x), np.cos(p * x), np.sin(p * y), np.cos(p * y)
    ax, ay = p * cx * sy, p * sx * cy
    axx, ayy, axy = -p * p * sx * sy, -p * p * sx * sy, p * p * cx * cy
    g = ax * ax + ay * ay
    gx, gy = 2 * (ax * axx + ay * axy), 2 * (ax * axy + ay * ayy)
    nu, dnu = law.nu_dnu(g)
    return -(nu * (axx + ayy) + dnu * (gx * ax + gy * ay))


def mms_problem(law: QuadraticLaw, n: int) -> Magnetostatic2D:
    """Unit square, n×n cells split into triangles, A = 0 on the boundary; every element is its own
    'coil side' carrying the manufactured source at its centroid."""
    xs = np.linspace(0.0, 1.0, n + 1)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    nodes = np.column_stack([X.ravel(), Y.ravel()])
    idx = lambda i, j: i * (n + 1) + j  # noqa: E731
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    i, j = i.ravel(), j.ravel()
    tris = np.vstack([np.column_stack([idx(i, j), idx(i + 1, j), idx(i + 1, j + 1)]),
                      np.column_stack([idx(i, j), idx(i + 1, j + 1), idx(i, j + 1)])])
    c = nodes[tris].mean(axis=1)
    j_elem = mms_source(law, c[:, 0], c[:, 1])
    m = len(tris)
    on_boundary = np.flatnonzero((nodes[:, 0] % 1.0 == 0) | (nodes[:, 1] % 1.0 == 0))
    winding = Winding(tuple(f"e{k}" for k in range(m)), ("c",), j_elem[:, None], 1, False)
    return Magnetostatic2D(
        nodes=nodes, triangles=tris, element_law=np.zeros(m, np.int64), laws=(law,),
        element_region=np.zeros(m, np.int64), region_names=("square",), region_kind={"square": "stator_iron"},
        element_coil=np.arange(m), winding=winding, currents=np.array([1.0]), dirichlet_nodes=on_boundary,
        depth=1.0,
    )
```

Create `tests/solvers/test_newton.py`:

```python
import dataclasses

import numpy as np
import pytest

from fem_fixtures import toroid_problem
from srmcore.fields.solution import SolveStatus
from srmcore.materials.laws import LinearLaw, library_law
from srmcore.solvers import skfem_reference
from srmcore.solvers.settings import NewtonSettings
from srmcore.solvers.skfem_reference import SkfemReference

M19 = library_law("M19")


def _small(law, current):
    return toroid_problem(law, current, n_theta=48, layers_per_mm=1)


def test_zero_current_gives_zero_field_without_iterating():
    s = SkfemReference().solve(_small(M19, 0.0), initial=np.ones(len(_small(M19, 0.0).nodes)))
    assert s.status is SolveStatus.OK and s.iterations == 0
    assert not np.any(s.a) and s.energy == 0.0 and s.coenergy == 0.0


def test_linear_problem_is_one_solve_with_equal_energies():
    s = SkfemReference().solve(_small(LinearLaw(1000.0), 100.0))
    assert s.status is SolveStatus.OK and s.iterations == 1 and s.residual < 1e-10
    assert s.energy == pytest.approx(s.coenergy, rel=1e-12)


def test_nonlinear_solve_meets_both_tolerances():
    s = SkfemReference().solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.OK and not s.fallbacks
    assert s.residual < 1e-8 and s.delta_a < 1e-8


def test_initial_guess_from_another_mesh_is_rejected():
    with pytest.raises(ValueError, match="initial guess"):
        SkfemReference().solve(_small(M19, 100.0), initial=np.zeros(7))


def test_continuation_from_a_nearby_solution_converges():
    solver = SkfemReference()
    p = _small(M19, 2000.0)
    first = solver.solve(p)
    again = solver.solve(p.with_currents([2100.0]), initial=first.a)
    assert again.status is SolveStatus.OK


def test_tangent_matches_finite_differences():
    p = _small(M19, 20000.0)
    solver = SkfemReference()
    a = 0.7 * solver.solve(p).a
    r0, tangent = solver.linearize(p, a)
    rng = np.random.default_rng(0)
    v = rng.standard_normal(len(a))
    v[p.dirichlet_nodes] = 0.0
    v *= np.linalg.norm(a) / np.linalg.norm(v)
    eps = 1e-5
    fd = (solver.linearize(p, a + eps * v)[0] - solver.linearize(p, a - eps * v)[0]) / (2 * eps)
    free = np.setdiff1d(np.arange(len(a)), p.dirichlet_nodes)
    assert np.linalg.norm((fd - tangent @ v)[free]) / np.linalg.norm((tangent @ v)[free]) < 1e-5


def test_nonconvergence_is_a_status_not_an_exception():
    s = SkfemReference(NewtonSettings(max_iterations=1)).solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.NONCONVERGED
    assert s.fallbacks == ("damped", "ramp")
    assert s.load_fraction == 1 / NewtonSettings().ramp_steps     # the ramp stopped at its first step
    assert np.all(np.isfinite(s.a))


def test_stalled_line_search_is_not_converged(monkeypatch):
    """If no step reduces the residual, the iterate is not accepted and the solve reports NONCONVERGED."""
    real = skfem_reference._System.residual
    calls = [0]

    def growing(self, a, f):
        r, nu, dnu = real(self, a, f)
        calls[0] += 1
        return r * (1.0 + calls[0]), nu, dnu

    monkeypatch.setattr(skfem_reference._System, "residual", growing)
    s = SkfemReference(NewtonSettings(max_halvings=3, ramp_steps=1)).solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.NONCONVERGED
    assert not np.any(s.a)                  # nothing was accepted from the zero start
    assert np.isfinite(s.residual)


@pytest.mark.parametrize("failures,status,fallbacks", [
    (1, SolveStatus.OK_WITH_FALLBACK, ("damped",)),
    (2, SolveStatus.OK_WITH_FALLBACK, ("damped", "ramp")),
])
def test_fallback_chain_order(monkeypatch, failures, status, fallbacks):
    real = skfem_reference._newton
    calls = []

    def flaky(*args, **kwargs):
        out = real(*args, **kwargs)
        calls.append(out)
        return dataclasses.replace(out, converged=False) if len(calls) <= failures else out

    monkeypatch.setattr(skfem_reference, "_newton", flaky)
    s = SkfemReference().solve(_small(M19, 20000.0))
    assert s.status is status and s.fallbacks == fallbacks and s.load_fraction == 1.0
    assert len(calls) == (2 if failures == 1 else 2 + NewtonSettings().ramp_steps)
```

Create `tests/solvers/test_mms.py`:

```python
"""Method of manufactured solutions on the nonlinear PDE (spec §8.2 suite 2): A = sin(πx)·sin(πy),
ν = ν0·(1 + α·B²). P1 elements must converge at rate 2 in L2 and rate 1 in the H1 seminorm."""
import math

import numpy as np
import pytest

from fem_fixtures import QuadraticLaw, mms_exact, mms_problem
from srmcore.fields.solution import SolveStatus
from srmcore.physics.fem import triangle_areas
from srmcore.solvers.skfem_reference import SkfemReference


def _errors(n: int) -> tuple[float, float]:
    law = QuadraticLaw(nu0=1.0, alpha=1.0)
    p = mms_problem(law, n)
    s = SkfemReference().solve(p)
    assert s.status is SolveStatus.OK
    area = triangle_areas(p.nodes, p.triangles)
    err = s.a - mms_exact(p.nodes[:, 0], p.nodes[:, 1])
    l2 = math.sqrt(float(area @ (err[p.triangles] ** 2).mean(axis=1)))
    c = p.nodes[p.triangles].mean(axis=1)
    ax = math.pi * np.cos(math.pi * c[:, 0]) * np.sin(math.pi * c[:, 1])
    ay = math.pi * np.sin(math.pi * c[:, 0]) * np.cos(math.pi * c[:, 1])
    h1 = math.sqrt(float(area @ ((s.b[:, 0] - ay) ** 2 + (s.b[:, 1] + ax) ** 2)))
    return l2, h1


def test_mms_convergence_rates():
    errors = [_errors(n) for n in (8, 16, 32)]
    for (l2a, h1a), (l2b, h1b) in zip(errors[:-1], errors[1:]):
        assert math.log2(l2a / l2b) == pytest.approx(2.0, abs=0.15)
        assert math.log2(h1a / h1b) == pytest.approx(1.0, abs=0.1)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/solvers -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'srmcore.fields.solution'` (collection error in both files).

- [ ] **Step 4: Implement**

`src/srmcore/fields/solution.py`:

```python
"""Solver output (spec §6), as plain numpy data."""
from dataclasses import dataclass
from enum import Enum

import numpy as np


class SolveStatus(str, Enum):
    OK = "OK"
    OK_WITH_FALLBACK = "OK_WITH_FALLBACK"
    NONCONVERGED = "NONCONVERGED"


@dataclass(frozen=True, eq=False)
class FieldSolution:
    a: np.ndarray            # A_z per node, Wb/m
    b: np.ndarray            # (n_elements, 2) flux density per element, T, stator (global) frame
    nu: np.ndarray           # reluctivity per element, m/H
    dnu_db2: np.ndarray      # differential reluctivity dν/d(B²) per element
    energy: float            # W = L·∫∫0^B H dB dS, J
    coenergy: float          # W' = L·∫∫0^H B dH dS, J
    status: SolveStatus
    iterations: int
    residual: float          # final relative residual
    delta_a: float           # final relative Newton update
    fallbacks: tuple[str, ...] = ()
    # Fraction of the requested circuit currents this field was solved for. Below 1 only when the
    # current ramp stopped early (status NONCONVERGED); never build a ψ-i table from such a field.
    load_fraction: float = 1.0
```

`src/srmcore/physics/energy.py`:

```python
"""Stored energy and co-energy of a solved field, identical for every solver adapter."""
import numpy as np

from .fem import triangle_areas
from .problem import Magnetostatic2D


def field_energies(problem: Magnetostatic2D, b: np.ndarray) -> tuple[float, float]:
    """(W, W') in joules: depth × Σ_elements area × ∫0^B H dB, and × ∫0^H B dH."""
    bm = np.hypot(b[:, 0], b[:, 1])
    area = triangle_areas(problem.nodes, problem.triangles)
    w = wc = 0.0
    for k, law in enumerate(problem.laws):
        idx = np.flatnonzero(problem.element_law == k)
        if len(idx) == 0:
            continue
        w += float(law.energy_density(bm[idx]) @ area[idx])
        wc += float(law.coenergy_density(bm[idx]) @ area[idx])
    return problem.depth * w, problem.depth * wc
```

`src/srmcore/solvers/settings.py`:

```python
"""Newton settings pinned across adapters (spec §6), and the adapter protocol."""
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..fields.solution import FieldSolution
from ..physics.problem import Magnetostatic2D

# Element order and quadrature rule every adapter must use, so cross-solver comparisons (M3) compare
# the same discretisation.
ELEMENT_ORDER = 1
QUADRATURE_ORDER = 2


@dataclass(frozen=True)
class NewtonSettings:
    residual_tol: float = 1e-8       # ||r_free|| / ||f_free||
    delta_tol: float = 1e-8          # ||ΔA|| / ||A||
    max_iterations: int = 50
    max_halvings: int = 20
    damped_max_step: float = 0.5     # step cap of the "damped" fallback until the residual is below 1e-2
    ramp_steps: int = 4              # current sub-steps of the "ramp" fallback


class SolverAdapter(Protocol):
    name: str

    def solve(self, problem: Magnetostatic2D, initial: np.ndarray | None = None) -> FieldSolution:
        """Never raises for non-convergence: returns status NONCONVERGED instead (spec §6)."""
        ...
```

`src/srmcore/solvers/skfem_reference.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/solvers tests/test_import_rules.py -q`
Expected: PASS (in about 10 s). The MMS rates come out as 2.00 in L2 and 1.00 in H1.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .github/workflows/ci.yml tests/test_import_rules.py src/srmcore/fields/solution.py src/srmcore/physics/energy.py src/srmcore/solvers tests/fem_fixtures.py tests/solvers
git commit -m "feat(solvers): scikit-fem reference Newton solver with consistent Jacobian and fallback chain" -m "<trailers>"
```

---

### Task 6: Flux linkage and the analytic toroid

**Review:** Sonnet.

**Files:**
- Create: `src/srmcore/post/quantities.py` (`flux_linkage` only; Task 7 adds the rest)
- Create: `tests/post/test_toroid.py`

**Interfaces:**
- Consumes: `Magnetostatic2D` (Task 4); `FieldSolution`, `SkfemReference`, `tests/fem_fixtures.py` (Task 5); `process_bh`, `BHTable`, `library_law` (Tasks 2–3).
- Produces: `flux_linkage(problem, solution) -> ndarray (n_circuits,)`, ψ_k = L·Σ_s C_sk·∫_s A dA, in Wb-turns.

The toroid has a current sheet +I at r ∈ [10, 11] mm, an iron ring at [12, 20] mm and a sheet −I at [21, 22] mm, with A = 0 at 30 mm. Between the sheets H = I/(2πr) exactly, whatever the material, so B in the iron and ψ follow from 1D integrals. The tests cover M19 up to 5 T (spec: "toroid … deep into saturation") and a synthetic CoFe-like curve (μr ≈ 20000, knee at 2.35 T) for spec §6's initial-permeability stiffness test.

- [ ] **Step 1: Write the failing tests**

Create `tests/post/test_toroid.py`:

```python
"""Current-sheet toroid (spec §8.2 suite 2): between the sheets H = I/(2πr) exactly, so B, A and ψ are
known in closed form up to a 1D integral, deep into saturation."""
import math

import numpy as np
import pytest

import fem_fixtures as F
from srmcore.fields.solution import SolveStatus
from srmcore.materials.bh import process_bh
from srmcore.materials.laws import library_law
from srmcore.materials.schema import BHTable
from srmcore.model.constants import MU0
from srmcore.post.quantities import flux_linkage
from srmcore.solvers.skfem_reference import SkfemReference


def _cofe_like():
    """Synthetic CoFe-like curve: μr ≈ 20000 initially, sharp knee at 2.35 T."""
    h = np.logspace(-1, 5.5, 40)
    b = 2.35 * np.tanh(MU0 * 20000 * h / 2.35) + MU0 * h
    curve, report = process_bh(BHTable(h=tuple(h), b=tuple(b)), 1.0, 2.40)
    assert report.initial_relative_permeability > 15000
    return curve


def _b_of_h(curve, h):
    grid = np.linspace(0.0, 10.0, 400_001)
    return np.interp(h, curve.h_of_b(grid), grid)


def _exact_psi(curve, current):
    """ψ = L·[mean A over the inner sheet - mean A over the outer sheet], A(r) = ∫_r^R B_θ ds."""
    r = np.linspace(1e-6, F.R_OUTER, 400_001)
    (a1, b1), (a2, b2) = F.SHEET_IN, F.SHEET_OUT
    enclosed = current * np.clip((r**2 - a1**2) / (b1**2 - a1**2), 0, 1) \
        - current * np.clip((r**2 - a2**2) / (b2**2 - a2**2), 0, 1)
    h = enclosed / (2 * math.pi * r)
    iron = (r > F.IRON[0]) & (r < F.IRON[1])
    b = np.where(iron, _b_of_h(curve, h), MU0 * h)
    seg = 0.5 * (b[1:] + b[:-1]) * np.diff(r)
    a = np.concatenate([np.cumsum(seg[::-1])[::-1], [0.0]])      # A(R_OUTER) = 0

    def mean_a(lo, hi):
        m = (r >= lo) & (r <= hi)
        return np.trapezoid(a[m] * r[m], r[m]) / np.trapezoid(r[m], r[m])

    return F.DEPTH * (mean_a(a1, b1) - mean_a(a2, b2))


def _solve(curve, current):
    p = F.toroid_problem(curve, current, n_theta=96, layers_per_mm=2)
    s = SkfemReference().solve(p)
    return p, s


@pytest.mark.parametrize("current", [50.0, 2000.0, 20000.0, 200000.0], ids=["1.4T", "1.9T", "2.3T", "5T"])
def test_m19_toroid_b_and_flux_linkage(current):
    curve = library_law("M19")
    p, s = _solve(curve, current)
    assert s.status is SolveStatus.OK
    iron = p.element_law == 1
    r = np.hypot(*p.nodes[p.triangles[iron]].mean(axis=1).T)
    b_exact = _b_of_h(curve, current / (2 * math.pi * r))
    assert np.max(np.abs(np.hypot(*s.b[iron].T) - b_exact) / b_exact) < 0.01
    psi = flux_linkage(p, s)[0]
    assert psi == pytest.approx(_exact_psi(curve, current), rel=1e-2)
    # Energy identity W + W' = ψ·i (spec §7.3), with W and W' integrated independently of ψ.
    assert s.energy + s.coenergy == pytest.approx(psi * current, rel=1e-8)


@pytest.mark.parametrize("current", [1.0, 5.0, 50.0, 500.0, 5000.0])
def test_high_initial_permeability_stiffness(current):
    """Spec §6: initial-permeability stiffness (CoFe) must converge, including through the knee."""
    curve = _cofe_like()
    p, s = _solve(curve, current)
    assert s.status in (SolveStatus.OK, SolveStatus.OK_WITH_FALLBACK)
    assert s.residual < 1e-8
    iron = p.element_law == 1
    r = np.hypot(*p.nodes[p.triangles[iron]].mean(axis=1).T)
    b_exact = _b_of_h(curve, current / (2 * math.pi * r))
    assert np.max(np.abs(np.hypot(*s.b[iron].T) - b_exact) / b_exact) < 0.02


def test_cofe_current_sweep_with_continuation():
    curve = _cofe_like()
    p = F.toroid_problem(curve, 0.0, n_theta=96, layers_per_mm=2)
    solver, a = SkfemReference(), None
    for current in (1.0, 5.0, 20.0, 50.0, 200.0, 500.0):
        s = solver.solve(p.with_currents([current]), initial=a)
        assert s.status is SolveStatus.OK
        a = s.a
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/post/test_toroid.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'srmcore.post.quantities'`.

- [ ] **Step 3: Implement**

`src/srmcore/post/quantities.py`:

```python
"""Per-point post-processing (spec §7.1): flux linkage per circuit."""
import numpy as np

from ..fields.solution import FieldSolution
from ..physics.fem import triangle_areas
from ..physics.problem import Magnetostatic2D


def flux_linkage(problem: Magnetostatic2D, solution: FieldSolution) -> np.ndarray:
    """ψ_k = L·Σ_s C_sk·∫_s A dA per circuit, Wb-turns. ∫A dA on a P1 triangle = area × mean nodal A."""
    in_coil = np.flatnonzero(problem.element_coil >= 0)
    tri = problem.triangles[in_coil]
    integral = triangle_areas(problem.nodes, tri) * solution.a[tri].mean(axis=1)
    per_side = np.bincount(problem.element_coil[in_coil], weights=integral,
                           minlength=len(problem.winding.coil_sides))
    return problem.depth * problem.winding.matrix.T @ per_side
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/post/test_toroid.py tests/test_import_rules.py -q`
Expected: PASS (in about 15 s). The measured margins were a B error ≤ 0.44 % (M19) and ≤ 0.70 % (CoFe), and a ψ error ≤ 0.31 %, against tolerances of 1 %, 2 % and 1 %.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/post/quantities.py tests/post/test_toroid.py
git commit -m "feat(post): flux linkage per circuit, validated on the nonlinear current-sheet toroid" -m "<trailers>"
```

---

### Task 7: Arkkio torque, saturation report and 8/6 machine checks

**Review:** Opus. Check the Arkkio integrand and sign convention, the quadrature, the percentile weighting and the test tolerances against the trial findings.

**Files:**
- Modify: `src/srmcore/post/quantities.py` (add `arkkio_torque`, `SaturationStats`, `saturation_report`)
- Create: `tests/post/test_machine_8_6.py`
- Create: `examples/solve_8_6.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above; `MachineMesh` band radii through `BandInfo` (Task 4).
- Produces:
  - `arkkio_torque(problem, solution) -> float`. T = L/(μ0·(r_out − r_in))·∫_band r·B_r·B_θ dS, in N·m, positive when counter-clockwise on the rotor. It uses the degree-2 edge-midpoint rule on each band triangle, and raises `ValueError` when `problem.band is None`.
  - `SaturationStats(peak, p95, p99)`, where p95 and p99 are area-weighted percentiles.
  - `saturation_report(problem, solution, machine: RadialSRMParams) -> dict[str, SaturationStats]`. Its keys are every region name plus `stator_yoke`/`stator_poles` (split at `stator_yoke_inner_radius`) and `rotor_yoke`/`rotor_poles` (split at `rotor_yoke_outer_radius`), computed from element centroids.

Sign convention: `mesh_at_angle(static, θ)` rotates the rotor counter-clockwise by θ, and phase A is aligned at θ = 0. For 0 < θ < π/Nr, phase A pulls the rotor back, so T < 0. At θ = 0, phase D gives T > 0 and phase B gives T < 0, so counter-clockwise motoring excites A → D → C → B. `test_phase_sequence_for_counter_clockwise_motoring` pins this for the drive work.

The tolerances rely on Task 1's mirror-symmetric band. Measured in the trial: T(aligned) = 0.023 % and T(+10°) + T(−10°) = 0.017 % of |T(10°)| (tolerance 0.2 %), and linear Arkkio vs dW′/dθ = 0.26 % (tolerance 1 %). The deep-saturation sweep (to 160 A) and the outer-ring solve are `slow`.

- [ ] **Step 1: Write the failing tests**

Create `tests/post/test_machine_8_6.py`:

```python
"""8/6 reference machine, screening mesh: zero current, linear Arkkio = co-energy, torque sign and
symmetry, energy identity, La/Lu band, saturation report, and the outer air ring."""
import dataclasses
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.fields.solution import SolveStatus
from srmcore.materials.laws import VACUUM, LinearLaw
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, saturation_report
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


@pytest.fixture(scope="module")
def solve(static):
    """solve(angle_in_band_pitches, amps_on_A, linear=False) -> (problem, solution), memoised."""
    cache = {}
    solver = SkfemReference()

    def run(k: int, amps: float, linear: bool = False, phase: str = "A"):
        key = (k, amps, linear, phase)
        if key not in cache:
            p = machine_problem(mesh_at_angle(static, k * static.settings.band_pitch), DESIGN, {phase: amps})
            if linear:
                p = dataclasses.replace(p, laws=tuple(law if law is VACUUM else LinearLaw(1000.0) for law in p.laws))
            cache[key] = (p, solver.solve(p))
        return cache[key]

    return run


def _pitches(static, degrees: float) -> int:
    k = math.radians(degrees) / static.settings.band_pitch
    assert abs(k - round(k)) < 1e-9, "test angles must sit on the band grid"
    return round(k)


def test_zero_current(solve):
    p, s = solve(0, 0.0)
    assert s.status is SolveStatus.OK
    assert np.all(flux_linkage(p, s) == 0) and arkkio_torque(p, s) == 0.0


def test_linear_arkkio_equals_coenergy_derivative(static, solve):
    k0, dk = _pitches(static, 10.0), 4
    p, s = solve(k0, 10.0, linear=True)
    dwc = (solve(k0 + dk, 10.0, linear=True)[1].coenergy - solve(k0 - dk, 10.0, linear=True)[1].coenergy) \
        / (2 * dk * static.settings.band_pitch)
    assert arkkio_torque(p, s) == pytest.approx(dwc, rel=0.01)       # trial: 0.26 %
    assert s.energy == pytest.approx(s.coenergy, rel=1e-12)


def test_torque_sign_symmetry_and_aligned_zero(static, solve):
    k = _pitches(static, 10.0)
    t_pos = arkkio_torque(*solve(k, 10.0))
    t_neg = arkkio_torque(*solve(-k, 10.0))
    t_aligned = arkkio_torque(*solve(0, 10.0))
    assert t_pos < 0 < t_neg                         # the rotor is pulled back towards alignment
    # Spec §8.3 zero-torque criterion is 1 %; the mirror-symmetric band gives ~0.02 % (trial).
    assert abs(t_pos + t_neg) < 0.002 * abs(t_pos)
    assert abs(t_aligned) < 0.002 * abs(t_pos)


def test_phase_sequence_for_counter_clockwise_motoring(solve):
    """At θ = 0 (A aligned), D pulls the rotor counter-clockwise and B clockwise, so counter-clockwise
    motoring excites A → D → C → B. The drive side (sub-project #4) relies on this convention."""
    t_d = arkkio_torque(*solve(0, 10.0, phase="D"))
    t_b = arkkio_torque(*solve(0, 10.0, phase="B"))
    assert t_d > 0 > t_b
    assert t_d == pytest.approx(-t_b, rel=0.02)


def test_energy_identity_and_status(solve):
    p, s = solve(0, 20.0)
    assert s.status is SolveStatus.OK
    psi = flux_linkage(p, s)
    assert s.energy + s.coenergy == pytest.approx(psi[0] * 20.0, rel=1e-8)
    assert psi[1] == pytest.approx(-psi[3], rel=1e-3)   # B and D are mirror images about phase A's axis


def test_aligned_to_unaligned_inductance_ratio(static, solve):
    psi_a = flux_linkage(*solve(0, 5.0))[0]
    psi_u = flux_linkage(*solve(_pitches(static, 30.0), 5.0))[0]
    assert 3.0 < psi_a / psi_u < 15.0                 # spec §7.3 "normal" La/Lu band


def test_saturation_report(solve):
    p, s = solve(0, 20.0)
    report = saturation_report(p, s, DESIGN.machine)
    for group in ("stator_iron", "rotor_iron", "shaft", "stator_poles", "stator_yoke", "rotor_poles", "rotor_yoke"):
        stats = report[group]
        assert stats.peak >= stats.p99 >= stats.p95 > 0
    assert report["stator_poles"].p95 > report["stator_yoke"].p95


@pytest.mark.slow
def test_deep_saturation_sweep(solve):
    """ψ(i) stays monotone and odd up to 160 A (stator pole tips well past the last B-H point)."""
    psi = [flux_linkage(*solve(0, amps))[0] for amps in (10.0, 40.0, 80.0, 160.0)]
    assert all(solve(0, amps)[1].status is SolveStatus.OK for amps in (10.0, 40.0, 80.0, 160.0))
    assert np.all(np.diff(psi) > 0)
    assert flux_linkage(*solve(0, -40.0))[0] == pytest.approx(-psi[1], rel=1e-9)


@pytest.mark.slow
def test_outer_air_ring_moves_the_zero_potential():
    ring = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening", outer_air_thickness=0.004))
    m = mesh_at_angle(build_machine_mesh(ring), 0.0)
    p = machine_problem(m, ring, {"A": 20.0})
    s = SkfemReference().solve(p)
    assert s.status is SolveStatus.OK
    r = np.hypot(m.nodes[:, 0], m.nodes[:, 1])
    on_od = np.isclose(r, DESIGN.machine.stator_outer_radius, rtol=1e-9)
    assert on_od.sum() > 0 and np.max(np.abs(s.a[on_od])) > 0
    assert np.all(s.a[p.dirichlet_nodes] == 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/post/test_machine_8_6.py -q`
Expected: FAIL with `ImportError: cannot import name 'arkkio_torque' from 'srmcore.post.quantities'`.

- [ ] **Step 3: Implement**

Replace `src/srmcore/post/quantities.py` with:

```python
"""Per-point post-processing (spec §7.1): flux linkage per circuit, Arkkio torque, saturation report."""
from dataclasses import dataclass

import numpy as np

from ..fields.solution import FieldSolution
from ..model.constants import MU0
from ..model.design import RadialSRMParams
from ..physics.fem import triangle_areas
from ..physics.problem import Magnetostatic2D

# Degree-2 rule on a triangle: the three edge midpoints, equal weights 1/3.
_MIDPOINTS = np.array([[0.5, 0.5, 0.0], [0.0, 0.5, 0.5], [0.5, 0.0, 0.5]])


def flux_linkage(problem: Magnetostatic2D, solution: FieldSolution) -> np.ndarray:
    """ψ_k = L·Σ_s C_sk·∫_s A dA per circuit, Wb-turns. ∫A dA on a P1 triangle = area × mean nodal A."""
    in_coil = np.flatnonzero(problem.element_coil >= 0)
    tri = problem.triangles[in_coil]
    integral = triangle_areas(problem.nodes, tri) * solution.a[tri].mean(axis=1)
    per_side = np.bincount(problem.element_coil[in_coil], weights=integral,
                           minlength=len(problem.winding.coil_sides))
    return problem.depth * problem.winding.matrix.T @ per_side


def arkkio_torque(problem: Magnetostatic2D, solution: FieldSolution) -> float:
    """T = L / (μ0·(r_out - r_in)) · ∫_band r·B_r·B_θ dS, N·m, positive counter-clockwise on the rotor."""
    if problem.band is None:
        raise ValueError("Arkkio torque needs a moving band (problem.band is None)")
    el = problem.band.elements
    tri = problem.triangles[el]
    bx, by = solution.b[el, 0], solution.b[el, 1]
    corners = problem.nodes[tri]                                  # (n, 3, 2)
    total = np.zeros(len(el))
    for weights in _MIDPOINTS:
        p = np.einsum("j,njk->nk", weights, corners)
        x, y = p[:, 0], p[:, 1]
        r = np.hypot(x, y)
        total += (bx * x + by * y) * (-bx * y + by * x) / r / 3   # r·B_r·B_θ
    integral = float(total @ triangle_areas(problem.nodes, tri))
    return problem.depth * integral / (MU0 * (problem.band.outer_radius - problem.band.inner_radius))


@dataclass(frozen=True)
class SaturationStats:
    peak: float
    p95: float
    p99: float


def _stats(bm: np.ndarray, area: np.ndarray) -> SaturationStats:
    order = np.argsort(bm)
    cum = np.cumsum(area[order]) / area.sum()
    pick = lambda q: float(bm[order][min(np.searchsorted(cum, q), len(bm) - 1)])  # noqa: E731
    return SaturationStats(peak=float(bm.max()), p95=pick(0.95), p99=pick(0.99))


def saturation_report(problem: Magnetostatic2D, solution: FieldSolution,
                      machine: RadialSRMParams) -> dict[str, SaturationStats]:
    """|B| peak and area-weighted 95th/99th percentiles per region, plus the iron split into poles and
    yokes by radius (stator yoke: r > stator_yoke_inner_radius; rotor yoke: r < rotor_yoke_outer_radius)."""
    bm = np.hypot(solution.b[:, 0], solution.b[:, 1])
    area = triangle_areas(problem.nodes, problem.triangles)
    centroid_r = np.hypot(*problem.nodes[problem.triangles].mean(axis=1).T)
    report: dict[str, SaturationStats] = {}
    groups: dict[str, np.ndarray] = {}
    for rid, name in enumerate(problem.region_names):
        groups[name] = problem.element_region == rid
    kind = np.array([problem.region_kind[n] for n in problem.region_names])[problem.element_region]
    stator, rotor = kind == "stator_iron", kind == "rotor_iron"
    groups["stator_yoke"] = stator & (centroid_r > machine.stator_yoke_inner_radius)
    groups["stator_poles"] = stator & (centroid_r <= machine.stator_yoke_inner_radius)
    groups["rotor_yoke"] = rotor & (centroid_r < machine.rotor_yoke_outer_radius)
    groups["rotor_poles"] = rotor & (centroid_r >= machine.rotor_yoke_outer_radius)
    for name, mask in groups.items():
        if mask.any():
            report[name] = _stats(bm[mask], area[mask])
    return report
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/post -q`
Expected: PASS for the fast tests (in about 45 s). Then run `.venv\Scripts\python -m pytest tests/post -m slow -q` and expect it to pass too (the deep-saturation sweep and the outer ring). La/Lu at 5 A is 9.5.

- [ ] **Step 5: Add the runnable example**

Create `examples/solve_8_6.py`:

```python
"""Solve the 8/6 SRM magnetostatically at the aligned and unaligned positions and print ψ, torque,
energies and the saturation report.

Run from the repo root:  .venv\\Scripts\\python examples\\solve_8_6.py [screening|full]
"""
import math
import sys
import time

from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, saturation_report
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
static = build_machine_mesh(design)
solver = SkfemReference()
for label, theta in (("aligned", 0.0), ("unaligned", math.pi / machine.n_rotor_poles), ("10 deg", math.radians(10.0))):
    mesh = mesh_at_angle(static, theta)
    problem = machine_problem(mesh, design)
    a = None
    print(f"--- {label} ({mesh.rotor_angle:.4f} rad)")
    for amps in (5.0, 10.0, 20.0):
        p = problem.with_currents([amps, 0.0, 0.0, 0.0])
        start = time.perf_counter()
        s = solver.solve(p, initial=a)
        seconds = time.perf_counter() - start
        a = s.a
        print(f"  i={amps:5.1f} A  {s.status.value:<16} it={s.iterations:2d} {seconds:5.1f}s  psi_A={flux_linkage(p, s)[0]:.5f} Wb  "
              f"T={arkkio_torque(p, s):+.4f} Nm  W={s.energy:.4f} J  W'={s.coenergy:.4f} J")
    peaks = {k: round(v.peak, 3) for k, v in saturation_report(p, s, machine).items()
             if k in ("stator_poles", "stator_yoke", "rotor_poles", "rotor_yoke")}
    print(f"  peak |B| at 20 A: {peaks}")
```

Run: `.venv\Scripts\python examples\solve_8_6.py`
Expected: three blocks (aligned, unaligned, 10 deg), all with status `OK` and a solve time per line (the speed baseline for the M3 go/no-go). For aligned at 5 A, psi_A should be about 0.170 Wb. At 10 deg and 10 A, T should be about −4.01 Nm.

- [ ] **Step 6: Update CLAUDE.md**

In `CLAUDE.md`, replace the paragraph that starts `**Current state:** M1 (geometry and mesh) is complete.` with:

```markdown
**Current state:** M1 (geometry and mesh) and M2 (materials and nonlinear magnetostatics) are complete. `maps` and `project` are still empty placeholders for later milestones (M3: NGSolve adapter go/no-go; M4: maps; M5: validation).
```

Add this line to the Commands block, after the `examples\mesh_8_6.py` line:

```
python examples\solve_8_6.py [screening|full]        # solve an 8/6 and print psi, torque, energies, saturation
```

After the "Pipeline (M1)" section, add:

```markdown
## Solve pipeline (M2)

1. **`materials/`**: `load_material(name)` reads `materials/data/<name>.json`. `process_bh` checks units, adds the origin, applies the stacking factor, requires J = B − μ0·H to be non-decreasing, and builds a monotone Hermite H(B) with a C¹ tail towards Js. `library_law(name)` returns the cached `ReluctivityLaw`; conductors and air use `LinearLaw`/`VACUUM`.
2. **`physics/build.py` `machine_problem(mesh, design, currents)`**: assigns laws by `region_kind` through `RegionMaterials`, builds the connection matrix from `CoilInfo` (`physics/winding.py`), takes Dirichlet nodes from `outer_edges` and band info from the mesh. It never parses region names.
3. **`solvers/skfem_reference.py` `SkfemReference().solve(problem, initial=None)`**: P1, quadrature order 2, Newton with the consistent Jacobian, and both residual and ΔA < 1e-8. On failure it falls back to damped Newton, then a current ramp, then `NONCONVERGED`; it never raises. It returns a `FieldSolution` (`fields/solution.py`) with A, element B, ν and energies.
4. **`post/quantities.py`**: `flux_linkage`, `arkkio_torque` (band radii from the mesh; positive counter-clockwise) and `saturation_report`. Phase A is aligned at θ = 0, and counter-clockwise motoring excites A → D → C → B.

Analytic test problems (the current-sheet toroid and MMS on the unit square) live in `tests/fem_fixtures.py`. Test file basenames must be unique, because `tests/` has no `__init__.py`.
```

- [ ] **Step 7: Run the full fast suite**

Run: `.venv\Scripts\python -m pytest -m "not slow" -q`
Expected: all pass, in under 10 minutes (about 2.5 minutes locally).

- [ ] **Step 8: Commit**

```bash
git add src/srmcore/post/quantities.py tests/post/test_machine_8_6.py examples/solve_8_6.py CLAUDE.md
git commit -m "feat(post): Arkkio torque and saturation report; 8/6 machine checks and solve demo" -m "<trailers>"
```

---

## M2 exit check

- [ ] Run: `.venv\Scripts\python -m pytest -m "not slow"`. Everything is green, in under 10 minutes.
- [ ] Run: `.venv\Scripts\python -m pytest -m slow`. Everything is green (M1's slow tests; M2 adds none).
- [ ] CI on the branch is green (Windows + Linux, Python 3.12 and 3.14). scikit-fem installs from PyPI on both platforms.
- [ ] Run `examples\solve_8_6.py screening` and `full`, and attach the output to the final review.
- [ ] Spec §9 M2 deliverables each map to a task: material schema (Task 2); B-H pipeline with tail (Task 3); per-region materials (Task 4); skfem_reference linear then nonlinear (Task 5); connection matrix (Task 4); ψ per circuit (Task 6); energies (Task 5); Arkkio at one angle (Task 7); saturation report (Task 7). The M2 tests are: B-H units (Task 3), MMS (Task 5), toroid (Task 6), zero current (Tasks 5 and 7), linear Arkkio = co-energy (Task 7) and CoFe stiffness (Task 6).

## Decisions

The owner delegated every open item to the expert panel (2026-09-29); its rulings are listed at the top of this plan and logged in spec §11 by Task 2. The owner still decides the phase relabelling, which is recorded in spec §10.

## Notes and known risks (carry into M3/M4)

- **Solve speed (M4; spec §10).** About 0.65–1.0 s per Newton iteration at 43k DOF, and 5–13 iterations cold (3–16 s per solve), against §7.2's ≤ 4 s. Options: vectorised P1 assembly with a fixed sparsity pattern, parallel map points (as in Motor-CAD), a tangent predictor, an energy line search, and the structured air-gap meshing already flagged in the M1 notes. `skfem_reference` itself stays as it is; it is the M3 cross-check.
- **Continuation (M4).** A warm start or a scaled start does not reduce iterations; the iteration count comes from pole-tip saturation. M4's sweep runner uses a tangent (Euler) predictor or parallel independent points.
- **Band pitch (M3).** The symmetric band removed the diagonal bias. M3's band-pitch convergence study measures what is left on `full`.
- **First Newton step (M4).** From A = 0 the tangent uses the initial permeability and overshoots badly at high current. The line search handles it (20 halvings); a predictor removes it.
- **Frames.** `FieldSolution.b` is in the stator (global) frame. The own-frame rotor B needed for iron losses (spec §7.1) is a rotation by −θ of the rotor elements. Add it with the replay work, not before.
- **L_inc.** `SkfemReference.linearize` already returns the consistent tangent at the converged state. M4 builds L_inc = ∂ψ/∂i on top of it (spec §7.1).
