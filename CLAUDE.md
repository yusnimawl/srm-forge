# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`srmcore` is the core engine (sub-project #1) of an in-house switched reluctance motor (SRM) design tool. It is a Python library with no UI and no server. The finished engine takes a radial SRM design and produces validated flux-linkage and torque maps. It has to be fast enough for an optimizer to call it.

**Living project doc (owner rule):** the project history lives in the Claude Docs doc "SRM design tool — how it was built: M1–M5, v0, v0b", https://claude.ai/code/artifact/7dc85cd6-a7f2-4bfa-8e35-de2604864d37. Every session that changes the project (a decision, a spike, a task done, a result, a merge, a new milestone or sub-project plan) updates that doc in the same session with the Claude Docs tools: edit the milestone's section (status, results, decisions, figures) and keep the "whole project" table current, with TBD for milestones not yet planned. Read the doc first (`view` since the last rev) so edits by the owner are kept.

The authoritative design is `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md`. It covers the architecture, physics, tolerances, milestones M1–M5, open items and the decision log. Read the relevant section before starting milestone work. Implementation plans are in `docs/superpowers/plans/`, and `docs/reference-machines.md` audits which published machines can be used for validation.

**Current state:** M1 (geometry and mesh), M2 (materials and nonlinear magnetostatics), M3 (NGSolve adapter go/no-go), M4a (`solve_point`), M4b (map grids, runner, HDF5 dataset and cache, process pool, `build_map`) and M4c (map products: tables, key numbers, §7.3 checks, exports, overlap map, held-out checks, fidelity check) are complete, so M4 is done. M5a (mesh convergence study: presets, corner-clustered angle grid, grid sizes, held-out limit 1.7 % with 64 samples, La at 5 % of I_max; `docs/m5a-results.md`) is done, M5b (TEAM 24 comparison, `docs/m5b-team24-results.md`) is done, M5c (FEMM fixtures, `docs/m5c-femm-results.md`) is done; M5d (measured Krishnan 6/4 and the analytic end-winding hook, `docs/m5d-krishnan-results.md`) is done; M5e1 (label logic and uncertainty budget, `maps/validation.py`, srmcore 0.3.0, `docs/superpowers/specs/2026-10-05-m5e1-label-budget-design.md`) is done; M5e2 (library adds, map identity, speed budgets re-baselined 2026-10-06 as `screening` < 430 s, `full` < 44 min and `full` extras < 31 min (measured × 1.25), validation report `docs/validation-report.md`) is done: srmcore 0.4.0 is 2D-verified (called EM-validated until 2026-10-12; `VALIDATED_VERSIONS = ("0.4.0",)`) and the slow suite passed on CI for the `v0.4.0` tag (Windows and Linux; report verdict PASS; `docs/handoff-2026-10-06-post-m5.md`); `project` is still an empty placeholder. v0b-1 (web search: `src/srmweb` API plus the `web/` React app) is merged to main; v0b-2a (cases and analysis plots) is merged to main; v0b-2b (waveforms tab, field plots, stroke animation) is merged to main (srmweb and `web/` 0.3.0; srmcore stays 0.4.0). A v0 end-to-end web path (requirements, candidates, Pareto plot) is designed in `docs/superpowers/specs/2026-09-30-v0-walking-skeleton-design.md`. **From 2026-10-12 the work follows the roadmap R1–R10 in `docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md`** (R1 UI reskin and label rename, R2 DXF round trip, R3 losses, R4 end effects, R5 thermal and rotor stress, R6 what-if tab, R7 recommender, R8 control SIL, R9 ripple optimisation, R10 fabrication package); it replaces v0b-3 and the core spec §1.3 order. Speed: a cold `screening` solve at 20 A takes 2.0–2.5 s (gate 4 s met, numpy tangent). The owner decided the M4 open items (spec §11, 2026-09-30): the 2026-09-30 speed budgets were superseded by the M5e2 ones; M5a superseded the grid sizes, the La tolerance (back to 3 %) and the held-out limit (1.7 %). See `docs/m4-handoff.md`. The owner accepted NGSolve as the primary solver (spec §11); `skfem_reference` stays as the independent cross-check.

