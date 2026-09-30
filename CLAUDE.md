# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`srmcore` is the core engine (sub-project #1) of an in-house switched reluctance motor (SRM) design tool. It is a Python library with no UI and no server. The finished engine takes a radial SRM design and produces validated flux-linkage and torque maps. It has to be fast enough for an optimizer to call it.

The authoritative design is `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md`. It covers the architecture, physics, tolerances, milestones M1–M5, open items and the decision log. Read the relevant section before starting milestone work. Implementation plans are in `docs/superpowers/plans/`, and `docs/reference-machines.md` audits which published machines can be used for validation.

**Current state:** M1 (geometry and mesh), M2 (materials and nonlinear magnetostatics), M3 (NGSolve adapter go/no-go), M4a (`solve_point`), M4b (map grids, runner, HDF5 dataset and cache, process pool, `build_map`) and M4c (map products: tables, key numbers, §7.3 checks, exports, overlap map, held-out checks, fidelity check) are complete, so M4 is done; M5 (validation) is next and `project` is still an empty placeholder. Speed: a cold `screening` solve at 20 A takes 2.0–2.5 s (gate 4 s met, numpy tangent). The owner decided the M4 open items (spec §11, 2026-09-30): the `screening` grid is 12 angles × 8 currents (peak torque within 0.24 % of `full`), the screening La tolerance is 5 %, the speed budgets are re-baselined to the laptop (`screening` < ~90 s, `full` < 13 min), and the held-out torque limit is 3 % (provisional until M5). See `docs/m4-handoff.md`. The owner accepted NGSolve as the primary solver (spec §11); `skfem_reference` stays as the independent cross-check.

## Commands

The project needs Python 3.12 or newer. CI tests on 3.12 and 3.14, on both Windows and Linux. A `.venv` exists at the repo root. `h5py` (HDF5 map datasets) is a required dependency.

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ngsolve]"
python -m pytest -m "not slow"                       # fast suite (what CI runs)
python -m pytest                                     # include slow property/quality tests
python -m pytest tests/mesh/test_band.py::test_name  # single test
python examples\mesh_8_6.py [screening|full]         # mesh an 8/6 and save PNG plots
python examples\solve_8_6.py [screening|full]        # solve an 8/6 and print psi, torque, energies, saturation
python examples\band_pitch_convergence.py           # band-pitch convergence table on the 8/6 screening mesh
python examples\solve_speed.py [screening|full]     # time cold and warm solves with both solvers
python examples\build_map_8_6.py [workers] [solver] # build and time the 8/6 screening map (I_max 20 A)
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

## Solve pipeline (M2–M4a)

1. **`materials/`**: `load_material(name)` reads `materials/data/<name>.json`. `process_bh` checks units, adds the origin, applies the stacking factor, requires J = B − μ0·H to be non-decreasing, and builds a monotone Hermite H(B) with a C¹ tail towards Js. `library_law(name)` returns the cached `ReluctivityLaw`; conductors and air use `LinearLaw`/`VACUUM`.
2. **`physics/build.py` `machine_problem(mesh, design, currents)`**: assigns laws by `region_kind` through `RegionMaterials`, builds the connection matrix from `CoilInfo` (`physics/winding.py`), takes Dirichlet nodes from `outer_edges` and band info from the mesh. It never parses region names.
3. **`solvers/skfem_reference.py` `SkfemReference().solve(problem, initial=None)`**: P1, quadrature order 2, Newton with the consistent Jacobian, and both residual and ΔA < 1e-8. On failure it falls back to damped Newton, then a current ramp, then `NONCONVERGED`; it never raises. It returns a `FieldSolution` (`fields/solution.py`) with A, element B, ν and energies.
3b. **`solvers/ngsolve_adapter.py` `NgsolveAdapter().solve(problem, initial=None)`**: the same contract and Newton scheme as `SkfemReference`, with the tangent built as numpy element matrices (`physics.fem.tangent_element_matrices`) scattered into NGSolve's sparsity pattern, and NGSolve supplying the load and the umfpack factorisation. `tests/physics/test_tangent_kernel.py` checks the tangent against NGSolve's own assembly. The secant residual is `physics.fem.secant_residual` (numpy). ν, dν/dB² and J are element-constant order-0 L2 grid functions; the quadrature rule is pinned to `QUADRATURE_ORDER`. The Newton driver is a deliberate separate copy, so the cross-solver tests compare the converged solutions (A, energies, ψ, torque), which checks assembly and the linear solve indirectly; the numpy stiffness is checked in `tests/physics/test_p1_kernels.py`. NGSolve is the `[ngsolve]` optional extra; its tests use `importorskip`.
4. **`post/quantities.py`**: `flux_linkage`, `arkkio_torque` (band radii from the mesh; positive counter-clockwise), `virtual_work_torque` (nodal-force torque from a virtual rotation of the band nodes at fixed A; agrees with Arkkio to 0.02 % on the 8/6) and `saturation_report`. Phase A is aligned at θ = 0, and counter-clockwise motoring excites A → B → C → D. `incremental_inductance(problem, sensitivity)` returns L_inc = ∂ψ/∂i (H) from the converged tangent.
4b. **`solvers/*` `sensitivity(problem, a)`**: dA/di per circuit (nodes × circuits) from the tangent at A; both adapters implement it, the adapters are compared with each other, and L_inc is checked against central differences.
5. **`maps/point.py` `solve_point(static, design, angle, currents, solver, initial=None, keep_field=False, with_l_inc=False)`**: mesh_at_angle → machine_problem → solve → post, returning a frozen `PointResult` (ψ, Arkkio and virtual-work torque, W, W′, status, iterations, optional L_inc). L_inc is withheld unless the solve converged at full load.

