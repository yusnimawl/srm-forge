# SRM Design Tool — Sub-project #1: Core Engine (`srmcore`) — Design Spec

- **Date:** 2026-09-28
- **Status:** Approved by owner 2026-09-28
- **Owner / sole developer:** product owner (full-time, no fixed deadline, quality over speed)
- **Reviewed during brainstorming by:** Engineer, Project Manager, Commercial-Tools Expert (JMAG / Motor-CAD), Electric-Machines & Power-Electronics Expert agents

---

## 1. Product context

### 1.1 End goal of the whole tool
A private, in-house, open-source-stack tool: the user enters vehicle-motor requirements (motorcycle and car traction, 10–100 kW) and the tool outputs **fabrication-ready switched reluctance motor (SRM) design options**, ranked for **super-high power density**.

- **Inputs (future sub-project #5):** peak & continuous power/torque, max speed, DC-bus voltage, size envelope, mass limit, cooling type, peak duration (default 30 s).
- **Outputs (future sub-projects #6–#7):** Pareto options on continuous & peak kW/kg, continuous & peak kW/L (active parts: stator, rotor, windings incl. end-turns), efficiency, torque ripple, noise, cost; each option with a fabrication package (lamination DXF, stack length, winding spec, materials, warnings, datasheet).

### 1.2 Decisions that apply to all sub-projects
| Topic | Decision |
|---|---|
| Licensing | Private in-house use; GPL dependencies allowed. Licence chosen only if ever distributed (GPLv3 obligations apply only on distribution). |
| Architecture | Local-first client-server: Python backend on localhost + web UI; job-runner and storage behind interfaces so a hosted service can be added later. |
| FEM stack | **Gmsh** (geometry + meshing) + **NGSolve** (solver), behind a solver adapter; subject to the M3 go/no-go. Fallback: in-house scikit-fem solver. |
| Topology scope | Radial-flux SRM now; axial-flux, 3D, mutually-coupled windings later — architecture must admit them without rewrite. |
| Units | SI internally everywhere; conversion only at UI/import edges. |
| Platforms | Windows + Linux in CI; macOS at release. |
| Repository | `D:\y\srm-designer` (git). Literature library stays in `D:\y\srm`. |

### 1.3 Sub-project roadmap
1. **Core engine (this spec)** — geometry, mesh, nonlinear 2D magnetostatics, ψ/T maps, validated.
2. Losses — iron (waveform-based, unipolar/DC-biased, minor loops, lamination eddy at kHz), copper incl. AC/proximity.
3. Thermal + rotor stress (+ NVH modal later).
4. Drive & commutation simulation — winding/circuit connections, converter library, controllers (single-pulse, hysteresis, PWM, angle control, TSF, DITC), SiC/IGBT losses, DC-link ripple; transient circuit-coupled FEM for verification.
5. Requirements & sizing.
6. Optimization — NSGA-III, one run per material then merged fronts; material as categorical variable later.
7. Fabrication package — aggregates all physics gates into the "fabrication-ready" label.
8. Backend (FastAPI, REST + WebSocket).
9. Web UI (presets by default + Advanced panel, Motor-CAD-like workflow tabs).
10. Later: DXF import, axial-flux, 3D, coupled-winding full maps.

---

## 2. Scope of sub-project #1

### 2.1 In scope
A Python library `srmcore` (no UI, no server) that, given a radial SRM design, produces validated flux-linkage and torque maps and associated quantities, fast enough to be called by an optimizer.

### 2.2 Out of scope (architecture-only or reserved)
Loss models, thermal, structural, drive simulation, sizing, optimization, fabrication package, backend, UI, DXF import, axial-flux, 3D, full coupled-winding maps, cut-edge degradation implementation, temperature-dependent B-H implementation, iron-B field storage by default.

### 2.3 Success criteria (definition of done)
- **M4 — "engine usable":** sub-projects #2–#4 may start.
- **M5 — "engine EM-validated":**
  - all fast and slow test suites green on Windows + Linux;
  - agreement with FEMM within tiered tolerances (§8.3) on M19 reference machines (Krishnan 8/6 + one published 12/8 or 24/16 with full geometry);
  - TEAM Problem 24 (a voltage-step, locked-rotor transient test) compared against its published measurements within the magnetostatic scope: steady-state static torque compared directly; measured current rise reproduced at map level by integrating dψ/dt = V − R·i on the locked-rotor ψ(i) map (eddy currents neglected); full transient comparison deferred to sub-project #4; rig 3D end effects included in the uncertainty budget;
  - measured-data comparison for at least one SRM reference **reported with error and uncertainty** (not hard pass/fail), before and after end-effect correction;
  - speed budgets met on the owner's machine (8 physical cores), as defined in §7.2;
  - validation report (markdown table + plots) generated.
- Sub-project #1 can award at most the label **"EM-validated"**. It never awards "fabrication-ready".

---

## 3. Architecture

### 3.1 Package layout
```
srmcore/
  model/       Pydantic schemas (SI, schema-versioned); design validator (pre-mesh)
  project/     project folder I/O: design.json + results.h5; provenance hash; result cache
  topology/    Topology protocol + RadialSRM            (AxialSRM later)
  geometry/    Gmsh OCC named regions; edge/corner tags; symmetry detection
  mesh/        size fields, air-gap layers, moving band, quality report; one Gmsh session per process
  materials/   B-H processing, library (JSON), importers
  physics/     solver-neutral problems: Magnetostatic2D   (Thermal, Structural later)
  fields/      region-tagged, frame-aware (stator/rotor) field containers
  solvers/     SolverAdapter protocol · ngsolve_adapter · skfem_reference
  post/        flux linkage, torque (3 methods), forces, L_inc, energies, saturation report, end-effect hooks
  maps/        sweep runner, fidelity presets, HDF5 map datasets, derived drive tables, exports
tests/         unit, analytic, cross-solver, cross-tool (FEMM fixtures), measured, convergence, property, regression
tools/         FEMM fixture-generation scripts (pyfemm, Windows-only, run once), WebPlotDigitizer import helpers
(reserved, not implemented: study/ for coupled multi-physics pipelines, metrics/ for FEM-free mass/volume/cost checks)
```

### 3.2 Rules
1. Allowed imports (anything not listed is forbidden; enforced by an import-linter test):

   | Module | May import |
   |---|---|
   | `model` | (nothing internal) |
   | `materials` | model |
   | `fields` | model |
   | `topology` | model |
   | `geometry` | model, topology |
   | `mesh` | model, geometry |
   | `physics` | model, materials, mesh |
   | `solvers` | model, materials, physics, fields |
   | `post` | model, materials, physics, fields |
   | `maps` | all of the above |
   | `project` | model, maps |
2. Only `solvers/` imports NGSolve; only `geometry/` and `mesh/` import Gmsh.
3. Layers exchange plain data objects (numpy arrays, Pydantic models) — never solver types.
4. New machines and physics are added behind Protocols; they become plugins only when a second implementation exists.
5. Full-machine model is the default; periodic-sector solving is opt-in and must be validated against the full model.

### 3.3 Data flow for one map
`RadialSRM params` → validate → build stator & rotor geometry once → mesh stator & rotor once → for each rotor angle θ (per worker): place rotor, re-triangulate moving band → for each current vector (continuation): build `Magnetostatic2D` → `adapter.solve` → post-process → write to map dataset.

---

## 4. Geometry & meshing

### 4.1 RadialSRM parameters (SI)
| Group | Parameters |
|---|---|
| Topology | Ns, Nr, phase count m (validated against Ns/Nr) |
| Main dimensions | stator OD, rotor OD, air gap g, stack length L, shaft diameter |
| Poles | stator pole arc βs, rotor pole arc βr, stator & rotor pole taper angles |
| Yokes | stator yoke thickness, rotor yoke thickness |
| Manufacturing | pole-root fillet radii (stator & rotor) |
| Coils | turns per pole, fill factor, slot-liner thickness → coil cross-section |
| Materials | material per region (stator, rotor, shaft, coils) |

### 4.2 Design validator (runs before meshing, milliseconds)
- Lawrenson feasibility (errors): min(βs, βr) ≥ 2π/(m·Nr); βs + βr < 2π/Nr. βs > βr is a **warning** only (valid designs exist).
- Yoke/fillet fit, coil non-overlap, positive clearances, minimum web/pole-tip widths.
- Unit sanity (rejects values implausible in metres, e.g. an air gap of 0.5 "m").
- Warning (not error): lamination thickness > 0.2 mm when electrical frequency f_max = Nr·n_max/60 > 1 kHz.
- Errors name the offending parameter and rule (`InputError`).

### 4.3 Named regions
Stator iron, rotor iron, shaft, one region per coil side (`coil_A1+`, `coil_A1-`, …), slot air, air-gap stator-side layer, **moving band**, air-gap rotor-side layer, optional thin outer air ring. Geometry auto-tags pole tips, fillet roots and yoke corners for refinement.

### 4.4 Rotor rotation — moving band
- Stator and rotor meshes are generated **once** and never change → iron elements are fixed points (required for B(t) loss evaluation).
- Only a thin annulus in the middle of the air gap is re-triangulated per angle, between two node circles with identical uniform pitch (conforming; no mortar/Nitsche dependency). Mortar/Nitsche remains a possible later upgrade.
- Requested angles snap to multiples of the band pitch; the actual grid used is reported.

### 4.5 Mesh controls (all stored in `design.json` and in the provenance hash)
| Control | Detail |
|---|---|
| Air-gap mesh | explicit radial layer count (≥ 4) and circumferential division count; band pitch derived from it |
| Per-region size table | element size per region; overrides preset |
| Edge/corner refinement | size + growth rate per auto-tag (pole tips, fillet roots, yoke corners) |
| Skin-depth layers | boundary-layer hook on conductors/shaft from max frequency & conductivity (used by sub-project #2) |
| Quality report | element count, min angle, aspect ratio, band skew; below threshold → `MeshRejected` |
| Adaptive refinement | energy-error-driven; used by the *reference* preset (M5) |
| Presets | `screening` (coarse), `full`, `reference` (adaptive); defaults set by M5 convergence study |

---

## 5. Materials

### 5.1 Schema
- **Identity:** grade, variant (anneal state), parent grade, thickness, supplier, **provenance** (source document/URL, page, date, measurement method Epstein/SST/ring, temperature, annealed yes/no + anneal recipe, typical vs guaranteed), **confidence grade** A (measured table of the actual lot) / B (digitised plot) / C (inferred).
- **Magnetic:** B-H curve(s) — one temperature implemented in #1, list-per-temperature reserved; stacking factor (supplier-measured, never defaulted); saturation polarisation Js with source.
- **Required:** density, cost per kg (drive kW/kg and cost objectives).
- **Reserved optional fields (not implemented in #1):** loss curves P(B, f) + metadata (method, frequency range, build factor), stress-dependent B-H/loss multipliers, anisotropy (RD/TD), cut-edge degradation parameters, thermal conductivity (in-plane/through-stack), specific heat, Young's modulus, Poisson ratio, yield strength.
- **Conductors (Cu/Al):** resistivity at reference temperature + temperature coefficient, density, cost, insulation class / max temperature.
- Each grade × anneal state is a separate material variant with its own data. Note: Hiperco 50A and Hiperco 50HS are **separate grades** (different processing), each with its own recommended anneal; they are not two anneals of one grade.

### 5.2 B-H processing
1. Import (CSV/JSON, or WebPlotDigitizer CSV). Units must be T and A/m; importer rejects/flags unit mix-ups.
2. Add origin point with initial permeability.
3. Apply stacking factor: `B_eff(H) = k·B_steel(H) + (1−k)·μ0·H`.
4. Fit a monotone PCHIP to B(H); derive reluctivity ν for Newton.
5. **Validity check:** ν > 0 and dH/dB > 0 (monotone B-H). Non-monotone data → error, with an optional **repair tool** (smoothing) that reports exactly what changed.
6. **Saturation tail:** beyond the last data point extrapolate the polarisation `J = B − μ0·H` towards Js with a fitted law (e.g. `J = Js − a/H`) joined smoothly (C¹) to the data. A ±2 % Js sensitivity check is part of validation.
7. **Fit-vs-datasheet error report** (a test).

### 5.3 Initial library
1. **M19** (validation; same curve exported to FEMM fixtures).
2. In M5: **JFE 10JNEX900** (0.10 mm, 6.5 % Si; JFE catalogue f2e-001, digitised → grade B), **Hiperco 50A** and **Hiperco 50HS** (Carpenter datasheets, grade B).
3. Other candidates (Permendur/Supermendur/Vacoflux, 1J22) added when supplier data is obtained. M270-35A is deprioritised (0.35 mm unsuitable at 1.6–5.3 kHz).

---

## 6. Physics — Magnetostatic2D

- **Formulation:** 2D planar vector potential A_z: `∇·(ν(|B|) ∇A_z) = −J_z`, depth = stack length L.
- **Winding as data — connection matrix C:** rows = coil sides, columns = **circuits** (coil groups), entries = sign × turns / (parallel paths × coil-side area). The drive simulator (sub-project #4) connects circuits into phases. Equal current split across parallel paths is an explicit, flagged assumption. Conventional SRM = block-diagonal C; bifilar/Miller auxiliary windings and mutually-coupled windings are different C matrices, no code change.
- **Boundary conditions:** A = 0 on the outer boundary (stator OD, or the optional outer air ring for yoke-saturation leakage). Periodic/anti-periodic only with opted-in sector symmetry.
- **Nonlinear solve:** Newton with consistent Jacobian (`ν + 2ν′·B⊗B`), damping/line search; **continuation** along the current sweep; converged on residual AND ΔA (defaults: relative residual < 1e-8, relative ΔA < 1e-8 — tight enough for the 1e-4 cross-solver target). Fallback chain: more damping → smaller current steps → status `NONCONVERGED` (never raises into callers). Initial-permeability stiffness (CoFe) covered by continuation and a dedicated test.
- **Element order, quadrature rule and Newton tolerances:** pinned and identical across adapters (for cross-solver comparisons).
- **Output `FieldSolution`** (numpy, frame-tagged): A per node, B and ν (and differential ν) per element, stored energy and co-energy, status.

---

## 7. Post-processing & maps

### 7.1 Per-point post-processing (`post/`)
- **Flux linkage per circuit:** `ψ_k = L · Σ_coil sides C_sk · ∫ A dA`, plus end-winding inductance hook.
- **Incremental inductance matrix** `L_inc = ∂ψ/∂i` from the converged Newton tangent (one extra linear solve per circuit, reused factorisation). Only when converged with the consistent Jacobian; recomputed after any fallback; verified against finite differences in tests.
- **Torque — three methods:** Arkkio (primary, in the moving band), nodal force/virtual work, and map-level co-energy (§7.3).
- **Forces:** radial + tangential force per stator pole; net unbalanced magnetic pull (arrays stored; used by NVH later). Air-gap force density with spatial-order decomposition is **deferred to the NVH work** (it needs the replay pass anyway).
- **Energies:** W and W′ per point.
- **Saturation report:** peak and percentile B per region (pole tips, yokes).
- **Coil-region B** (slot leakage field) stored for AC/proximity copper loss (sub-project #2).
- **Iron element B** in own frame: optional, **off by default** (large), enabled for final designs. Map-grid B is only an optimizer estimate: sub-project #2 builds element B(t) with a **replay pass** — the drive simulation's i(t) is fed back through FEM at 64–128 steps per electrical period over the full pitch (mirror reduction is invalid for B(t)); chopping ripple ΔB added analytically from L_inc and Δi. The same replay yields NVH force harmonics.
- **End-effect hooks:** analytic end-winding inductance (implemented); 3D fringing factor (implemented only after calibration against measured data). Unaligned inductance accuracy is treated as critical.

### 7.2 Map generation (`maps/`)
- **Fidelity presets:** `screening` (~8 angles × ~8 currents, coarse mesh — used by optimizer), `full` (~30 × ~20 — Pareto candidates), `reference` (fine/adaptive — validation). The optimizer never runs full maps on every candidate.
- **Angle grid:** one rotor pole pitch 2π/Nr, halved by mirror symmetry only when geometry **and** excitation are symmetric (checked; coupled maps handled as circuit permutation); denser near overlap start and near alignment; snapped to band pitch.
- **Current grid:** non-uniform, denser at low current and around the saturation knee; mandatory i = 0 row (ψ = 0 exactly); `I_max = max(1.2 × peak demand, device current limit) + chopping-overshoot margin` (absolute, not "× rated"). For #1 without requirements, I_max is a user parameter.
- **Excitation:** one circuit at a time (diagonal maps) **plus a coarse two-phase overlap map** `ψ, T(θ, i_k, i_k+1)` (~8 × 8 × 10) over the overlap angle window, generated for the `full` and `reference` presets (not `screening`). **Mutual-coupling check** reports Δψ and ΔT vs superposition (threshold 2 %).
- **Screening fidelity check:** on a sample of designs (M4 test set, and periodically during optimization runs in #6), screening results are compared with full maps; key numbers (peak static torque, La, Lu, ψ at I_max) must stay within 3 % and design **ranking** must be preserved (Spearman ρ ≥ 0.95). Otherwise the screening preset is refined.
- **Temperature:** B-H temperature is part of the map key; multi-temperature maps supported by the data model.
- **Dataset (HDF5, labelled coords):** ψ[θ,i,circuit], T[θ,i], L_inc, ∂ψ/∂θ, F_pole[θ,i,pole], W′, status[θ,i], overlap map, provenance (design hash, mesh settings, solver + dependency versions, material variant + temperature).
- **Derived drive tables:** inverse i(θ, ψ) on a saturation-graded ψ grid (flag points where ∂ψ/∂i < ε), T(θ, ψ), ∂ψ/∂θ from the same interpolant. Interpolation: PCHIP in current/flux, periodic spline in angle. Checks: ψ monotone in i, inverse round-trip error.
- **Standard results:** ψ-i curves per angle, L(θ) at several currents, T(θ) curves, La, Lu, La/Lu, peak static torque, key-numbers summary.
- **Exports:** lookup tables to CSV and `.mat` (for Simulink/PLECS). FMU/Modelica export deferred to sub-project #4.
- **Parallelism:** persistent worker processes, one Gmsh session each, BLAS/OpenMP pinned to 1 thread per worker, physical cores only; each worker owns a set of angles and sweeps all currents with continuation.
- **Cache:** keyed by provenance hash; only complete maps are cached.
- **Speed budget** (owner's machine, 8 physical cores; each budget covers exactly what is listed):

  | Preset | Included | Budget |
  |---|---|---|
  | `screening` | diagonal map (~8 × 8) + cheap §7.3 checks | < ~30 s per design |
  | `full` | diagonal map (~30 × ~20) + cheap §7.3 checks | < 5 min (≈ ≤ 4 s per solve, ~20–40k DOF) |
  | `full` extras | overlap map (~640 solves) + held-out interpolation solves | separate budget, < 7 min |
  | `reference` | everything, adaptive mesh | no budget (validation only) |

### 7.3 Map-level consistency checks (automatic; checks needing extra FEM solves — held-out interpolation, band-radius independence — run only for `full` and `reference`)
- **Co-energy torque:** stroke-average torque from ΔW′ vs Arkkio within 2 %; pointwise comparison only after θ-smoothing and away from overlap start.
- Arkkio vs nodal-force torque within 1 % of peak torque.
- **Held-out interpolation test:** extra FEM solves at grid mid-points; interpolated ψ within 0.5 %, T within 1 % of peak.
- Energy identity `W + W′ = Σ_k ψ_k·i_k` per point (reduces to ψ·i for a single circuit); loop energy `∮ i dψ = ∫ T dθ` per stroke.
- ∫T dθ over a full pitch = 0 at constant current; T = 0 at aligned/unaligned; correct sign pattern; T(−θ) = −T(θ) under mirror.
- Arkkio torque independent of band radius.
- La/Lu: < 2 fails, 2–3 warns (legitimate for high-rotor-pole designs such as 24/16), 3–15 normal, > 15 warns; Lu ≥ air-slot estimate; ∂ψ/∂i > 0; ψ ≤ N_series·Bsat·A_pole·L·(1+margin) with N_series = series turns per circuit (turns per pole × poles in series per path); ψ decreasing from aligned to unaligned; saturation knee consistent with material Bsat; element B not above extrapolated Bsat beyond tolerance.
- Reciprocity L_ij = L_ji (coupled/overlap maps).
- Magnetic-circuit analytic estimates of La/Lu within expected band.

---

## 8. Error handling, testing & validation

### 8.1 Error handling
| Class / status | Meaning & handling |
|---|---|
| `InputError` | validator failure; names parameter + rule; raised before meshing |
| `MeshRejected` | quality below threshold; design reported infeasible |
| `OK` / `OK_WITH_FALLBACK` / `NONCONVERGED` | per-solve status |
| `WorkerCrashed` | native crash in pool; retry once in a fresh process, then failed |

- **Map policy:** isolated `NONCONVERGED` points interpolated + flagged. Map **fails** if > 2 % of points fail, or any point at the aligned position, at I_max, or inside the overlap window fails. Designs targeting a fabrication label require **zero** failed points in the top current level and overlap window.
- Nothing silent: every result carries status + warnings; the optimizer treats failures as infeasible.
- Cancellation keeps partial results; only complete maps are cached. Progress and cancel callbacks on all long operations.
- Structured JSON logs tagged with the provenance hash.

### 8.2 Test suites
| # | Suite | Content |
|---|---|---|
| 1 | Unit | validator rules, B-H processing (monotone, stacking, tail), connection matrix, interpolation, schema round-trip, unit-mix-up regression |
| 2 | Analytic / MMS | **method of manufactured solutions** on the nonlinear PDE with expected convergence rates; toroid with current-sheet winding (exact analytic) deep into saturation; C-core reluctance as sanity band only; Arkkio vs analytic C-core force; zero current → zero torque/force; linear case Arkkio = co-energy |
| 3 | Cross-solver | NGSolve vs scikit-fem, same mesh, element order, quadrature, Newton tolerances and B-H: relative agreement ≤ 1e-4 |
| 4 | Cross-tool | FEMM fixtures (generated once on Windows by `tools/` pyfemm script; same fitted B-H; FEMM lamination fill off; versioned) |
| 5 | Measured | **TEAM Problem 24** first (NGSolve reference implementation exists), within magnetostatic scope as defined in §2.3: static torque at final current, current rise via ψ(i)-map integration, eddy currents neglected; then SRM measured curves (Krishnan / theses with test-bench data), digitised, with uncertainty budget; before and after end-effect correction |
| 6 | Convergence | mesh refinement series, band pitch, held-out grid interpolation, zero-current torque noise |
| 7 | Property-based | hypothesis over a bounded parameter box of valid geometries: meshing succeeds, ψ monotone, symmetry, sign pattern; few examples in fast suite, more nightly |
| 8 | Regression | golden results for reference designs; speed benchmark tracked (fails only on the owner's machine) |
| 9 | Robustness | fuzzed importers/validator (malformed CSV, unit mix-ups); determinism across OS and repeated runs |

- **CI:** Windows + Linux; fast suite on every commit (< 10 min); slow validation suite locally or on a self-hosted runner, nightly/on demand. Exact dependency versions pinned in a lock file used for validation.

### 8.3 Tolerances
| Quantity | vs FEMM | vs measured |
|---|---|---|
| ψ | ±2 % | reported with uncertainty budget |
| Average static torque (unsaturated / mid range) | ±3 % | reported |
| Torque near alignment / deep saturation | ±5 % | reported |
| Cross-solver (same mesh) | ≤ 1e-4 relative | — |
| Arkkio vs nodal | ≤ 1 % of peak | — |
| Co-energy (stroke average) vs Arkkio | ≤ 2 % | — |
| Held-out interpolation | ψ ≤ 0.5 %, T ≤ 1 % of peak | — |
| Mutual-coupling check threshold | Δψ, ΔT 2 % | — |
| Zero-current torque noise | < 1 % of average torque | — |
| Screening vs full | key numbers ≤ 3 %, ranking Spearman ρ ≥ 0.95 | — |

### 8.4 Uncertainty budget
Every key result (La, Lu, peak torque, ψ at I_max) carries a worst-case uncertainty from: material confidence grade, mesh convergence estimate, 2D end-effect correction uncertainty, digitisation error where applicable.

### 8.5 Labels & fabrication gate
- #1 awards **"EM-validated"** when: produced by a validated engine version, reference-preset convergence check passed on that design, every point of every map has status `OK` or `OK_WITH_FALLBACK` (**no interpolated `NONCONVERGED` points** — a map with flagged points is usable for optimization but cannot be EM-validated), material confidence grade recorded.
- **"Fabrication-ready"** is awarded only by sub-project #7 and additionally requires (criteria exist from day one, **unmet by default**): material grade A (measured, annealed lot); losses computed; thermal hot-spot ≤ insulation class − 20 K at continuous and 30 s peak; rotor safety factor ≥ 1.5 at 1.2 × max speed with actual anneal-state yield + pole-root fatigue; insulation peak voltage incl. SiC dv/dt reflection below PDIV with margin; drive feasibility (current build-up/decay within stroke at max speed and bus voltage); tolerance-corner check (air gap ±0.05 mm, Js ±2 %, stacking factor tolerance) still meeting specs; design inside the validated envelope; human sign-off.

### 8.6 Validation report & correlation log
- Generated at M5 as markdown table + plots; grows over time. Records engine version, pinned dependency versions and their licences, every comparison with pass/fail or error ± uncertainty.
- **Correlation log:** future locked-rotor ψ(θ, i) and static-torque tests on built prototypes are recorded and used to recalibrate end-effect hooks.

---

## 9. Milestones

| Milestone | Deliverables | Tests introduced |
|---|---|---|
| **M1** | model/ schemas + validator; RadialSRM; geometry with named regions & tags; stator/rotor meshing, moving band, mesh controls, quality report; mesh plot; confirm reference-machine data availability (full geometry + B-H + measured ψ) | validator/schema units, bounded property meshing tests, mesh-quality rejection |
| **M2** | minimal material schema (identity, one B-H, stacking factor, conductor ρ, density, cost) + B-H pipeline incl. tail; per-region materials; skfem_reference linear then nonlinear; connection matrix; ψ per circuit; energies; Arkkio at one angle; saturation report | B-H units, MMS, toroid, zero-current, linear Arkkio = co-energy, high-initial-permeability stiffness test (synthetic CoFe-like curve; real CoFe data arrives in M5) |
| **M3 (go/no-go)** | ngsolve_adapter at parity incl. moving-band rotation; nodal-force torque; TEAM 24 set up (using the existing NGSolve reference as a guide); decision recorded: NGSolve accepted, or fallback to skfem as primary | cross-solver ≤ 1e-4, band-pitch convergence, Arkkio vs nodal |
| **M4 — engine usable** | grids + fidelity presets; HDF5 datasets; persistent worker pool; cache; L_inc, ∂ψ/∂θ; inverse tables; overlap map + coupling check; standard results & key numbers; LUT exports (CSV, .mat); per-pole force arrays; all §7.3 checks; screening-vs-full fidelity check; error policy, cancellation, crash retry | map monotonicity, held-out interpolation, symmetry, coupling, screening fidelity, error policy, goldens |
| **M5 — EM-validated** | FEMM fixtures; TEAM 24 comparison (magnetostatic scope, §2.3); SRM measured-data comparison; end-winding hook + end-effect calibration; adaptive reference preset; mesh-preset defaults from convergence study; uncertainty budgets; validation report; library adds 10JNEX900, Hiperco 50A/50HS | FEMM tolerances, measured comparisons, reference convergence, speed benchmark |

**Go/no-go rule for M3:** if NGSolve cannot reach cross-solver agreement and TEAM 24 behaviour within 2 weeks of M3 start, the scikit-fem solver becomes the primary engine for #1 and NGSolve is re-evaluated when 3D/thermal work begins. The owner makes the call and records it in the spec's decision log.

---

## 10. Open items (do not block #1)
- DC-bus voltage per vehicle (asked in sub-project #4; affects I_max and drive feasibility).
- Lamination supplier and grade (JYStator unverified; request datasheets measured after anneal, loss 50 Hz–>1 kHz, anneal spec, post-anneal yield, stacking factor, coating, price/MOQ/lead time, ring samples; obtain a second quote from JFE / Carpenter / VAC).

## 11. Decision log
| Date | Decision |
|---|---|
| 2026-09-28 | Stack Gmsh + NGSolve behind adapter, M3 go/no-go vs scikit-fem reference |
| 2026-09-28 | Private use; GPL allowed; licence decided only on distribution |
| 2026-09-28 | Moving-band rotation; full-model default |
| 2026-09-28 | Connection-matrix columns are circuits |
| 2026-09-28 | Fidelity presets; optimizer uses screening maps |
| 2026-09-28 | #1 awards "EM-validated" only; "fabrication-ready" belongs to #7 |
| 2026-09-28 | First validation measured benchmark: TEAM Problem 24 |
| 2026-09-28 | Repository at `D:\y\srm-designer`; spec approved |