`src/srmapp/` holds the requirements-driven search (requirements, wires, candidate generator, stage-1 filter, windings, drive envelope, turns scan, stage-2 evaluation, Pareto set); it imports `srmcore` public modules and `srmcore` never imports it (`tests/app/test_app_layering.py`). Every candidate is mapped once at `REFERENCE_TURNS` over the largest ampere-turns any allowed winding carries; `turns.rescale_turns` gives the exact map at any turn count and `turns.choose_turns` picks the winding: in wire mode (`Requirements.wires` and `phase_current_a` given) the feasible winding with the lowest resistance, in density mode the feasible winding with the most equivalent turns (turns / paths). Windings may use parallel pole paths (a paths of N turns act as N/a turns on the map); `j_limit` caps the conductor RMS current density inside the drive's stroke search, `j_peak_max` (default 2 x `j_limit`) caps the peak density and thus the map range, and a design is feasible when its worst ratio is at least `SearchSettings.resolved_margin`: an explicit `margin`, or 1 + `JS_STEP` + `GRADE_ALLOWANCE` of the worse stator/rotor B-H grade (A 1.02, B 1.05, C 1.12). `SearchSettings.materials` defaults to 10JNEX900 for stator and rotor; candidates take the stator material's lamination thickness. Stage 2 adds the analytic end-winding inductance (`maps.end_winding`, image factor 1.5) to the reference-turns map before the turns scan; it scales with turns², so it stays exact under `rescale_turns`. The on/off grid is 80 x 80. See `docs/superpowers/specs/2026-10-01-v0a2-turns-after-map-design.md` and `docs/superpowers/specs/2026-10-01-rms-paths-grid-margin-design.md`.

## Commands

The project needs Python 3.12 or newer. CI tests on 3.12 and 3.14, on both Windows and Linux. A `.venv` exists at the repo root. `h5py` (HDF5 map datasets) is a required dependency.

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ngsolve,web]"
python -m pytest -m "not slow"                       # fast suite (what CI runs)
python -m pytest                                     # include slow property/quality tests
python -m pytest tests/mesh/test_band.py::test_name  # single test
python examples\mesh_8_6.py [screening|full]         # mesh an 8/6 and save PNG plots
python examples\solve_8_6.py [screening|full]        # solve an 8/6 and print psi, torque, energies, saturation
python examples\band_pitch_convergence.py           # band-pitch convergence table on the 8/6 screening mesh
python examples\solve_speed.py [screening|full]     # time cold and warm solves with both solvers
python examples\build_map_8_6.py [workers] [solver] # build and time the 8/6 screening map (I_max 20 A)
python examples\fidelity_8_6.py                     # screening-vs-full fidelity on 4 variants of the 8/6 (several hours with the M5a presets)
python examples\v0_search.py [n_candidates] [shortlist]   # requirements-driven search on a small budget
python examples\v0_grid_study.py                            # reduced map grids against a 12 x 8 map (set PYTHONPATH=tests)
python examples\v0_angle_check.py [n_candidates] [n_currents]   # stage-2 angle, current and drive-discretisation check at the search defaults (hours)
python examples\mesh_convergence.py run|run-presets|split|report ...   # M5a mesh-convergence study (see its docstring)
python examples\em_validate_8_6.py [workers] [--json PATH]   # 2D-verified checks and uncertainty budget on the 8/6 full map (about 1 h)
python examples\team24_check.py [--json PATH]       # TEAM 24 comparison against the measured tables (NGSolve optional)
$env:PYTHONPATH="tests"; python examples\speed_budget.py [--json PATH]   # time screening and full maps for the speed budgets
python tools\validation_report.py                   # write docs/validation-report.md from docs/validation/ (verdict PASS/PENDING/FAIL, exit 1 on FAIL)
python tools\digitise_bh.py                         # reproduce the traced/read library B-H curves (needs the dev extra, PyMuPDF)
$env:PYTHONPATH="tests"; python tools\femm_fixtures.py <machine> [--level F]   # regenerate a FEMM fixture (Windows, FEMM 4.2, pyfemm; hours)
$env:PYTHONPATH="tests"; python examples\femm_check.py [machine ...] [--json PATH]   # FEMM cross-tool comparison tables
$env:PYTHONPATH="tests"; python examples\krishnan_6_4_check.py [--json PATH]   # measured Krishnan/Materu 6/4 comparison with end-winding correction (about 17 min)
```

Web layer (see "Web layer (v0b)" below):

```powershell
srmweb                                              # or: python -m srmweb (serves the API and web/dist on 127.0.0.1:8000)
cd web; npm ci; npm run dev                         # Vite dev server, /api proxied to 127.0.0.1:8000
cd web; npm run build                               # type-check and build web/dist
cd web; npx vitest run                              # frontend unit tests
python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api   # regenerate web/src/api/schema.ts after an API change
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
4. **`mesh/static.py`**: meshes the stator and the rotor **once**, with the rotor at angle 0, and extracts `StaticMesh`. The iron mesh never changes afterwards, because later loss evaluation needs fixed iron nodes. `mesh/settings.py` resolves presets (`screening` knobs; `full` and `reference` are the same knobs at fixed `MeshSettings.scale`, 2^(-1/2) and 0.25) and the band pitch. `mesh/sizing.py` is the size field.
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
4c. **`post/end_winding.py`** `end_turn_inductance(...)`: analytic end-winding inductance of a coil (Grover partial inductances of the two end overhangs). `image_factor` runs from 1.0 (default, coil in free air, the lower bound) to 2.0 (iron image, the upper bound); reports use the midpoint 1.5. **`maps/end_winding.py`**: `coil_geometry`, `end_winding_inductance(machine, image_factor)` per phase, and `with_end_winding(result, l_end)`, which adds L_end·i to ψ (and the energies and L_inc) after the map. Torque is unchanged; the 2D map and its cache are never altered, and `build_map` does not apply it. 3D iron-end fringing is not modelled.
5. **`maps/point.py` `solve_point(static, design, angle, currents, solver, initial=None, keep_field=False, with_l_inc=False)`**: mesh_at_angle → machine_problem → solve → post, returning a frozen `PointResult` (ψ, Arkkio and virtual-work torque, W, W′, status, iterations, optional L_inc). L_inc is withheld unless the solve converged at full load.

