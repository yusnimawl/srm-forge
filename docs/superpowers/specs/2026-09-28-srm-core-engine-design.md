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
`RadialSRM params` → validate → build stator & rotor geometry once → mesh stator & rotor once → for each map point (angle θ, current vector; one pool job each, each solved from A = 0): place rotor, re-triangulate moving band → build `Magnetostatic2D` → `adapter.solve` → post-process → write to map dataset.

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
Stator iron, rotor iron, shaft, one region per coil side (`coil_A1+`, `coil_A1-`, …), slot air, air-gap stator-side layer, **moving band**, air-gap rotor-side layer, optional thin outer air ring. Geometry auto-tags pole tips (`pole_tip`) and pole roots (`pole_root`) for refinement; "yoke corners" is the unfilleted case of a pole root (when a pole has no fillet, its sharp corner is tagged `pole_root` too, as a point rather than an arc).

### 4.4 Rotor rotation — moving band
- Stator and rotor meshes are generated **once** and never change → iron elements are fixed points (required for B(t) loss evaluation).
- Only a thin annulus in the middle of the air gap is re-triangulated per angle, between two node circles with identical uniform pitch (conforming; no mortar/Nitsche dependency). Mortar/Nitsche remains a possible later upgrade.
- Requested angles snap to multiples of the band pitch; the actual grid used is reported.

