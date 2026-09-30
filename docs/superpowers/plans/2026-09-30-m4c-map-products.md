# M4c Map Products Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish milestone M4 ("engine usable"): meet the solve and map speed budgets, add L_inc, ∂ψ/∂θ, per-pole forces and energy to the map dataset, derive inverse drive tables, standard results and key numbers, run all §7.3 checks, add the overlap map with coupling and reciprocity checks, non-A excitation, CSV/.mat exports, the screening-vs-full fidelity check and golden regression numbers.

**Architecture:** Speed first (Tasks 1–2) because it sets how expensive every later map is. The map runner (`maps/run.py`) stays the single solve path; new modules only post-process a `MapResult` (`tables.py`, `results.py`, `checks.py`, `export.py`) except `overlap.py` and `fem_checks.py`, which run extra solves through the same pool. Public entry points live in `maps/__init__.py`.

**Tech Stack:** Python ≥ 3.12, numpy, scipy (`CubicSpline`, `PchipInterpolator`, `scipy.io.savemat`, `scipy.stats.spearmanr`), h5py, NGSolve (umfpack), scikit-fem (reference solver), pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` (§7.1, §7.2, §7.3, §8.1, §8.3, §9 M4 row, §10 M4b→M4c items). Handoff: `docs/m4-handoff.md`.

## Global Constraints

- Import rules (`tests/test_import_rules.py`): `maps` may import every lower layer; `post` may import model, materials, physics, fields; only `solvers/` imports `ngsolve`/`netgen`/`skfem`.
- SI units everywhere (m, rad, A, Wb-turns, N, N·m, J, H).
- Layers exchange numpy arrays, frozen Pydantic models and frozen dataclasses (`@dataclass(frozen=True, eq=False)` for array holders).
- No new dependencies. scipy and h5py are already required.
- Fast suite (`python -m pytest -m "not slow"`) stays under 10 minutes; mark anything slower than ~20 s `@pytest.mark.slow`. Test file basenames are unique across `tests/`.
- Comments describe the code as it is now, with no task or plan history.
- Do not change open-owner-decision behaviours (`self_starting`, `MIN_WEB_WIDTH`).
- Cross-solver agreement NGSolve vs scikit-fem stays ≤ 1e-4 relative (`tests/solvers/test_cross_solver.py`).
- Tolerances (spec §8.3): Arkkio vs nodal ≤ 1 % of peak; co-energy stroke average vs Arkkio ≤ 2 %; held-out interpolation ψ ≤ 0.5 %, T ≤ 1 % of peak; mutual coupling threshold Δψ, ΔT 2 %; screening vs full key numbers ≤ 3 %, ranking Spearman ρ ≥ 0.95.
- Speed budgets (spec §7.2): cold `screening` 20 A solve ≤ 4 s; `screening` map (~8 × 8) + cheap checks < ~30 s; `full` map (~30 × ~20) + cheap checks < 5 min; `full` extras (overlap map + held-out solves) < 7 min.
- Phase A is aligned at θ = 0; counter-clockwise motoring excites A → B → C → D. Stator pole k sits at angle k·2π/Ns. Stroke angle ε = 2π/(m·Nr); rotor pole pitch τ = 2π/Nr.

## Rulings made while writing this plan (owner may overturn)

1. **Speed:** the NGSolve adapter keeps NGSolve's sparsity pattern and umfpack factorisation but fills the tangent's values from a numpy element kernel (measured: NGSolve `Assemble` 0.31 s vs umfpack `Inverse` 0.10 s per Newton iteration on the 8/6 screening mesh). The netgen mesh is built with the bulk `AddPoints`/`AddElements` API (Python loop measured at 0.62 s per angle). The numpy kernel is a third implementation of the tangent (skfem assembles its own), so the cross-solver check stays independent.
2. **Job granularity:** one pool job per map point, largest current first. Each point already solves from A = 0, so this changes no numbers.
3. **L_inc reuse of the Newton factorisation:** not done; with numpy assembly a separate factorisation costs about 0.15 s per point. Recorded in §10.
4. **Pole forces:** Maxwell stress averaged over the moving band, each band element assigned to the stator pole whose sector (centre ± π/Ns) holds its centroid. Force on the stator pole, radial positive outward, tangential positive counter-clockwise, in the pole's local frame.
5. **Saturation-graded ψ grid:** ψ values of the aligned-position ψ(i) curve at uniformly spaced currents, so the grid is dense in ψ where the curve is flat (saturation). n_psi = 2 × n_currents.
6. **La, Lu:** secant ψ/i at the lowest non-zero grid current; Lu at θ_aligned + τ/2 from the periodic angle spline.
7. **ψ bound margin** 10 %; **La analytic band** 0.5 ≤ La/La_est ≤ 1.5 (warn outside); **Lu air-slot estimate** Lu ≥ Lu_est (fail below); **element-B check** peak iron |B| ≤ 1.15·Js (warn above); **zero-mean and aligned/unaligned zero torque** limit 1 % of peak torque; **band-radius independence** limit 1 % of peak torque. Saturation-knee-vs-Bsat check deferred to §10 (no quantitative rule in the spec).
8. **Non-A excitation:** phase k (0 = A) is aligned at θ_k = (k·ε) mod τ; the diagonal map of phase k uses the phase-A angle grid shifted by θ_k and snapped to the band pitch.
9. **Overlap window** for the A→B handover: [θ_B − (βs + βr)/2, θ_A + τ] taken modulo τ, i.e. from the start of B's pole overlap until A's alignment; empty when (βs + βr)/2 ≤ ε, in which case no overlap map is built. Default overlap grid 8 angles × 8 × 8 currents (both phases on the diagonal-map current grid for that size).
10. **Goldens and fidelity runs** are `slow` tests plus an example script; measured numbers go to the handoff.

## Review Focus

1. A map built before this change (old HDF5 schema without the new datasets) must be a cache miss, not a crash.
2. A cancelled map (partial, `complete=False`) passed to the analysis functions must raise a clear `ValueError`, not produce NaN key numbers silently.
3. Designs where ψ is not strictly increasing in current at some angle must be reported by the monotonicity check and must not crash the inverse table (flagged, NaN where undefined).
4. An empty overlap window (narrow poles) must yield "no overlap map" cleanly, not an empty-array crash.
5. Exports must round-trip: reading the CSV and the .mat back gives the same numbers to 1e-12 relative.

---

### Task 1: Numpy tangent kernel and bulk netgen mesh in the NGSolve adapter

**Files:**
- Modify: `src/srmcore/physics/fem.py` (add `tangent_element_matrices`)
- Modify: `src/srmcore/solvers/ngsolve_adapter.py`
- Test: `tests/physics/test_tangent_kernel.py` (new), existing `tests/solvers/*`
- Modify: `docs/m4-handoff.md` (speed table), spec §10 "[M2→M4] Solve speed" item

**Interfaces:**
- Produces: `tangent_element_matrices(grads, areas, triangles, nu, dnu, a) -> np.ndarray` shape (n_elements, 3, 3), per unit depth: `K_e[i, j] = area·(ν·∇φ_i·∇φ_j + 2·dν/dB²·(∇φ_i·∇A)(∇φ_j·∇A))`. Same B convention as `secant_residual` (|B| = |∇A| on P1).

- [ ] **Step 1:** Write `tests/physics/test_tangent_kernel.py`: build the 8/6 `screening` problem at θ = 0, 20 A on A (as `tests/solvers/test_ngsolve_adapter.py` does), take a random A (seeded, scale 1e-3), and assert that the scattered numpy kernel equals the matrix NGSolve assembles from the existing `BilinearForm` to 1e-10 relative (compare as dense rows on a sample of 200 rows, or via scipy CSR from `mat.CSR()`). Use `pytest.importorskip("ngsolve")`.
- [ ] **Step 2:** Implement `tangent_element_matrices` in `physics/fem.py` with `np.einsum` (no Python loops).
- [ ] **Step 3:** In `_Discretisation.__init__`, assemble the tangent once (to fix the sparsity pattern), then compute a scatter index: for every element entry (e, i, j) its position in the matrix's value array (`mat.AsVector().FV().NumPy()`), using `mat.CSR()` (row pointer + column indices) and `np.searchsorted` on keys `row * n + col`. Assert every entry is found.
- [ ] **Step 4:** In `_System.solve_tangent` and `NgsolveAdapter.sensitivity`, replace `tangent.Assemble()` with: values[:] = `np.bincount(scatter, weights=K.ravel(), minlength=nnz)` (scatter into the NumPy view of the matrix values). Keep `Inverse(freedofs, inverse="umfpack")`.
- [ ] **Step 5:** Replace the Python loops in `_netgen_mesh` with `mesh.AddPoints(...)` and `mesh.AddElements(dim=2, index=1, data=..., base=0)` (check the exact signature with `help()`), keeping vertex i = node i, element k = triangle k and the orientation fix. The existing `space.ndof != len(nodes)` guard stays.
- [ ] **Step 6:** Build the free-dof `BitArray` without a Python loop if the API allows (e.g. from a numpy bool array); otherwise leave it.
- [ ] **Step 7:** Update the module docstring (the tangent is no longer assembled in NGSolve; NGSolve supplies the sparsity pattern, the load and umfpack).
- [ ] **Step 8:** Run `python -m pytest tests/solvers tests/physics tests/post -m "not slow"`; all pass, cross-solver ≤ 1e-4 unchanged.
- [ ] **Step 9:** Run `python examples\solve_speed.py screening` three times; record cold 20 A time and iterations in `docs/m4-handoff.md` (speed table: new row "numpy tangent into NGSolve CSR") and update the spec §10 "Solve speed" item and CLAUDE.md "Speed" sentence with the measured numbers. State plainly whether the 4 s gate is met.
- [ ] **Step 10:** Commit `perf(solvers): numpy tangent into NGSolve's matrix and bulk netgen mesh build`.

### Task 2: One pool job per map point

**Files:**
- Modify: `src/srmcore/maps/run.py`, `src/srmcore/maps/api.py`
- Test: `tests/maps/test_run.py`, `tests/maps/test_build_map.py`
- Modify: `docs/m4-handoff.md`, `CLAUDE.md`, `examples/build_map_8_6.py` (progress text says points, not angles)

**Interfaces:**
- Consumes: `map_ordered(fn, items, workers, initializer, initargs, cancel, progress)` from `maps/pool.py` (results in item order, `None` for cancelled items).
- Produces: `solve_job((angle, current, excited)) -> dict` of scalars/1-D arrays for one point; `run_map` signature unchanged.

- [ ] **Step 1:** Test: `run_map` with `workers=2` on a 2-angle × 3-current grid (8/6 screening, skfem or ngsolve as existing tests do) gives the same arrays as `workers=1` to 1e-12; progress reports `total == n_angles * n_currents`.
- [ ] **Step 2:** Replace `solve_angle`/`_solve_job` with a per-point job; jobs ordered by descending current (then angle), results scattered back into the (angle, current) arrays. Keep `solve_angle` only if something else uses it (grep); otherwise delete it and its tests move to the per-point function.
- [ ] **Step 3:** `build_map` clamps workers to `min(workers, n_points, 61)`.
- [ ] **Step 4:** Update the `run.py` module docstring (one job per point).
- [ ] **Step 5:** `python -m pytest tests/maps -m "not slow"` passes.
- [ ] **Step 6:** Run `python examples\build_map_8_6.py 8` and `... 4`; record wall times in the handoff M4b table as new rows (label "per-point jobs + numpy tangent") and state whether the 30 s budget is met. Update CLAUDE.md "Speed" sentence.
- [ ] **Step 7:** Commit `perf(maps): one pool job per map point`.

### Task 3: Energy, L_inc and per-pole forces in the map

**Files:**
- Create: `src/srmcore/post/forces.py`
- Modify: `src/srmcore/maps/point.py`, `src/srmcore/maps/run.py`, `src/srmcore/maps/dataset.py`
- Test: `tests/post/test_pole_forces.py` (new), `tests/maps/test_run.py`, `tests/maps/test_dataset.py`

**Interfaces:**
- Produces: `pole_forces(problem: Magnetostatic2D, solution: FieldSolution, n_stator_poles: int) -> np.ndarray` shape (n_stator_poles, 2): [radial, tangential] force in N on each stator pole (stack length included), radial positive outward, tangential positive counter-clockwise, in the frame of pole k at angle k·2π/Ns. Stress on the stator side: f_r = −(B_r² − B_θ²)/(2μ0), f_θ = −B_r·B_θ/μ0, averaged over the band like `arkkio_torque` (∫_band f dS / (r_out − r_in) ≈ ∫ f r dθ at the band), each element assigned by centroid angle to the pole sector [k·2π/Ns − π/Ns, k·2π/Ns + π/Ns).
- Produces: `PointResult.pole_force` (n_poles, 2) (always computed); `MapResult` gains `energy` (angle, current), `l_inc` (angle, current, circuit) = ∂ψ_k/∂i_excited (NaN where withheld), `pole_force` (angle, current, pole, 2). Dataset `_DIMS` gains `energy: ("angle","current")`, `l_inc: ("angle","current","circuit")`, `pole_force: ("angle","current","pole","component")`. Failure-policy fill covers the new fields.

- [ ] **Step 1:** Tests for `pole_forces` on the 8/6 screening problem solved with the reference solver (or reuse a fixture from `tests/post/test_machine_8_6.py`): (a) zero current → all zeros; (b) 20 A on A at θ = 10°: Σ_k F_θ,k · (r_in + r_out)/2 = −arkkio_torque within 1 %; (c) at θ = 0, pole 0 (phase A) radial force < 0 and |net force vector| (sum of pole forces rotated to x-y) < 1e-3 × |F_r of pole 0| (A poles are diametrically opposite); (d) at θ = 0 the tangential force on pole 0 is below 1 % of its radial force.
- [ ] **Step 2:** Implement `post/forces.py` with the same midpoint quadrature as `arkkio_torque` (reuse `_MIDPOINTS` by importing from `post.quantities`).
- [ ] **Step 3:** `solve_point` computes `pole_force` from `design.machine.n_stator_poles`; `run_map` requests `with_l_inc=True` and stores the excited column of L_inc; energy from `PointResult.energy`.
- [ ] **Step 4:** Extend `_FIELDS`/fill so `energy`, `l_inc`, `pole_force` are PCHIP-filled along current like ψ; `MapResult` docstring lists the new fields with units.
- [ ] **Step 5:** Dataset: write/read the new arrays; a file missing any of them is a cache miss (covered by `KeyError`; add a test that writes an old-layout file without `l_inc` and checks `cached_map` returns None).
- [ ] **Step 6:** Run `python -m pytest tests/maps tests/post -m "not slow"`.
- [ ] **Step 7:** Commit `feat(maps): energy, L_inc and per-pole forces in the map dataset`.

### Task 4: ∂ψ/∂θ and inverse drive tables

**Files:**
- Create: `src/srmcore/maps/tables.py`
- Modify: `src/srmcore/maps/dataset.py` (store `dpsi_dtheta`)
- Test: `tests/maps/test_tables.py`

**Interfaces:**
- Produces:
  - `angle_spline(result: MapResult, values: np.ndarray) -> CubicSpline` — periodic cubic spline over one rotor pole pitch τ = 2π/Nr, built from `result.angles` plus the wrap-around point (angle + τ, same value), axis 0 = angle. Nr is `round(2π / period)`; take τ from a `period` argument: signature `angle_spline(angles, values, period)`.
  - `dpsi_dtheta(result: MapResult, period: float) -> np.ndarray` (angle, current, circuit), Wb-turns/rad, derivative of the periodic spline.
  - `@dataclass(frozen=True, eq=False) DriveTables`: `angles`, `psi_grid` (n_psi,), `current` (angle, psi) = i(θ, ψ) in A (NaN where ψ exceeds ψ(θ, I_max)), `torque` (angle, psi) = T(θ, ψ) (Arkkio), `flat` (angle, psi) bool where ∂ψ/∂i < `eps` (default `eps = 1e-3 × (La at lowest current)`), `monotone` (angle,) bool, `roundtrip_error` float (max |ψ(θ, i(θ,ψ)) − ψ| / ψ_max over defined points).
  - `drive_tables(result: MapResult, n_psi: int | None = None) -> DriveTables` — excited circuit only; PCHIP in current for ψ(i) and T(i), PCHIP of i(ψ) on monotone angles; non-monotone angles: `monotone[a] = False`, row NaN. ψ grid per ruling 5 (aligned curve at uniform currents, 2 × n_currents points, first point 0).
  - `MapResult` inputs must be complete: raise `ValueError("map is incomplete")` otherwise (all public functions in tables/results/checks/export share one helper `require_complete(result)` placed in `maps/run.py`).
- Dataset: `dpsi_dtheta` is written by `write_map` when given (computed in `store_map` from the result and the provenance's design Nr); read back as an extra return? Keep it simple: `write_map` stores `dpsi_dtheta` computed there; `read_map` ignores it (derivable). Test that the file contains it with the right shape.

- [ ] **Step 1:** Tests with a synthetic `MapResult` (no FEM): ψ(θ, i) = L(θ)·i with L(θ) = L0 + L1·cos(Nr·θ) and a saturating variant ψ = Ψs·tanh(L(θ)·i/Ψs); torque from the co-energy derivative. Check `dpsi_dtheta` against the analytic derivative (rel 1e-2 on 16 angles), the inverse round-trip < 1e-6 on the linear case, `flat` true only on the deeply saturated synthetic case, non-monotone angle flagged and NaN, incomplete map raises.
- [ ] **Step 2:** Implement `tables.py`.
- [ ] **Step 3:** Dataset `dpsi_dtheta`.
- [ ] **Step 4:** `python -m pytest tests/maps -m "not slow"`.
- [ ] **Step 5:** Commit `feat(maps): dpsi/dtheta and inverse drive tables`.

### Task 5: Standard results and key numbers

**Files:**
- Create: `src/srmcore/maps/results.py`
- Test: `tests/maps/test_results.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) KeyNumbers`: `la` (H), `lu` (H), `la_lu` (ratio), `peak_torque` (N·m, max |Arkkio| over the grid), `psi_max` (Wb-turns, excited ψ at aligned, I_max), `i_max` (A), `aligned_angle` (rad), `unaligned_angle` (rad).
  - `aligned_angle(machine, excited: str) -> float` — (k·ε) mod τ for phase letter index k (this is Task 8's rule; phase A → 0). Put it in `maps/grids.py`.
  - `key_numbers(result: MapResult, machine: RadialSRMParams) -> KeyNumbers` (ruling 6).
  - `inductance_curves(result, currents: Sequence[float] | None = None) -> np.ndarray` (angle, n_sel) secant ψ/i of the excited circuit at the selected grid currents (default: all non-zero grid currents); `torque_curves(result)` → Arkkio torque (angle, current) (just a view; skip if it is only `result.torque_arkkio` — then do not add it).
- [ ] **Step 1:** Tests on the synthetic map from Task 4 (move its builder to `tests/maps/map_fixtures.py`, unique basename): La, Lu, ratio, peak torque, ψ_max match the analytic values (rel 1e-2 for Lu via the spline, exact for grid points).
- [ ] **Step 2:** Implement.
- [ ] **Step 3:** Commit `feat(maps): standard results and key numbers`.

### Task 6: Cheap §7.3 map checks and `analyse_map`

**Files:**
- Create: `src/srmcore/maps/checks.py`
- Modify: `src/srmcore/maps/__init__.py`
- Test: `tests/maps/test_checks.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Check`: `name: str`, `status: Literal["pass", "warn", "fail"]`, `value: float`, `limit: float`, `detail: str`.
  - `map_checks(result: MapResult, design: Design) -> tuple[Check, ...]` with these names and rules (excited circuit e, stroke = unaligned → aligned in the motoring direction, i.e. θ from θ_a − τ/2 to θ_a; torque integrals via `angle_spline(...).integrate`):
    1. `coenergy_torque` — per non-zero current: |∫_stroke T dθ − (W′(θ_a) − W′(θ_a − τ/2))| / |W′(θ_a) − W′(θ_a − τ/2)|, max over currents; fail > 0.02.
    2. `arkkio_vs_nodal` — max |T_arkkio − T_vw| / peak |T|; fail > 0.01.
    3. `energy_identity` — max |W + W′ − ψ_e·i| / max(ψ_e·i); fail > 1e-3.
    4. `loop_energy` — at I_max: |∫_0^Imax (ψ_e(θ_a) − ψ_e(θ_u)) di − ∫_stroke T(I_max) dθ| / ∫_0^Imax (ψ_e(θ_a) − ψ_e(θ_u)) di, ψ along current by PCHIP integration, ψ at θ_u from the angle spline; fail > 0.02.
    5. `zero_mean_torque` — max over currents |∫_0^τ T dθ| / (peak·τ); fail > 0.01.
    6. `zero_torque_aligned_unaligned` — max |T(θ_a)|, |T(θ_u)| over currents / peak; fail > 0.01.
    7. `sign_pattern` — T ≤ 0.01·peak on grid angles in (θ_a, θ_u) and T ≥ −0.01·peak on (θ_u, θ_a + τ) (mod τ); value = worst violation / peak; fail > 0.
    8. `la_lu` — ratio La/Lu: < 2 fail, 2–3 warn, 3–15 pass, > 15 warn.
    9. `dpsi_di_positive` — min over angles of min Δψ_e along current / ψ_max; fail ≤ 0.
    10. `psi_bound` — ψ_max / (N_series · Js · w_pole · L · 1.1), N_series = turns_per_pole · Ns / m, w_pole = 2·r_bore·sin(βs/2), Js = stator material `saturation_polarisation`; fail > 1.
    11. `psi_decreasing` — ψ_e(θ, I_max) non-increasing over grid angles from θ_a to θ_u and non-decreasing from θ_u to θ_a + τ, tolerance 0.005·ψ_max; value = worst violation / ψ_max; fail > 0.005.
    12. `la_analytic` — La / La_est, La_est = p·N²·μ0·(r_bore·min(βs, βr)·L)/g with p = Ns/m poles per phase, N = turns_per_pole, g = air_gap; warn outside [0.5, 1.5].
    13. `lu_air_slot` — Lu / Lu_est, Lu_est = p·N²·μ0·(r_bore·βs·L)/(g + h_r), h_r = rotor_outer_radius − rotor_yoke_outer_radius; fail < 1.
    14. `iron_b_peak` — needs `MapResult.b_peak` (angle, current): peak |B| in stator and rotor iron per point (add it in this task: `PointResult.b_peak` from `saturation_report`'s iron groups or directly from `solution.b` over iron elements; dataset dim ("angle","current")); value = max b_peak / Js; warn > 1.15.
  - `@dataclass(frozen=True, eq=False) MapReport`: `result`, `key_numbers`, `tables`, `dpsi_dtheta`, `checks`; `ok` property = no check with status "fail".
  - `analyse_map(result: MapResult, design: Design) -> MapReport` (calls `require_complete`).
  - Export `analyse_map`, `MapReport`, `Check`, `KeyNumbers`, `DriveTables` from `maps/__init__.py`.
- [ ] **Step 1:** Unit tests on synthetic maps: each check passes on a consistent synthetic map and fails on a deliberately broken one (e.g. torque scaled by 1.1 fails `coenergy_torque`; flip sign fails `sign_pattern`; ratio 1.5 fails `la_lu`, 2.5 warns). Keep synthetic helpers in `tests/maps/map_fixtures.py`.
- [ ] **Step 2:** One FEM test: 8/6 `screening`, 3 angles (0, τ/4, τ/2)? — the spline needs the full pitch, so use `n_angles=8, n_currents=3` via `build_map(..., workers=4)`; mark `slow` if > 20 s. Record which checks pass/warn/fail in the task report (do not loosen limits to make them pass; report failures).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Commit `feat(maps): cheap map consistency checks and analyse_map`.

### Task 7: CSV and .mat exports

**Files:**
- Create: `src/srmcore/maps/export.py`
- Test: `tests/maps/test_export.py`

**Interfaces:**
- Produces:
  - `export_csv(report: MapReport, directory) -> list[Path]` writing `psi_map.csv` (long format, header `angle_rad,current_A,psi_<circuit>...,torque_Nm,coenergy_J,l_inc_H,status,filled`), `inverse_current.csv` (`angle_rad,psi_Wb,current_A,torque_Nm,flat`), `key_numbers.csv` (`name,value,unit`). Plain `csv` module or `np.savetxt`; `repr`-precision floats.
  - `export_mat(report: MapReport, path) -> Path` via `scipy.io.savemat`: `angles`, `currents`, `psi` (angle × current × circuit), `torque`, `coenergy`, `l_inc`, `dpsi_dtheta`, `psi_grid`, `current_of_psi`, `torque_of_psi`, `status`, `circuits`, `key_numbers` (struct), `provenance_hash` if given (optional keyword argument).
  - Export both from `maps/__init__.py`.
- [ ] **Step 1:** Round-trip tests (Review Focus 5) on the synthetic map: read CSV with `np.loadtxt`/`csv`, `.mat` with `scipy.io.loadmat`, compare to 1e-12 relative.
- [ ] **Step 2:** Implement.
- [ ] **Step 3:** Commit `feat(maps): CSV and .mat lookup-table exports`.

### Task 8: Diagonal maps for every phase

**Files:**
- Modify: `src/srmcore/maps/grids.py` (`aligned_angle` from Task 5 lives here), `src/srmcore/maps/run.py`, `src/srmcore/maps/api.py`, `src/srmcore/maps/checks.py`/`results.py` (use `aligned_angle(machine, result.excited)` everywhere phase A was assumed)
- Test: `tests/maps/test_grids.py`, `tests/maps/test_run.py`, a FEM test in `tests/maps/test_phases.py`

**Interfaces:**
- Produces: `check_excited(excited, n_phases)` accepts any phase letter of the machine; `apply_failure_policy(result, aligned: float)` uses the given aligned angle (`np.isclose` on angles modulo τ); `build_map` shifts the angle grid by `aligned_angle(machine, excited)` (then snaps, wraps into [0, τ), sorts).
- [ ] **Step 1:** FEM test (8/6 screening, reference solver or ngsolve, few points): for each phase B, C, D, torque at θ_k with 10 A on phase k is below 1 % of the torque at θ_k + τ/4, and ψ_k(θ_k) equals ψ_A(0) within 1e-3 relative (symmetry). Also `aligned_angle` unit test: 8/6 gives [0, 15°, 30°, 45°] for A–D; 12/8 (m = 3) gives [0, 15°, 30°]; 6/4 (m = 3): [0, 30°, 60°].
- [ ] **Step 2:** Implement; lift the phase-A restriction; update docstrings and `run_map`'s circuit validation.
- [ ] **Step 3:** Update spec §10 M4b item (vi) as done; add a §11 row.
- [ ] **Step 4:** Commit `feat(maps): diagonal maps for every phase`.

### Task 9: Overlap map, coupling and reciprocity checks

**Files:**
- Create: `src/srmcore/maps/overlap.py`
- Modify: `src/srmcore/maps/dataset.py` (overlap group), `src/srmcore/maps/__init__.py`
- Test: `tests/maps/test_overlap.py`

**Interfaces:**
- Produces:
  - `overlap_window(machine) -> tuple[float, float] | None` per ruling 9 (A→B handover: start θ_B − (βs + βr)/2, end τ, both in [0, τ] after taking θ_B − (βs+βr)/2 modulo τ; None when (βs + βr)/2 ≤ ε).
  - `@dataclass(frozen=True, eq=False) OverlapResult`: `angles`, `currents_a`, `currents_b`, `circuits`, `psi` (angle, ia, ib, circuit), `torque_arkkio` (angle, ia, ib), `l_inc` (angle, ia, ib, 2, 2) = ∂ψ_{A,B}/∂i_{A,B}, `status` (angle, ia, ib), `complete: bool`.
  - `run_overlap_map(static, design, angles, currents_a, currents_b, solver_name, workers, progress, cancel) -> OverlapResult` — one pool job per point (reuse the pool worker initialiser from `run.py`; generalise the job to take a current dict), `with_l_inc=True`. Failure policy: any NONCONVERGED point in a complete overlap map raises `MapFailed` (spec §8.1 overlap window rule); no filling.
  - `build_overlap_map(design, i_max, *, solver="ngsolve", workers=None, n_angles=8, n_currents=8, cache_dir=None, progress=None, cancel=None) -> OverlapResult | None` (None for an empty window). Cache: provenance with `"overlap": True` and both grids; stored as its own HDF5 file.
  - `coupling_checks(overlap: OverlapResult) -> tuple[Check, ...]`: `coupling_psi` = max over points with both currents > 0 of |ψ_A(ia, ib) − ψ_A(ia, 0)| / max ψ_A (and the same for ψ_B against ψ_B(0, ib)), warn > 0.02 (coupling is a property, not an error: warn means the superposition drive model is not enough); `coupling_torque` = max |T(ia, ib) − T(ia, 0) − T(0, ib)| / peak |T|, warn > 0.02; `reciprocity` = max |L_AB − L_BA| / max(|L_AA|), fail > 1e-3.
- [ ] **Step 1:** Tests: `overlap_window` for the 8/6 (βs = 20°, βr = 22°: (βs+βr)/2 = 21° > ε = 15°, window [54°, 60°] = [θ_B − 21° + τ, τ]) and a narrow-pole case returning None (Review Focus 4). Coupling/reciprocity checks on synthetic OverlapResults (pass and warn/fail cases). One FEM test with a 2 × 3 × 3 overlap grid on 8/6 screening (`slow` if > 20 s): reciprocity passes.
- [ ] **Step 2:** Implement; add overlap group read/write in `dataset.py` (`write_overlap`/`read_overlap`) and cache helpers reusing `_path` with a distinct prefix `overlap_`.
- [ ] **Step 3:** Update spec §10 M4b item (viii) as done.
- [ ] **Step 4:** Commit `feat(maps): overlap map with coupling and reciprocity checks`.

### Task 10: FEM-backed checks (held-out interpolation, band-radius independence)

**Files:**
- Create: `src/srmcore/maps/fem_checks.py`
- Modify: `src/srmcore/post/quantities.py` (add `arkkio_torque_annulus(problem, solution, region)`; share code with `arkkio_torque`)
- Test: `tests/maps/test_fem_checks.py`

**Interfaces:**
- Produces:
  - `arkkio_torque_annulus(problem, solution, elements: np.ndarray, r_in: float, r_out: float) -> float`; `arkkio_torque` becomes a call to it with the band. Gap annuli: regions `airgap_rotor` (rotor OD → band inner radius) and `airgap_stator` (band outer radius → bore radius); radii from `design.machine` (`rotor_outer_radius`, `band_inner_radius`, `band_outer_radius`, `bore_radius`).
  - `fem_checks(design, result: MapResult, *, solver="ngsolve", workers=None, n_samples=16) -> tuple[Check, ...]` — runs only when `design.mesh.preset in ("full", "reference")`, otherwise returns `()`. `held_out_psi` / `held_out_torque`: solve at `n_samples` mid-points (angle mid-points × current mid-points, evenly subsampled, excluding the zero-current column), compare with the periodic-spline × PCHIP interpolant of the map; fail when ψ error > 0.5 % of ψ at that point... use the spec wording: ψ within 0.5 % (relative to ψ_max), T within 1 % of peak. `band_radius`: at 3 points (θ = τ/8, τ/4, 3τ/8 from aligned, at I_max) solved with `keep_field=True`, max |T_gap_layer − T_band| / peak over both gap layers; fail > 0.01 (ruling 7).
- [ ] **Step 1:** Tests: `arkkio_torque_annulus` on the band equals `arkkio_torque` exactly; on the gap layers within 1 % of peak at 20 A, θ = 10° on the 8/6 screening mesh. `fem_checks` returns `()` for screening. One `slow` test running `fem_checks` on a small `full`-preset map (8 angles × 4 currents).
- [ ] **Step 2:** Implement.
- [ ] **Step 3:** Commit `feat(maps): held-out interpolation and band-radius checks`.

### Task 11: Screening-vs-full fidelity check

**Files:**
- Create: `src/srmcore/maps/fidelity.py`, `examples/fidelity_8_6.py`
- Test: `tests/maps/test_fidelity.py`
- Modify: `docs/m4-handoff.md`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) FidelityReport`: `designs: int`, `rel_error: dict[str, np.ndarray]` (key number → per-design |screening − full| / |full|), `spearman: dict[str, float]`, `ok: bool` (all errors ≤ 0.03 and all ρ ≥ 0.95).
  - `fidelity_check(designs: Sequence[Design], i_max: float, *, solver="ngsolve", workers=None, cache_dir=None, progress=None) -> FidelityReport` — for each design builds the screening map and the full map (same machine, `mesh.preset` switched with `model_copy(update=...)`), key numbers compared: `la`, `lu`, `peak_torque`, `psi_max`. Spearman over designs per key number (`scipy.stats.spearmanr`); with fewer than 3 designs ρ is NaN and `ok` ignores it.
- [ ] **Step 1:** Unit test with `build_map` monkeypatched to return synthetic maps (no FEM): errors and ρ computed right; `ok` false when one key number is 4 % off.
- [ ] **Step 2:** Implement; `examples/fidelity_8_6.py` runs 4 variants of the example 8/6 (stator pole arc 18°, 20°, 22°; rotor pole arc 22° / 24° mix) at I_max = 20 A with a cache dir under the scratch/temp folder, prints a table.
- [ ] **Step 3:** Run the example (it takes minutes; run in the background) and record the table, wall times of the `full` maps against the 5 min budget, and pass/fail in `docs/m4-handoff.md`.
- [ ] **Step 4:** Commit `feat(maps): screening-vs-full fidelity check`.

### Task 12: Goldens and M4 close-out docs

**Files:**
- Create: `tests/maps/test_goldens.py`, `tests/maps/goldens_8_6.json`
- Modify: `CLAUDE.md`, spec §9/§10/§11, `docs/m4-handoff.md`, `examples/build_map_8_6.py` (print key numbers and check summary via `analyse_map`)

- [ ] **Step 1:** `slow` golden test: the example 8/6 `screening` map at I_max = 20 A (build with `workers=4`): key numbers match `goldens_8_6.json` to 1e-3 relative, and the check statuses match the stored statuses. Generate the JSON once from the current engine (document the command in the test docstring).
- [ ] **Step 2:** Update `examples/build_map_8_6.py` to print key numbers and each check's status.
- [ ] **Step 3:** Docs: CLAUDE.md "Current state" (M4 complete), map pipeline section lists the new modules; spec §10 M4b→M4c items updated (done / still open with reasons, including rulings 3 and 7's deferred knee check); spec §11 row "M4c decisions" with this plan's rulings; handoff renamed in content to an M5 handoff section ("M5 carry-in").
- [ ] **Step 4:** Full fast suite `python -m pytest -m "not slow"` green and under 10 minutes (record time); slow suite for `tests/maps` green.
- [ ] **Step 5:** Commit `docs: M4 complete; goldens for the 8/6 screening map`.