## Map pipeline

1. **`maps/grids.py`**: `angle_grid` (dense at the pole corners, snapped to the band pitch, one rotor pole pitch) and `current_grid` (power law, dense at low current); `GRID_SIZES` gives the default (angles, currents) per fidelity preset: screening 40 × 8, full 48 × 20, reference 120 × 40.
2. **`maps/run.py` `run_map(static, design, angles, currents, solver_name, excited="A", workers=1, ...)`**: one job per point (each solved from A = 0, highest current first), then `apply_failure_policy` (isolated non-converged points are PCHIP-filled along current and flagged; the map fails with `MapFailed` above 2 % failed points or on a failure at the aligned angle, at zero current or at I_max). It validates `excited` (any phase of the machine; `aligned_angle` validates the letter) and the currents before making a solver. Cancellation returns a partial, unfilled result with `complete=False`.
3. **`maps/dataset.py`**: `provenance` hashes the design, the resolved mesh settings, grids, excitation, solver and srmcore version plus the material JSON bytes; `write_map`/`read_map` use HDF5; `cached_map`/`store_map` serve and store complete maps only, and treat foreign-schema files as misses.
4. **`maps/pool.py` `map_ordered`**: spawn `ProcessPoolExecutor`, results in item order, one retry of the unfinished items after a worker crash, then `WorkerCrashed`. `workers <= 1` runs in-process, through the same `_init_worker`. Workers run single-threaded numerics (`OMP/OPENBLAS/MKL_NUM_THREADS=1`, `make_solver(name, threads=1)`).
5. **`maps/api.py` `build_map(design, i_max, solver="ngsolve", excited="A", workers=None, n_angles, n_currents, cache_dir, progress, cancel)`**: grids, provenance, cache lookup, mesh built once in the parent, `run_map`, cache store. `workers=None` means half the logical CPUs.

## Map products