### 4.5 Mesh controls (all stored in `design.json` and in the provenance hash)
| Control | Detail |
|---|---|
| Air-gap mesh | explicit radial layer count (≥ 4) and circumferential division count; band pitch derived from it |
| Per-region size table | element size per region; overrides preset |
| Edge/corner refinement | size + growth rate per auto-tag: `pole_tip`, `pole_root` (pole roots — filleted or, as yoke corners, unfilleted) |
| Skin-depth layers | boundary-layer hook on conductors/shaft from max frequency & conductivity (used by sub-project #2) |
| Quality report | element count, min angle, aspect ratio, band skew; below threshold → `MeshRejected` |
| Adaptive refinement | energy-error-driven; deferred, not built (the *reference* preset is the screening knobs at uniform scale 0.25) |
| Presets | `screening` (coarse), `full`, `reference`; defaults set by the M5a study: the screening knobs, with `full` and `reference` at fixed `MeshSettings.scale` (2^(-1/2) and 0.25); an adaptive `reference` is not built (§11, 2026-10-03) |

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
4. Fit a monotone cubic Hermite interpolant to H(B) through the stacked points (PCHIP knot derivatives; the end derivative equals the last secant; if the fitted end derivative at B=0 is not positive, the first secant is used instead); ν = H/B for Newton.
5. **Validity check:** ν > 0 and dH/dB > 0 (monotone B-H). Non-monotone data → error, with an optional **repair tool** (smoothing) that reports exactly what changed.
6. **Saturation tail:** beyond the last data point extrapolate the polarisation `J = B − μ0·H` towards Js with the law `J = Js − d/(1 + s·(H − Hn)/d)`, d = Js − Jn and s the data's end slope of J, which joins the data C¹ and stays well-conditioned as s → 0. A ±2 % Js sensitivity check is part of validation.
7. **Fit-vs-datasheet error report** (a test).

### 5.3 Initial library
1. **M19** (validation; same curve exported to FEMM fixtures).
2. Added in M5e2 (2026-10-05): 10JNEX900 (B), Hiperco 50A (B), Hiperco 50HS at 720/740/760 °C (C), M43 (C); sources in `docs/sources/materials/`. Added 2026-10-06: NO20 (B, Cogent thin-NO DC table, Js and stacking provisional), Vacoflux 48 (B, VAC table plus the vector curve below 300 A/m), Vacoflux 50 (C, VAC table only, no data below 300 A/m). Added 2026-10-06: NO10-1270N and NO20-1200H (B, Tata Hi-Lite datasheets Mar 2019, 50 Hz magnetisation table 20-20000 A/m; Js and stacking provisional).
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
- **Fidelity presets:** `screening` (40 angles × 8 currents, coarse mesh — used by optimizer), `full` (48 × 20 — Pareto candidates), `reference` (120 × 40, screening knobs at scale 0.25 — validation); angles × power-law currents, plus the La current; the angle grid is clustered at the pole corners (M5a). The optimizer never runs full maps on every candidate.
- **Angle grid:** one rotor pole pitch 2π/Nr, the full pitch is solved (no mirror reduction; decided 2026-09-30, §11); denser near overlap start and near alignment; snapped to band pitch.
- **Current grid:** non-uniform, denser at low current and around the saturation knee; mandatory i = 0 row (ψ = 0 exactly); `I_max = max(1.2 × peak demand, device current limit) + chopping-overshoot margin` (absolute, not "× rated"). For #1 without requirements, I_max is a user parameter.
- **Excitation:** one circuit at a time (diagonal maps) **plus a coarse two-phase overlap map** `ψ, T(θ, i_k, i_k+1)` (~8 × 8 × 10) over the overlap angle window, generated for the `full` and `reference` presets (not `screening`). **Mutual-coupling check** reports Δψ and ΔT vs superposition (threshold 2 %).
- **Screening fidelity check:** on a sample of designs (M4 test set, and periodically during optimization runs in #6), screening results are compared with full maps; key numbers (peak static torque, La, Lu, ψ at I_max) must stay within 3 % and design **ranking** must be preserved (Spearman ρ ≥ 0.95). Otherwise the screening preset is refined.
- **Temperature:** B-H temperature is part of the map key; multi-temperature maps supported by the data model.
- **Dataset (HDF5, labelled coords):** ψ[θ,i,circuit], T[θ,i], L_inc, ∂ψ/∂θ, F_pole[θ,i,pole], W′, status[θ,i], overlap map, provenance (design hash, mesh settings, solver + dependency versions, material variant + temperature).
- **Derived drive tables:** inverse i(θ, ψ) on a saturation-graded ψ grid (flag points where ∂ψ/∂i < ε), T(θ, ψ), ∂ψ/∂θ from the same interpolant. Interpolation: PCHIP in current/flux, periodic spline in angle. Checks: ψ monotone in i, inverse round-trip error.
- **Standard results:** ψ-i curves per angle, L(θ) at several currents, T(θ) curves, La, Lu, La/Lu, peak static torque, key-numbers summary.
- **Exports:** lookup tables to CSV and `.mat` (for Simulink/PLECS). FMU/Modelica export deferred to sub-project #4.
- **Parallelism:** persistent worker processes that receive the mesh built once in the parent, BLAS/OpenMP pinned to 1 thread per worker; one job per map point, largest current first, no continuation between points.
- **Cache:** keyed by provenance hash; only complete maps are cached.
- **Speed budget** (each budget covers exactly what is listed). Re-baselined 2026-10-06 (M5e2) to the measured worst case of the 8/6 and 12/8 × 1.25 on the development laptop (i7-13620H, 6P+4E cores, 8 workers, cold cache; `examples/speed_budget.py`, `docs/validation/speed.json`); speed is revisited when the optimizer (#6) needs it:

  Measured 2026-10-06: `screening` 228 s (8/6) and 342 s (12/8); `full` 1550 s and 2094 s; `full` extras 1463 s and 980 s. The 2026-09-30 budgets (< ~90 s, < 13 min, < 7 min) were for the pre-M5a grids and `full` mesh (§11).

  | Preset | Included | Budget |
  |---|---|---|
  | `screening` | diagonal map (40 × 8) + cheap §7.3 checks | < 430 s per design (original target 30 s) |
  | `full` | diagonal map (48 × 20) + cheap §7.3 checks | < 44 min (original target 5 min) |
  | `full` extras | overlap map (~640 solves) + held-out interpolation solves | separate budget, < 31 min |
  | `reference` | everything, 120 × 40 grid, `reference` mesh (uniform scale 0.25; adaptive refinement deferred, not built) | no budget (validation only) |

### 7.3 Map-level consistency checks (automatic; checks needing extra FEM solves — held-out interpolation, band-radius independence — run only for `full` and `reference`)
- **Co-energy torque:** stroke-average torque from ΔW′ vs Arkkio within 2 %; pointwise comparison only after θ-smoothing and away from overlap start.
- Arkkio vs nodal-force torque within 1 % of peak torque.
- **Held-out interpolation test:** extra FEM solves at grid mid-points; interpolated ψ within 0.5 %, T within 1.7 % of peak torque at 64 held-out samples (set by M5a, §11).
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

- **CI:** Windows + Linux; fast suite on every commit (< 30 min; raised from 10 min on 2026-10-06, §11); slow validation suite locally or on a self-hosted runner, nightly/on demand. Exact dependency versions pinned in a lock file used for validation.

### 8.3 Tolerances
| Quantity | vs FEMM | vs measured |
|---|---|---|
| ψ | ±2 % | reported with uncertainty budget |
| Average static torque (unsaturated / mid range) | ±3 % | reported |
| Torque near alignment / deep saturation | ±5 % | reported |
| Cross-solver (same mesh) | ≤ 1e-4 relative | — |
| Arkkio vs nodal | ≤ 1 % of peak | — |
| Co-energy (stroke average) vs Arkkio | ≤ 2 % | — |
| Held-out interpolation | ψ ≤ 0.5 %, T ≤ 1.7 % of peak torque at 64 held-out samples (set by M5a, §11) | — |
| Mutual-coupling check threshold | Δψ, ΔT 2 % | — |
| Zero-current torque noise | < 1 % of average torque | — |
| Screening vs full | all key numbers ≤ 3 % (La read at 5 % of I_max, M5a), ranking Spearman ρ ≥ 0.95 | — |

### 8.4 Uncertainty budget
Every key result (La, Lu, peak torque, ψ at I_max) carries a worst-case uncertainty from: material confidence grade, mesh convergence estimate, 2D end-effect correction uncertainty, digitisation error where applicable.

### 8.5 Labels & fabrication gate
- #1 awards **"EM-validated"** when: produced by a validated engine version, reference-preset convergence check passed on that design, every point of every map has status `OK` or `OK_WITH_FALLBACK` (**no interpolated `NONCONVERGED` points** — a map with flagged points is usable for optimization but cannot be EM-validated), material confidence grade recorded.
- **"Fabrication-ready"** is awarded only by sub-project #7 and additionally requires (criteria exist from day one, **unmet by default**): material grade A (measured, annealed lot); losses computed; thermal hot-spot ≤ insulation class − 20 K at continuous and 30 s peak; rotor safety factor ≥ 1.5 at 1.2 × max speed with actual anneal-state yield + pole-root fatigue; insulation peak voltage incl. SiC dv/dt reflection below PDIV with margin; drive feasibility (current build-up/decay within stroke at max speed and bus voltage); tolerance-corner check (air gap ±0.05 mm, Js ±2 %, stacking factor tolerance) still meeting specs; design inside the validated envelope; human sign-off.

### 8.6 Validation report & correlation log
- The report is `docs/validation-report.md`, generated by `tools/validation_report.py`; it grows over time. Records engine version, pinned dependency versions and their licences, every comparison with pass/fail or error ± uncertainty.
- **Correlation log:** future locked-rotor ψ(θ, i) and static-torque tests on built prototypes are recorded and used to recalibrate end-effect hooks.

---

## 9. Milestones

| Milestone | Deliverables | Tests introduced |
|---|---|---|
| **M1** | model/ schemas + validator; RadialSRM; geometry with named regions & tags; stator/rotor meshing, moving band, mesh controls, quality report; mesh plot; confirm reference-machine data availability (full geometry + B-H + measured ψ) | validator/schema units, bounded property meshing tests, mesh-quality rejection |
| **M2** | minimal material schema (identity, one B-H, stacking factor, conductor ρ, density, cost) + B-H pipeline incl. tail; per-region materials; skfem_reference linear then nonlinear; connection matrix; ψ per circuit; energies; Arkkio at one angle; saturation report | B-H units, MMS, toroid, zero-current, linear Arkkio = co-energy, high-initial-permeability stiffness test (synthetic CoFe-like curve; real CoFe data arrives in M5) |
| **M3 (go/no-go)** | ngsolve_adapter at parity incl. moving-band rotation; nodal-force torque; TEAM 24 set up (using the existing NGSolve reference as a guide); decision recorded: NGSolve accepted, or fallback to skfem as primary | cross-solver ≤ 1e-4, band-pitch convergence, Arkkio vs nodal |
| **M4 — engine usable (complete 2026-09-30; speed, fidelity and held-out torque items open in §10)** | grids + fidelity presets; HDF5 datasets; persistent worker pool; cache; L_inc, ∂ψ/∂θ; inverse tables; overlap map + coupling check; standard results & key numbers; LUT exports (CSV, .mat); per-pole force arrays; all §7.3 checks; screening-vs-full fidelity check; error policy, cancellation, crash retry | map monotonicity, held-out interpolation, symmetry, coupling, screening fidelity, error policy, goldens |
| **M5 — EM-validated (complete 2026-10-06; srmcore 0.4.0 validated, `docs/validation-report.md`; slow suite green on CI for the `v0.4.0` tag)** | FEMM fixtures (done in M5c, `docs/m5c-femm-results.md`); TEAM 24 comparison (magnetostatic scope, §2.3; done in M5b, `docs/m5b-team24-results.md`); SRM measured-data comparison and end-winding hook (done in M5d, `docs/m5d-krishnan-results.md`; fringing calibration not done); (mesh-preset defaults done in M5a; adaptive reference preset deferred); uncertainty budgets and label logic (done in M5e1, `maps/validation.py`, §11 2026-10-05); validation report (done in M5e2, `tools/validation_report.py`); library adds 10JNEX900, Hiperco 50A/50HS, M43 (done in M5e2) | FEMM tolerances, measured comparisons, reference convergence, speed benchmark |

**Go/no-go rule for M3:** if NGSolve cannot reach cross-solver agreement and TEAM 24 behaviour within 2 weeks of M3 start, the scikit-fem solver becomes the primary engine for #1 and NGSolve is re-evaluated when 3D/thermal work begins. The owner makes the call and records it in the spec's decision log.

---

## 10. Open items (do not block #1)
- DC-bus voltage per vehicle (asked in sub-project #4; affects I_max and drive feasibility).
- Lamination supplier and grade (JYStator unverified; request datasheets measured after anneal, loss 50 Hz–>1 kHz, anneal spec, post-anneal yield, stacking factor, coating, price/MOQ/lead time, ring samples; obtain a second quote from JFE / Carpenter / VAC).
- **[M5] Reference-machine data gaps and self-starting-rule conflicts, from the `docs/reference-machines.md` audit (owner decision needed before M5):**
  (i) no SRM in the literature library at `D:\y\srm` satisfies criteria (a) full geometry + (b) B-H curve + (c) measured ψ(θ,i)/T(θ,i) together; TEAM Problem 24 is the only source that fully qualifies, and only for its own single-pole-pair locked-rotor scope (spec §2.3).
  (ii) no complete published 12/8 or 24/16 geometry was found in the library; the best traction-class candidate (Jiang's 24/16 PhD thesis) is still missing `rotor_yoke_thickness` and `rotor_pole_taper`, and its 1 mm fillet is a pole-shoe fillet with no M1-topology counterpart.
  (iii) Decided 2026-09-30 (§11): the `self_starting` rule stays a hard error for user designs; validation reference machines (Krishnan's 6/4, Jiang's 24/16) are built inside `model.validator.waive_rules("self_starting")`, which turns only that error into a warning. Closed 2026-10-05: M5d builds the 6/4 inside `waive_rules("self_starting")` and the 6/4 data gaps are filled (§11); the 24/16 is built the same way in M5c.
  (iv) the B-H gap is resolved by library curves at grade C (spec §5.1/§5.3's confidence grade C = "inferred") — i.e. these machines' named lamination grades (M43, M19) are expected to get their B-H curves from `srmcore`'s own materials library, not from the literature that only names the grade; M19 is already the item-1 initial-library entry, M43 would need to be added. Decided 2026-09-30: M43 is added in M5, with the reference machines, as a grade C library curve.
- **[M1→M5] Minimum web/pole-tip width — decided 2026-09-30 (§11).** The `min_width` rule uses max(`MIN_WEB_WIDTH` = 1 mm, 2 × `lamination_thickness`) (`model.validator.min_web_width`); the topology fit check keeps the 1 mm floor.
- **[M2→M5] Provisional material data in `src/srmcore/materials/data/`.** The M19 and steel_1010 B-H tables are FEMM 4.2 library curves (confidence C; FEMM's M-19 points above about 2.0 T are its own extrapolation). Their Js (M19 2.03 T, steel_1010 2.10 T) and densities (7650 and 7870 kg/m³) are typical handbook or datasheet values that have not been checked; each record lists them in `provisional_fields`. No `cost_per_kg` is set. Replace these with supplier values before M5. The §5.2 ±2 % Js sensitivity check runs in M5; steel_1010's tail is flat, so Js barely affects it.
- **[M2→M4] Solve speed.** M4a measured on the 8/6 `screening` mesh (42935 nodes, 20 A on phase A, NGSolve, one thread): cold solve 4.5–5.3 s in 11 Newton iterations (was 9 s; timings vary ±30 % run to run), so the §7.2 gate of 4 s was missed by 12–30 % (4.5–5.3 s vs 4 s) with the tangent assembled in NGSolve. The tangent is now numpy element matrices scattered into NGSolve's CSR value array (NGSolve keeps the pattern, the load and umfpack) and the netgen mesh is built in bulk: cold 20 A solve 2.0–2.5 s in 11 iterations, so the gate is met. A warm 5-10-20 A sweep takes 26 iterations, so warm starts give no gain. Done: numpy secant residual. Tried and dropped: an Euler current predictor (a0 + S·Δi with S = dA/di). It cut the warm sweep from 26 to 24 iterations (8 %) and a cold 20 A start from 11 to 8 iterations with 3 sub-steps (27 %) and to 6 with 6, but each sub-step costs a tangent factorisation plus a solve per circuit, so NGSolve wall time did not improve (4.46 s to 4.79 s with 3 steps, within run-to-run noise), 5.81 s (6 steps) and 5.99 s (1 step, 14 iterations); skfem 4.50 s to 3.50 s (3 steps) only. Not kept (keep rule: at least 25 % fewer iterations including its own cost in seconds). skfem with 3 sub-steps reached 3.5 s cold in one run; the predictor pays off only where the sensitivity solves are cheap. M4b built the process pool (one thread per worker, §7.2); with one job per point the 8/6 `screening` map takes 46 s on 8 workers and 51 s on 4 against the 30 s budget (not met). Mean per-job time rises from 1.63 s at 1 worker to 4.44 s at 8 (i7-13620H, 6P+4E cores), so the gap is CPU contention, not load balance or code. Remaining options, owner decides: reuse umfpack's symbolic factorisation (about 8 % per solve), fewer air-gap layers (needs the `min_layers` rule relaxed), coarser slot-air grading in `screening` (M5 preset study); details in `docs/m4-handoff.md`. Reuse of the Newton factorisation for L_inc is deferred (see the M4b map open items).
- **[M2→M4] Per-region stacking factor.** Motor-CAD sets the stacking factor per stator and rotor component; srmcore sets it per material. Revisit when rotor and stator use different stacks.
- **[M3→M4] Solver work after the go/no-go.** (i) Share the Newton driver between the two adapters only if the independence of the cross-check is no longer wanted; today the driver is a deliberate copy, so cross-solver agreement checks assembly and the linear solve, not the Newton logic. (ii) `ngsolve_adapter` builds the netgen mesh in bulk (`AddPoints`/`AddElements`) whenever the mesh changes (every angle) and still rebuilds the free-dof `BitArray` for every problem: cache it for maps. (iii) umfpack raises on a singular tangent where skfem's `spsolve` returns NaN and ends NONCONVERGED; align the never-raises behaviour if degenerate problems matter. (iv) Single-thread NGSolve shows no speed gain over skfem at 43k DOF; NGSolve assembly scales with threads (0.28 s to 0.04 s at 8), but §7.2 pins one thread per worker.
- **[M4b→M4c] Map open items.** (i) Resolved in M5a (§11): the angle grid is clustered at the pole corners. (ii) Saturation-knee current refinement: the power-law current grid is fixed. (iii) Physical core count for the default worker count (`build_map` uses half the logical CPUs; psutil is not a dependency). (iv) Deferred: reuse of the Newton factorisation for L_inc (L_inc is in the dataset; its separate factorisation costs about 0.15 s per point). (v) Temperature in the map cache key. (vi) Done (2026-09-30): non-A excitation. `aligned_angle` gives the aligned angle per phase and `build_map` shifts the angle grid to it. (vii) Engine code changes enter the cache key only through the srmcore version; a solver or physics change without a version bump serves stale maps. (viii) Done: overlap-window failure rule (§8.1). Any non-converged point in a complete overlap map raises `MapFailed`; nothing is filled. (ix) A public accessor for material file paths: provenance hashes the material JSON bytes through the private `materials.library._data_dir()`.
- **[M4b→M4c] Pool behaviour to revisit.** Pool jobs are one per map point (largest current first). Cancellation is checked per point and does not stop jobs already running; finished jobs are kept. A failing worker initializer is reported as `WorkerCrashed` after the retry. `MapFailed` carries no arrays. Importing `srmcore.maps` pins the OMP/OpenBLAS/MKL thread counts to 1 in the parent process too.
- **[M4c→M5] Open items after M4.** Decided 2026-09-30 (see §11): screening grid, La fidelity tolerance, speed budgets, held-out torque limit; the screening fidelity (La), held-out torque limit, grid sizes and mesh-preset defaults are settled by the M5a study (resolved 2026-10-03, §11, `docs/m5a-results.md`). Still open: (i) the saturation-knee-vs-Bsat check is deferred; (ii) reuse of the L_inc factorisation is deferred; (iii) check limits confirmed 2026-09-30 (ψ-bound margin 10 %, La analytic band 0.5–1.5, `iron_b_peak`: area-weighted p99.9 of iron |B| against the last stacked B-H point, warn; redefined 2026-10-05); (iv) the cause of the `full`-map time (600 points on a finer mesh) is not measured.
- **[M5a→M5] Speed budgets — decided 2026-10-05, measured 2026-10-06 (§11).** Re-baseline the §7.2 speed budgets for the M5a presets and grids (`full` maps measured 27-68 min, held-out at 64 samples); the M5 exit criterion "speed budgets met" depends on it. See `docs/m5a-results.md`.
- **[M5a→M5] Band noise — decided 2026-10-05 (§11).** The new `full` has fewer band divisions than the old one (band aspect 3 kept), and band noise dominates the 24/16 held-out error, so the 1.7 % held-out limit is in effect a band-noise limit. Outcome: the noise is accepted and `full` keeps its band divisions; the 1.7 % held-out limit covers it.
- **[M5a→M5] `iron_b_peak` definition — decided 2026-10-05 (§11).** The pointwise peak element |B| is mesh dependent at the pole-corner singularity. Outcome: the check uses the area-weighted 99.9th percentile of iron |B| (`b_peak`) against the smaller last stacked B-H point of the stator and rotor materials, and warns above 1.
- **[M3→M5] Band-pitch study caveat (resolved 2026-10-03: M5a measured band noise at 0.47 % RMS of peak torque on the new `full` preset, §11).** Changing the band divisions also changes the iron mesh nodes at the gap, so `examples/band_pitch_convergence.py` mixes band pitch with local gap refinement. On `screening` at 20 A and 10° the torque changes by 0.0102 N·m from D to 2D and 0.0040 N·m from 2D to 4D. Three samples show convergence, not an order.

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
| 2026-09-29 | B-H fit is a monotone Hermite interpolant of H(B), not a PCHIP of B(H) (§5.2 step 4); decided by the owner's expert panel |
| 2026-09-29 | Saturation tail J = Js − d/(1 + s·(H−Hn)/d), C¹ at the last point (§5.2 step 6) |
| 2026-09-29 | μ0 = 4π×10⁻⁷ exactly (FEMM parity) |
| 2026-09-29 | Outer air ring is `MeshSettings.outer_air_thickness`, default 0 (A = 0 on the stator OD); M5 decides whether to default to a ring |
| 2026-09-29 | Material costs stay unset until supplier quotes exist; placeholder values are listed in `provisional_fields` |
| 2026-09-29 | **M3 go/no-go: NGSolve accepted as the primary solver** (owner decision). `skfem_reference` stays as the independent cross-check. Evidence: NGSolve and scikit-fem agree to ~1e-11 (bar 1e-4) on the 8/6 across angles and currents and on TEAM 24; Arkkio and virtual-work torque agree to 0.02 %; TEAM 24 static torque is within 6.4 % of measurement (proposed 10 % criterion, provisional). Single-thread speed shows no gain over skfem, so speed was not the reason. |
| 2026-09-29 | Phases relabelled so counter-clockwise motoring reads A→B→C→D (M4a Task 2); lettering runs against pole order when Ns > Nr. Reason: drive-side commutation tables assume alphabetical order. |
| 2026-09-29 | **M4a outcome.** `solve_point`, phase order A→B→C→D and L_inc (checked against finite differences) are in. On NGSolve a cold `screening` 20 A solve is 4.5–5.3 s in 11 iterations, so the 4 s gate is not met; the owner decides whether M4b starts with the remaining speed options (§10). Euler current predictor dropped: fewer iterations but no NGSolve time saved once its sensitivity solves are counted (skfem with 3 sub-steps reached 3.5 s cold in one run; the predictor pays off only where the sensitivity solves are cheap). |
| 2026-09-30 | **M4b decisions.** h5py is a required dependency (HDF5 map dataset). The parent builds the mesh once and ships it to pool workers, instead of a Gmsh session per worker. Excitation layout: one circuit carries the current, the others are open, and ψ holds every circuit. No mirror reduction and no continuation between points (each point solves from A = 0, so points stay independent). Angle grid is warped (dense at alignment) and snapped to the band pitch; current grid is a power law, denser at low current. The solver is chosen by name with no fallback to the other solver. Maps are restricted to excited phase A for now (the aligned angle is only derived for A). Material JSON bytes are hashed into the map provenance. |
| 2026-09-30 | **M4c decisions.** (1) The NGSolve adapter fills the tangent from a numpy element kernel into NGSolve's sparsity pattern and factorises with umfpack; the netgen mesh is built in bulk. (2) One pool job per map point, largest current first. (3) Pole forces are net force vectors per stator pole, projected on the pole's radial and tangential axes. (4) The saturation-graded ψ grid comes from the aligned curve at uniform currents, with n_psi = 2 × n_currents. (5) La and Lu are secant values at the lowest non-zero grid current. (6) Provisional check limits: ψ-bound margin 10 %; La analytic band 0.5-1.5 (warn); Lu ≥ air-slot estimate; iron B ≤ 1.15 Js (warn; raised to 1.5 Js the same day, see the validator and check-limit row below); zero-torque and band-radius limits 1 % of peak; the energy checks warn below 16 angles. (7) Phase k is aligned at (k·ε) mod τ, and its grid is the phase-A grid shifted by that angle. (8) The overlap window runs from θ_B − (βs+βr)/2 to τ. (9) Held-out samples are angle midpoints × current midpoints, with the indices spread separately. |
| 2026-09-30 | **Diagonal maps for every phase.** Phase k (A = 0) is aligned at θ_k = (k·ε) mod τ, with ε = 2π/(m·Nr) and τ = 2π/Nr (`maps.grids.aligned_angle`). The map of phase k uses the phase-A angle grid shifted by θ_k, snapped to the band pitch, wrapped into [0, τ) and sorted; the failure policy's aligned-position check compares angles modulo τ. The phase-A restriction is lifted. |
| 2026-09-30 | **M4 open items decided by the owner.** (1) `screening` grid is 12 angles × 8 currents: 8 angles missed the peak torque by up to 6.7 % against the `full` map, 12 angles by at most 0.24 %, at about 1.5× the map time. (2) Screening fidelity tolerance for La is 5 % (the screening mesh under-resolves the pole tips; La error 2.6–3.0 % independent of the angle count); other key numbers stay at 3 %. (3) Speed budgets re-baselined to the laptop measurements (`screening` < ~90 s, `full` < 13 min); speed is revisited when the optimizer needs it. (4) Held-out torque limit 3 % of peak, provisional until the M5 convergence study (measured 2.1 % on the default `full` grid). |
| 2026-09-30 | **Validator and check-limit decisions (owner).** (1) `self_starting` stays a hard error for user designs; validation reference machines that break it as published are built inside `waive_rules("self_starting")` (only this rule is waivable). (2) Minimum web/pole-tip width = max(1 mm, 2 × lamination thickness). (3) Map-check limits confirmed: ψ-bound margin 10 %, La analytic band 0.5–1.5 (warn); the iron-B warning moves from 1.15 to 1.5·Js because element peaks at the pole-tip corners reach 1.4–1.5·Js at 20 A on the 8/6. (4) M43 is added to the materials library in M5 as a grade C curve. |
| 2026-10-03 | **M5a mesh convergence decisions.** The owner approved the presets and the angle grid on 2026-10-02. (1) Presets: `screening` unchanged; `full` and `reference` are the screening knobs at `MeshSettings.scale` 2^(-1/2) and 0.25; provenance hashes the resolved mesh settings. Worst mesh error over 4 designs: `full` ψ 0.25 %, torque 0.36 % of peak; `reference` ψ 0.04 %, torque 0.09 %; `screening` ψ 0.46 %, torque 0.64 %. (2) The angle grid is clustered at the pole corners; `GRID_SIZES` screening 40 × 8, `full` 48 × 20, `reference` 120 × 40 (angle-interpolation torque error 0.68 % at 48 angles, 8.4 % on the old grid at 30). (3) La is read at 5 % of I_max; at equal current `screening` and `full` agree to 0.05 %, so the old 2.6–3.0 % La error was the definition and the fidelity tolerance for La returns to 3 %. (4) Held-out torque limit 1.7 % of peak (worst measured 1.10 % on the 24/16 `full` map at 64 samples, × 1.5) and `fem_checks` defaults to 64 samples (16 under-read the worst error by up to 2.8×). (5) Not done: adaptive `reference` preset, nested refinement, P2 elements; the 24/16 level-5 mesh (3.2 M nodes) did not fit in 16 GB. Details in `docs/m5a-results.md`. |
| 2026-10-04 | **M5b TEAM 24.** Table I H read as ×10⁴ A-t/m (printed header and Fig. 3; the earlier reading was 10× too soft), points 18–21 dropped (J dips ≤ 5 mT), Js 2.0 T assumed. No pass/fail gate against the measurement: 2D torque −13.1 %, rotor-pole flux ≈ −17 %, current rise up to ≈ +18 % ahead; at steady state the model is low, the sign of the omitted 3D end flux. Early in the rise the sign differs: at 2 ms the measured torque (0.02 N·m) and flux are at the table's rounding limit (±25 % of 0.02), so +98 % torque and +61 % flux there mean only "model high"; from 5 ms T(i_meas) runs −7.5 % (5 ms), +10.2 % (10 ms), −13.3 % (200 ms), settling at −13.1 %, and F(i_meas) is high early (+21.1 % at 5 ms, +7.2 % at 10 ms) and low from 20 ms, settling to −17.2 %. Eddy currents in the solid steel make the measured current higher and the measured flux and torque lower early (zero at steady state), consistent with the model current lagging at 2 ms and T(i_meas), F(i_meas) being high early; since ∫(V − R·i) dt = ψ_final, eddy currents also leave the measured current below the eddy-free one later, so the mid-rise lead of the model current is consistent with eddy currents, with the lower 2D ψ_final (omitted 3D end flux) and with the interpolated low-field B-H (none established; only the 3D end flux explains the steady-state deficit). Slow test pins the 2D result and the signs; the M5d end-effect hook is to be checked on TEAM 24. See `docs/m5b-team24-results.md`. |
| 2026-10-04 | **M5c FEMM fixtures.** Machines: Krishnan 8/6 (assumed liner 0.5 mm, clearance 1 mm, fillets and tapers 0, fill 0.22, M19), Jiang 24/16 (assumed fields in `docs/m5c-femm-results.md`, waived `self_starting`, M19) and the synthetic 12/8. A = 0 on the stator OD in both tools (the outer-air-ring default stays open). FEMM gets the densely sampled srmcore law with LamFill 1, superseding the earlier §10 note to give FEMM the raw curve plus its LamFill. Torque tolerance has a floor of 1 % of the peak torque at that current; mid-range is 1/6 to 5/6 of the unaligned angle at or below the rated current (1.7 i_k rounded to 2 significant figures). Result against FEMM 4.2 at mesh level 2 (worst point): Krishnan 8/6 ψ 0.158 %, torque 0.34 % relative (\|T\| ≥ 5 % of peak) and 0.330 % of peak, largest error/limit 0.11; synthetic 12/8 ψ 0.111 %, 0.60 % and 0.451 %, 0.20; Jiang 24/16 ψ 0.137 %, 0.42 % and 0.334 %, 0.09. FEMM's own mesh-level change is up to 0.26 % in ψ, the size of the ψ differences (srmcore is below FEMM at all Krishnan and 20 of 21 synthetic points); the worst torque differences are above FEMM's own estimate. See `docs/m5c-femm-results.md`. |
| 2026-10-05 | **M5d measured Krishnan 6/4 and end-winding hook (owner decisions).** (1) Geometry: book bore 102.06 mm and back iron 10.515 mm (reproduce Materu's 2D FEA at 1 A), shaft 28.56 mm and rotor pole height 27.25 mm from the Materu dissertation (VT 1989, Table 1 p. 41, Appendix A pp. 287–288); the dissertation bore 122.0 mm / back iron 10.15 mm is a budget row; built inside `waive_rules("self_starting")` (closes the 6/4 §10 item). (2) Coil packed against the yoke, packing 0.5 (0.35–0.65 budget row), liner 0.3 mm; the `coil_inner_clearance` units guard is widened from 20 mm to 0.1 m (solved clearance 21.5 mm). (3) M19 library curve, steel_1010 as a crude bound ("E140" is unidentified). (4) End-winding hook: analytic, no calibration, `post/end_winding.py` (Grover partial inductances of the two end overhangs, L = k · N² · 2 · (M(span, g) − M(span, separation)), image factor k from 1 (free air) to 2 (against iron), midpoint 1.5 reported and the 1-to-2 half-spread an uncertainty row); `maps/end_winding.py` `with_end_winding` applies it after the map (2D map and cache unchanged); 3D iron-end fringing stays uncorrected. (5) Table 1 values only, no digitising. Result at 1 / 10 / 20 A (error vs measured before to after the correction, ± model uncertainty after, measurement scatter not stated for La and T_avg): La −2.6 % to −2.0 % (±13.4 %, material row ±9.8 % at 1 A), −15.1 % to −11.4 % (±2.6 %), −21.6 % to −15.0 % (±4.0 %); Lu +28.8 % to +45.2 % (±28.3 %), +13.0 % to +27.3 % (±26.1 %), +28.4 % to +44.7 % (±28.4 %); T_avg unchanged −10.9 % (±16.7 %), −16.9 % (±3.3 %), −28.5 % (±6.3 %). The correction (5.80 mH per phase) moves La toward the measurement but Lu away, because the 2D Lu (45.7 mH, coil against the yoke) is already above the measured 35.5–40.7 mH; about 9 % of the measured T_avg at 20 A (2.5 % at 10 A) is the too-high 2D Lu inflating the unaligned coenergy and the rest follows the saturated La; the 20 A La residual (-15.0 %; if all linked flux crossed the pole, the measured flux would imply about 2.6 T in the pole and yoke, an upper bound because slot and end leakage carry part of it) is outside the model uncertainty and is unlikely to come from the M19/steel_1010 lamination curves alone (the budget has no row for the Js of the unidentified "E140" steel) or the end turns (3D fringing or the measurement; not separable here). Measured T_avg is computed from measured flux linkage, so it is not independent of La and Lu. TEAM 24 independent check (hook not tuned on it, midpoint 9.83 mH for both coils): ψ at 7.41 A +19.8 %; mid-rise current lead +18.6 % to +8.1 % (maximum for t ≥ 5 ms), with early over-correction (2 ms −1.7 % to −17.3 %); steady-state current and static torque and flux unchanged. See `docs/m5d-krishnan-results.md` and `docs/m5b-team24-results.md`. |
| 2026-10-05 | **M5e1 label and budget (owner decisions).** (1) Convergence check (§8.5) = a point check plus the existing FEM checks: 4 key points (La, Lu, ψ_max, peak torque) solved on `full` and on `reference`, ψ within 0.5 % of the point's ψ and torque within 1 % of peak torque (M5a worst full-vs-reference: ψ 0.25 %, torque 0.36 %), and `fem_checks` (held-out ψ and torque, band radius) must pass. (2) `full` and `reference` maps can earn the label, `screening` never. (3) `VALIDATED_VERSIONS` (`srmcore.maps.validation`) is empty; M5e2 adds the version once the validation report passes; any other version gets no label. (4) Budget rows (worst-case sum): mesh, material, end effect, digitisation. (5) Material row = Js ±2 % half-spread + grade allowance A 0 %, B 3 %, C 10 %; the ±2 % Js check (§5.2) is its first part. (6) `iron_b_peak` = area-weighted 99.9th percentile of iron \|B\|, warns above the last stacked B-H data point. Spike on the 8/6 golden at 20 A (screening / full / reference, 0 to 20°): the element maximum grows with refinement (1.20–1.47 / 1.26–1.53 / 1.42–1.68 Js, pole-corner singularity), area p99.9 stays 0.78–1.08 Js and changes by at most 0.005; M19's last data point is about 1.11 Js, so the golden returns to `pass`. (7) Band noise in `full` is accepted, the 1.7 % held-out limit covers it. (8) A point-check failure gives no label and names the failing point and error; the adaptive `reference` preset stays deferred. (9) One entry `em_validate`; nothing is stored in HDF5. (10) The budget is on the end-winding-corrected key numbers (image factor 1.5), the 2D values reported beside them. (11) Js −2 % is tried first; when the B-H data already exceed Js − 2 % (M19: last point 2.006 T > 1.989 T; steel_1010: 2.073 T > 2.058 T) the half-spread is \|value(+2 %) − value(nominal)\| and the result records "+2 % only". (12) Map warnings are informational: no optimizer or search may use a `warn` as a constraint; hard limits live in `srmapp` requirements. srmcore 0.3.0 (the `b_peak` definition changed, old caches miss). See `docs/superpowers/specs/2026-10-05-m5e1-label-budget-design.md`. |
| 2026-10-05 | **M5e2 validated release (owner decisions).** (1) Library adds from public datasheets, sources committed in `docs/sources/materials/`: 10JNEX900 (B, JFE Technical Report 21 DC curve, digitisation 0.025), Hiperco 50A (B, Carpenter E199, digitisation 0.015), Hiperco 50HS at 720/740/760 °C (C, Carpenter E198 table only above 800 A/m; no unannealed variant), M43 (C, FEMM, points to 2.20 T because FEMM's own points above it have dB/dH < μ0); Hiperco stacking 0.95 provisional. (2) Speed budgets re-baselined to the measured worst case × 1.25 (2026-10-06: `screening` < 430 s, `full` < 44 min, `full` extras < 31 min; old: < ~90 s, < 13 min, < 7 min). (3) CI: private repo; branch pushes run Linux and Windows 3.12; PRs and `v*` tags the full matrix; the slow suite (`slow.yml`) runs on `v*` tags and manual dispatch. (4) Validation report generated by `tools/validation_report.py` (`docs/validation-report.md`), regenerated per release. (5) `MapResult` carries `design_hash` and `preset`; `em_validate` checks `map_identity`. (6) srmcore 0.4.0 is the first entry of `VALIDATED_VERSIONS`; a red slow-suite run on the `v0.4.0` tag removes it in a follow-up release. (7) Adaptive `reference` preset not built (the 8/6 passes the uniform check). Spec `docs/superpowers/specs/2026-10-05-m5e2-validated-release-design.md`. |
| 2026-10-06 | **Fast-suite budget and library adds (owner decisions).** (1) The fast-suite CI budget is raised from 10 to 30 min (measured 9:26 idle to 15:03 under load); the CI job timeout goes from 20 to 40 min. Splitting the suite (xdist, shards, tiers) is not done. (2) Library adds NO20 (B), Vacoflux 48 (B) and Vacoflux 50 (C) from the Cogent thin-NO brochure and the VAC CoFe brochure (sources in `docs/sources/materials/`); Pyleecan's materials (Apache-2.0, no provenance) are not used; the JYStator steel grade is to be asked from the supplier. |
