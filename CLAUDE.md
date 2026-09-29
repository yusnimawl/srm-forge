# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`srmcore` is the core engine (sub-project #1) of an in-house switched reluctance motor (SRM) design tool. It is a Python library with no UI and no server. The finished engine takes a radial SRM design and produces validated flux-linkage and torque maps. It has to be fast enough for an optimizer to call it.

The authoritative design is `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md`. It covers the architecture, physics, tolerances, milestones M1–M5, open items and the decision log. Read the relevant section before starting milestone work. Implementation plans are in `docs/superpowers/plans/`, and `docs/reference-machines.md` audits which published machines can be used for validation.

**Current state:** M1 (geometry and mesh), M2 (materials and nonlinear magnetostatics), M3 (NGSolve adapter go/no-go) and M4a (`maps/point.py` `solve_point`, phase order A→B→C→D, incremental inductance, solve-speed work) are complete. M4a speed result: a cold `screening` solve at 20 A takes about 4.5–5 s (11 Newton iterations), so the 4 s gate is not met; see `docs/m4-handoff.md`. An Euler current predictor was tried and dropped (spec §10). The owner accepted NGSolve as the primary solver (spec §11); `skfem_reference` stays as the independent cross-check. `maps` and `project` are still empty placeholders for later milestones (M4: maps; M5: validation).

## Commands