1. **`maps/tables.py`**: `angle_spline`, `dpsi_dtheta`, and `drive_tables` (`DriveTables`: inverse i(θ,ψ) and T(θ,ψ) on a saturation-graded ψ grid, flat, monotone, round-trip checked).
2. **`maps/results.py`**: `key_numbers` (`KeyNumbers`: La and Lu as secant values at 5 % of I_max, peak torque, ψ_max), `inductance_curves`. `grids.aligned_angle` gives each phase's aligned angle.
3. **`maps/checks.py`**: the cheap §7.3 checks (`Check`), `analyse_map` returning a `MapReport`. Energy checks warn instead of fail below 16 angles. Limits are provisional (spec §11).
4. **`maps/export.py`**: `export_csv`, `export_mat`.
5. **`maps/overlap.py`** with `api.build_overlap_map`: overlap map, coupling and reciprocity checks; any non-converged point in a complete overlap map raises `MapFailed`.
6. **`maps/fem_checks.py`**: held-out interpolation and band-radius independence (`full`/`reference` only). **`maps/fidelity.py`**: `fidelity_check` (screening vs full).
7. The map and HDF5 dataset also hold energy, L_inc (excited column), per-pole force vectors (`post/forces.py`) and `b_peak` (area-weighted 99.9th percentile of iron |B|, `point.B_PEAK_QUANTILE`; the `iron_b_peak` check compares it with the last stacked B-H point). Every phase can be excited; its angle grid is the phase-A grid shifted by that phase's aligned angle. The pool runs one job per map point, largest current first. `pool.default_workers` is shared by the API and the checks.
8. `tests/maps/test_goldens.py` (slow) compares the 8/6 screening key numbers and check statuses with `goldens_8_6.json`; the regeneration command is in its docstring.
9. **`maps/validation.py`** `em_validate(design, result, solver="ngsolve", workers=None)` returns `EmValidation(label, checks, budget, engine_version, material_grades)`. The label ("2D-verified") needs every check to pass: `engine_version` (in `VALIDATED_VERSIONS`, `("0.4.0",)`; the validation report gates adding a version), `preset` (the map's preset equals the design's, and is `full` or `reference`), `map_identity` (the map's design hash, `maps.identity.design_hash`, equals the design's), `no_filled_points`, `map_matches_design` (the peak-torque key point solved on the design's mesh equals the map's value within 0.1 %), `point_convergence_psi` / `_torque` (4 key points on `full` vs `reference`: ψ 0.5 %, torque 1 % of peak), the `fem_checks` (including `held_out_converged`, which warns when a held-out solve was skipped), `material_grade` and `budget_finite`. `UncertaintyBudget` has worst-case rows (mesh, material = Js ±2 % plus grade allowance A 0 / B 3 / C 10 %, end effect at image factors 1 and 2, digitisation via `SoftMagneticMaterial.digitisation_error`) relative to the end-winding-corrected key numbers beside the 2D values (the mesh and material rows are rescaled by 2D value / corrected value). When the B-H data already exceed Js − 2 % (M19, steel_1010) only +2 % is used and the note says so. It runs up to 16 sequential solves and stores nothing.

Analytic test problems (the current-sheet toroid and MMS on the unit square) live in `tests/fem_fixtures.py`. `tests/team24_fixture.py` builds the TEAM Problem 24 rig as a `Magnetostatic2D`; the comparison is in `docs/m5b-team24-results.md` and the slow test in `tests/validation/test_team24.py`. `tests/femm_machines.py` defines the FEMM comparison machines and points; fixtures are in `tests/validation/fixtures/`, the slow test is `tests/validation/test_femm.py`. `tests/solvers/test_cross_solver.py` compares the two solvers at 1e-4. Test file basenames must be unique, because `tests/` has no `__init__.py`.

## Tests

- `tests/conftest.py` provides the reference designs as factories `make_8_6`, `make_12_8` and `make_24_16`. Each accepts `**overrides`. The same designs are available as fixtures (`srm_8_6`, …, and the parametrized `reference_design`). `pythonpath = ["tests"]`, so tests can `from conftest import make_8_6`.
- Property tests use hypothesis over a bounded valid-design box. Keep the fast-suite variants deterministic and small, and mark long-running ones `@pytest.mark.slow`.
- The spec sets the CI budget for the fast suite at under 30 minutes (raised from 10 on 2026-10-06; the CI job timeout is 40 min).

## Conventions

- Keep comments free of task or plan history. Comments should explain the code as it is now.
- Open owner decisions are tracked in spec §10; decisions go in spec §11. `self_starting` is a hard error for user designs; only validation reference machines may build inside `model.validator.waive_rules("self_starting")`. The minimum web width is max(1 mm, 2 × lamination thickness).
- Map check warnings are informational; no optimizer or search may use a `warn` as a constraint. Hard limits live in `srmapp` requirements.

## Web layer (v0b)