## Map pipeline (M4b)

1. **`maps/grids.py`**: `angle_grid` (warped, dense at alignment, snapped to the band pitch, one rotor pole pitch) and `current_grid` (power law, dense at low current); `GRID_SIZES` gives the default sizes per fidelity preset.
2. **`maps/run.py` `run_map(static, design, angles, currents, solver_name, excited="A", workers=1, ...)`**: one job per point (each solved from A = 0, highest current first), then `apply_failure_policy` (isolated non-converged points are PCHIP-filled along current and flagged; the map fails with `MapFailed` above 2 % failed points or on a failure at the aligned angle, at zero current or at I_max). It validates `excited` (any phase of the machine; `aligned_angle` validates the letter) and the currents before making a solver. Cancellation returns a partial, unfilled result with `complete=False`.
3. **`maps/dataset.py`**: `provenance` hashes the design, grids, excitation, solver and srmcore version plus the material JSON bytes; `write_map`/`read_map` use HDF5; `cached_map`/`store_map` serve and store complete maps only, and treat foreign-schema files as misses.
4. **`maps/pool.py` `map_ordered`**: spawn `ProcessPoolExecutor`, results in item order, one retry of the unfinished items after a worker crash, then `WorkerCrashed`. `workers <= 1` runs in-process, through the same `_init_worker`. Workers run single-threaded numerics (`OMP/OPENBLAS/MKL_NUM_THREADS=1`, `make_solver(name, threads=1)`).
5. **`maps/api.py` `build_map(design, i_max, solver="ngsolve", excited="A", workers=None, n_angles, n_currents, cache_dir, progress, cancel)`**: grids, provenance, cache lookup, mesh built once in the parent, `run_map`, cache store. `workers=None` means half the logical CPUs.

## Map products (M4c)

1. **`maps/tables.py`**: `angle_spline`, `dpsi_dtheta`, and `drive_tables` (`DriveTables`: inverse i(θ,ψ) and T(θ,ψ) on a saturation-graded ψ grid, flat, monotone, round-trip checked).
2. **`maps/results.py`**: `key_numbers` (`KeyNumbers`: La and Lu as secant values at the lowest non-zero current, peak torque, ψ_max), `inductance_curves`. `grids.aligned_angle` gives each phase's aligned angle.
3. **`maps/checks.py`**: 14 cheap §7.3 checks (`Check`), `analyse_map` returning a `MapReport`. Energy checks warn instead of fail below 16 angles. Limits are provisional (spec §11).
4. **`maps/export.py`**: `export_csv`, `export_mat`.
5. **`maps/overlap.py`** with `api.build_overlap_map`: overlap map, coupling and reciprocity checks; any non-converged point in a complete overlap map raises `MapFailed`.
6. **`maps/fem_checks.py`**: held-out interpolation and band-radius independence (`full`/`reference` only). **`maps/fidelity.py`**: `fidelity_check` (screening vs full).
7. The map and HDF5 dataset also hold energy, L_inc (excited column), per-pole force vectors (`post/forces.py`) and `b_peak`. Every phase can be excited; its angle grid is the phase-A grid shifted by that phase's aligned angle. The pool runs one job per map point, largest current first. `pool.default_workers` is shared by the API and the checks.
8. `tests/maps/test_goldens.py` (slow) compares the 8/6 screening key numbers and check statuses with `goldens_8_6.json`; the regeneration command is in its docstring.

Analytic test problems (the current-sheet toroid and MMS on the unit square) live in `tests/fem_fixtures.py`. `tests/team24_fixture.py` builds the TEAM Problem 24 rig as a `Magnetostatic2D`; the finding is in `docs/team24-feasibility.md`. `tests/solvers/test_cross_solver.py` compares the two solvers at 1e-4. Test file basenames must be unique, because `tests/` has no `__init__.py`.

## Tests

- `tests/conftest.py` provides the reference designs as factories `make_8_6`, `make_12_8` and `make_24_16`. Each accepts `**overrides`. The same designs are available as fixtures (`srm_8_6`, …, and the parametrized `reference_design`). `pythonpath = ["tests"]`, so tests can `from conftest import make_8_6`.
- Property tests use hypothesis over a bounded valid-design box. Keep the fast-suite variants deterministic and small, and mark long-running ones `@pytest.mark.slow`.
- The spec sets the CI budget for the fast suite at under 10 minutes.

## Conventions

- Keep comments free of task or plan history. Comments should explain the code as it is now.
- Open owner decisions are tracked in spec §10, for example whether the `self_starting` rule should be an error or a warning, and the provisional `MIN_WEB_WIDTH = 1e-3` m. Leave these behaviours unchanged unless the owner decides. Record decisions in spec §11.