The project needs Python 3.12 or newer. CI tests on 3.12 and 3.14, on both Windows and Linux. A `.venv` exists at the repo root.

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ngsolve]"
python -m pytest -m "not slow"                       # fast suite (what CI runs)
python -m pytest                                     # include slow property/quality tests
python -m pytest tests/mesh/test_band.py::test_name  # single test
python examples\mesh_8_6.py [screening|full]         # mesh an 8/6 and save PNG plots
python examples\solve_8_6.py [screening|full]        # solve an 8/6 and print psi, torque, energies, saturation
python examples\band_pitch_convergence.py           # band-pitch convergence table on the 8/6 screening mesh
python examples\team24_check.py                     # TEAM 24 static torque and current rise (needs the ngsolve extra)
```

On Linux, the gmsh wheel needs `libglu1-mesa` (CI also installs `libxcursor1 libxft2 libxinerama1`). There is no linter or formatter configured.

## Architecture rules (enforced by tests)

`tests/test_import_rules.py` parses every source file and fails on forbidden imports (spec §3.2):

| Subpackage | May import (internal) |
|---|---|
| `model` | nothing |
| `materials`, `fields`, `topology` | model |
| `geometry` | model, topology |
| `mesh` | model, geometry |
| `physics` | model, materials, mesh |
| `solvers` / `post` | model, materials, physics, fields |
| `maps` | all of the above |
| `project` | model, maps |

- Only `geometry/` and `mesh/` may import `gmsh`. Only `solvers/` may import `skfem`, `ngsolve` or `netgen`. Top-level modules such as `srmcore/__init__.py` must not import any of `gmsh`, `skfem`, `ngsolve` or `netgen`.
- Layers exchange plain data: numpy arrays, frozen Pydantic models and frozen dataclasses. Never pass Gmsh or solver objects across a layer boundary.
- Everything is in SI units internally (metres, radians, amperes). The validator rejects values that look like millimetres, with rule `units`.

## Pipeline (M1)

`Design` (in `model/design.py`: frozen, `extra="forbid"`, schema-versioned) holds `RadialSRMParams`, `MeshSettings` and `RegionMaterials`. It flows through these steps:

1. **`model/validator.py`**: closed-form checks that run before meshing. They cover Lawrenson feasibility, fit, clearances, units and minimum web width. Errors raise `InputError`, which names the parameter and the rule. Warnings are returned.
2. **`topology/radial.py`**: builds a pure-Python 2D outline from `primitives.py` (lines, arcs, fillets). The outline includes the stator bore, the rotor boundary, coil sides and refinement features (`pole_tip`, `pole_root`). No Gmsh is involved at this stage. Fit failures are converted to `InputError`.
3. **`geometry/build.py`**: turns the outline into Gmsh OCC surfaces with named regions (iron, shaft, coil sides `coil_A1+`/`coil_A1-`, slot air, air-gap layers, band). `geometry/session.py` initialises Gmsh once per process and gives each use a fresh, isolated model. Building a second mesh in the same process must produce an identical result.
4. **`mesh/static.py`**: meshes the stator and the rotor **once**, with the rotor at angle 0, and extracts `StaticMesh`. The iron mesh never changes afterwards, because later loss evaluation needs fixed iron nodes. `mesh/settings.py` resolves presets (`screening`/`full`/`reference`) and the band pitch. `mesh/sizing.py` is the size field.
5. **`mesh/machine.py` `mesh_at_angle`**: rotates the rotor nodes and re-triangulates only the thin moving-band annulus. `band.py` zips two node rings that have the same uniform pitch. Angles are wrapped into [0, 2π). `snap_angle` snaps an angle to the band pitch.
6. **`mesh/quality.py`**: quality report and gate. A failure raises `MeshRejected`, which carries either a `MeshQualityReport` or a `BandRejection`.
7. **`mesh/api.py` `build_machine_mesh`**: the public entry point. It validates, builds the static mesh and quality-gates it at angle 0 and at half a band pitch.

## Solve pipeline (M2)

1. **`materials/`**: `load_material(name)` reads `materials/data/<name>.json`. `process_bh` checks units, adds the origin, applies the stacking factor, requires J = B − μ0·H to be non-decreasing, and builds a monotone Hermite H(B) with a C¹ tail towards Js. `library_law(name)` returns the cached `ReluctivityLaw`; conductors and air use `LinearLaw`/`VACUUM`.
2. **`physics/build.py` `machine_problem(mesh, design, currents)`**: assigns laws by `region_kind` through `RegionMaterials`, builds the connection matrix from `CoilInfo` (`physics/winding.py`), takes Dirichlet nodes from `outer_edges` and band info from the mesh. It never parses region names.
3. **`solvers/skfem_reference.py` `SkfemReference().solve(problem, initial=None)`**: P1, quadrature order 2, Newton with the consistent Jacobian, and both residual and ΔA < 1e-8. On failure it falls back to damped Newton, then a current ramp, then `NONCONVERGED`; it never raises. It returns a `FieldSolution` (`fields/solution.py`) with A, element B, ν and energies.
3b. **`solvers/ngsolve_adapter.py` `NgsolveAdapter().solve(problem, initial=None)`**: the same contract and Newton scheme as `SkfemReference`, with NGSolve assembling the tangent and the load and doing the umfpack solves. The secant residual is `physics.fem.secant_residual` (numpy). ν, dν/dB² and J are element-constant order-0 L2 grid functions; the quadrature rule is pinned to `QUADRATURE_ORDER`. The Newton driver is a deliberate separate copy, so the cross-solver tests compare that numpy stiffness and the NGSolve load and tangent against skfem's assembly, plus the linear solve. NGSolve is the `[ngsolve]` optional extra; its tests use `importorskip`.
4. **`post/quantities.py`**: `flux_linkage`, `arkkio_torque` (band radii from the mesh; positive counter-clockwise), `virtual_work_torque` (nodal-force torque from a virtual rotation of the band nodes at fixed A; agrees with Arkkio to 0.02 % on the 8/6) and `saturation_report`. Phase A is aligned at θ = 0, and counter-clockwise motoring excites A → B → C → D. `incremental_inductance(problem, sensitivity)` returns L_inc = ∂ψ/∂i (H) from the converged tangent.
4b. **`solvers/*` `sensitivity(problem, a)`**: dA/di per circuit (nodes × circuits) from the tangent at A; both adapters implement it and the tests compare it with central differences.
5. **`maps/point.py` `solve_point(static, design, angle, currents, solver, initial=None, keep_field=False, with_l_inc=False)`**: mesh_at_angle → machine_problem → solve → post, returning a frozen `PointResult` (ψ, Arkkio and virtual-work torque, W, W′, status, iterations, optional L_inc). L_inc is withheld unless the solve converged at full load.

Analytic test problems (the current-sheet toroid and MMS on the unit square) live in `tests/fem_fixtures.py`. `tests/team24_fixture.py` builds the TEAM Problem 24 rig as a `Magnetostatic2D`; the finding is in `docs/team24-feasibility.md`. `tests/solvers/test_cross_solver.py` compares the two solvers at 1e-4. Test file basenames must be unique, because `tests/` has no `__init__.py`.

## Tests

- `tests/conftest.py` provides the reference designs as factories `make_8_6`, `make_12_8` and `make_24_16`. Each accepts `**overrides`. The same designs are available as fixtures (`srm_8_6`, …, and the parametrized `reference_design`). `pythonpath = ["tests"]`, so tests can `from conftest import make_8_6`.
- Property tests use hypothesis over a bounded valid-design box. Keep the fast-suite variants deterministic and small, and mark long-running ones `@pytest.mark.slow`.
- The spec sets the CI budget for the fast suite at under 10 minutes.

## Conventions

- Keep comments free of task or plan history. Comments should explain the code as it is now.
- Open owner decisions are tracked in spec §10, for example whether the `self_starting` rule should be an error or a warning, and the provisional `MIN_WEB_WIDTH = 1e-3` m. Leave these behaviours unchanged unless the owner decides. Record decisions in spec §11.