- `src/srmweb`: `config` (env settings), `store` (SQLite `srmweb.db`, schema v2: jobs, cases, results and the `map_times` and `scan_times` tables the estimate reads; `attach_evaluation` is the one place an evaluation makes a stale case evaluated; a v1 file is migrated automatically on open), `jobs` (two lane threads, the main one and a quick one for `animate`; queue cap, running jobs marked interrupted on restart, resume; job kinds `search`, `evaluate`, `validate`, `animate`), `serialize` (NaN to null, electrical angles), `schemas` and `results` (request and response models), `cases` (the case check every route runs on raw inputs, `resolved_margin` and the evaluate-time `estimate`; no HTTP), `setup` (setup files and the map from a case-input loc to a setup-file loc), `api` (routes under `/api`, SSE at `/api/jobs/{id}/events`), `auth` (token plus HttpOnly SameSite=Strict cookie; a non-loopback host without `SRMWEB_TOKEN` is refused at start), `geometry` (outline SVG), `openapi` (schema dump).
- Cases (`srmapp.case`, `srmapp.references`): a case is one design plus its inputs (`CaseInputs`: requirements, design, winding `auto` or a `FixedWinding`, limits), created from a search candidate, a reference machine, an edit of an evaluated case, or an imported setup file. A new case is a stale draft whose inputs are stored raw and may be invalid; Evaluate and the setup export validate them (422 with field paths). An evaluated case is read-only (edit creates a new case); resuming an `evaluate` job is refused with 409 unless its case is still the same stale draft. `evaluate` runs the map once at the reference turns and the winding choice; `validate` runs `em_validate` and needs a `full` preset. Every result view shows "Unvalidated, peak-only" unless the case carries the 2D-verified label. At most 6 cases can be shown in the graphs.
- Routes: `/api/health`, `/api/geometry` (outline SVG), `/api/references`, `/api/materials`, `/api/validate` (live input check; also the resolved margin), `/api/cases` (GET list, POST create), `/api/cases/{id}` (GET, PATCH flag, comment, case label, show_in_graphs, draft inputs; DELETE), `/api/cases/{id}/evaluate|validate` (POST, return a job id), `/api/cases/{id}/estimate` (new map or cache hit; the time is the map, if new, plus the winding choice that follows it, from recent map times and scan times per winding mode (`auto` or `fixed`) or, without history, the speed budget and 450 s / 15 s for the scan), `/api/cases/{id}/setup` (export), `/api/cases/{id}/map.mat`, `/api/setup/check`, plus the job routes and `/api/settings/cache`.
- Setup files (`*.srm-setup.json`, `schema: "srm-setup"`, versioned) hold the requirements, design, winding and limits of a case; importing one creates a stale draft case.
- Env vars: `SRMWEB_HOST`, `SRMWEB_PORT`, `SRMWEB_DB`, `SRMWEB_CACHE_DIR`, `SRMWEB_WORKERS`, `SRMWEB_TOKEN`, `SRMWEB_QUEUE_MAX`, `SRMWEB_STATIC` (built frontend directory).
- v0b-2b: `srmapp.field` (`field_mesh`, `field_frame` one frame per call, `cached_frame`, probes; phase A only, solved on the reference-turns design at coil current = phase current x turns / (paths x `REFERENCE_TURNS`), ψ rescaled to the chosen winding; frames cached as npz in `<cache_dir>/fields/` with `PROBE_VERSION` in the name). `srmweb.quick` (`QuickLane`: a spawn `Pool(1)` so a solve past its 120 s limit can be terminated; `LaneTimeout` gives 504) and `srmweb.frames` (binary wire format: JSON header, then 8-byte-aligned little-endian arrays). `JobRunner` has two lane threads: the main one and a quick one for job kind `animate`; cancel, resume and SSE work the same for both. Routes: `GET /api/cases/{id}/field/mesh`, `POST /api/cases/{id}/field` (one snapshot), `POST /api/cases/{id}/animate` (job, 12 to 72 frames from unaligned to aligned), `GET /api/jobs/{id}/frames` (410 once the cache was cleared). The cache size and clear count the `fields/*.npz` files too, and clear is 409 while either lane is busy. The web Field tab renders with WebGL2 (2D canvas fallback) and the animation shows B(θ) probes (stator pole, yoke, rotor pole; the rotor_pole probe is the rotor pole centred at −2π/N_r in the rotor frame, which aligns with phase A's x-axis pole at the end of the animate stroke). `EnvelopeOut` `line_mean`/`line_rms`/`power_factor` (and the waveforms) are optional so evaluations stored before 0.3.0 still load. Temp files `*.tmp.npz` are not counted or deleted.
- Waveforms: `srmapp.drive.envelope` returns per-speed phase and line current waveforms on the envelope's own simulation grid (n_theta - 1 samples); phase voltage is the converter's average over each interval, the line (bus) current is the sum over the phases shifted by τ/q, and the power factor is copper-loss only. Search results leave out `envelope.waveforms` (size); the Waveforms tab shows on cases only.
- Layering: `srmweb` imports `srmapp` and `srmcore`, never the reverse; `srmweb` must not import gmsh, ngsolve, netgen or skfem (`tests/app/test_app_layering.py`).
- `web/`: React 19, Vite, TypeScript, Tailwind v4, shadcn (Base UI). `src/api/schema.ts` is generated from the OpenAPI dump; do not edit it by hand.
