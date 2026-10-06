# M5 roadmap: M5b–M5e2

M5 earns `srmcore` the **"EM-validated"** label (core spec §2.3, §8.2–8.6, §9). M5a (mesh convergence, presets, angle grid) is done: see `docs/m5a-results.md` and spec §11 (2026-10-03). Each remaining sub-milestone runs in its own session with the usual cycle: brainstorm → spec → plan → subagent-driven build → final review → local merge on the owner's yes.

Order: **M5b → M5c → M5d → M5e.** M5b and M5c are independent (either can go first). M5d needs the end-winding hook (built in M5d). M5e comes last and closes M5.

## Cross-cutting owner items (decide when the milestone that needs them starts)

| Item | Needed by | Where |
|---|---|---|
| Speed budgets re-baseline (decided and measured 2026-10-06) | closed | spec §11 2026-10-05 |
| Band noise in `full` (accepted, covered by the 1.7 % held-out limit; decided 2026-10-05) | closed | spec §11 2026-10-05 |
| `iron_b_peak` check definition (area p99.9; decided 2026-10-05) | closed | spec §11 2026-10-05 |
| Material data: M19 / steel_1010 Js and densities are unchecked FEMM/handbook values (grade C) | M5c, M5d (uncertainty), M5e (±2 % Js check) | spec §10 [M2→M5] |
| Outer air ring default (`outer_air_thickness` = 0 now) | M5c (FEMM boundary must match) | spec §11 2026-09-29 |
| Search margin 1.05 revisit | after M5e | handoff 2026-10-02 |

## M5b: TEAM Problem 24

**Done 2026-10-04:** see `docs/m5b-team24-results.md`.

- **Goal:** the magnetostatic TEAM 24 comparison counts as validation evidence (spec §2.3, §8.2 suite 5).
- **Have:** `tests/team24_fixture.py`, `examples/team24_check.py`, `docs/m5b-team24-results.md` (static torque -13.1 % vs measured; current rise up to +18.6 % ahead; both solvers agree to 5e-13).
- **Owner decisions (2026-10-04):**
  1. Table I H read as ×10⁴ A-t/m, points 1–17 used, Js 2.0 T assumed.
  2. No pass/fail gate; the result is reported as error ± uncertainty.
  3. Current-rise and static deviations are consistent with the omitted 3D end flux (steady-state deficit, mid-rise current lead) and eddy currents (early lag, mid-rise lead; zero at steady state); Table V (rotor-pole flux) is compared.
- **Scope (done):** slow test, uncertainty budget and results doc; see `docs/m5b-team24-results.md` and the spec §11 entry.
- **Done:** slow test green locally on Windows (Linux coverage of the slow test waits for M5e's "all suites on CI" item); result with error and uncertainty recorded; spec §10 TEAM 24 item closed in §11.
- **Size:** small (FEM runs are seconds).

## M5c: FEMM fixtures (cross-tool)

**Done 2026-10-04:** see `docs/m5c-femm-results.md`.

- **Goal:** agreement with FEMM 4.2 within §8.3 (ψ ±2 %, mid-range torque ±3 %, near-alignment/saturated torque ±5 %) on M19 reference machines: Krishnan 8/6 plus one published 12/8 or 24/16 with full geometry.
- **Have:** FEMM 4.2 installed; pyfemm starts it (install with `.venv\Scripts\python -m pip install pyfemm` when M5c starts). `docs/reference-machines.md` audits the machines.
- **Owner decisions first:**
  1. Krishnan 8/6 missing fields: `fill_factor`, `slot_liner_thickness`, `coil_inner_clearance` (assume values; they barely affect EM).
  2. Second machine: no published 12/8 or 24/16 has full geometry. Jiang 24/16 needs `rotor_yoke_thickness`, `rotor_pole_taper`, liner and clearance assumptions, and its 1 mm pole-shoe fillet has no topology counterpart; it is built inside `waive_rules("self_starting")`. Alternative: a synthetic 12/8/24/16 (conftest) compared against FEMM only — weaker but complete geometry.
  3. FEMM boundary to match ours (A = 0 at the stator OD) or an outer air ring on both.
- **Scope:** a `tools/` pyfemm script that builds the same geometry and B-H in FEMM and writes versioned fixtures once on Windows (give FEMM the raw B-H plus its LamFill, not the stacked curve, or stacking is applied twice; same fitted B-H otherwise); FEMM's own mesh converged so its discretisation error does not eat the ±2 %; slow tests comparing ψ and torque at the agreed points; the M43 grade C library curve if a chosen machine needs it.
- **Done:** fixtures committed with provenance; slow comparison green within §8.3; deviations explained.
- **Size:** medium; fixtures are generated once.

## M5d: measured Krishnan 6/4 + end-winding hook

**Done 2026-10-05:** see `docs/m5d-krishnan-results.md` (decisions in spec §11). Decisions: book bore with dissertation shaft and rotor pole height, coil packed against the yoke at packing 0.5, M19, analytic end-winding hook (Grover partial inductances, image factor 1–2, midpoint reported, no calibration), Table 1 values only. Results: the correction moves La toward the measurement (20 A: -21.6 % to -15.0 %) but Lu away (10 A: +13.0 % to +27.3 %, the 2D Lu is already above measured); T_avg is unchanged (-16.9 % at 10 A, -28.5 % at 20 A), about 9 % of it at 20 A from the too-high 2D Lu and the rest from the saturated La; the 20 A La residual is outside the stated model uncertainty and is unlikely to come from the lamination curves alone (if all linked flux crossed the pole it would be about 2.6 T, an upper bound since slot and end leakage carry part; the budget has no row for the unidentified "E140" steel's Js) or from the end turns (3D iron-end fringing or the measurement). TEAM 24 independent check: mid-rise current lead +18.6 % to +8.1 %, with early over-correction (2 ms: -1.7 % to -17.3 %). Open for M5e: the uncertainty budget and report must carry these as residuals; fringing stays uncalibrated.

- **Goal:** measured-SRM comparison reported **with error and uncertainty, before and after end-effect correction** (spec §2.3).
- **Have:** Krishnan 6/4 measured La, Lu and stroke-averaged torque at 2 rotor positions × 3 currents (1, 10, 20 A), Table 2.3 (`docs/reference-machines.md`).
- **Owner decisions first:**
  1. Missing fields: `shaft_diameter`, `rotor_yoke_thickness` (the single "back iron" figure is assumed stator), `fill_factor`, `slot_liner_thickness`, `coil_inner_clearance`.
  2. Lamination grade and B-H source for the 6/4 (grade C library curve; M43 if named).
  3. End-winding model: which hook (analytic end-turn inductance added to ψ, an axial-length factor, or a calibrated correction), and what it may be calibrated on (calibrating on the same data it is judged against is circular).
- **Scope:** build the 6/4 inside `waive_rules("self_starting")`; maps at the measured points; end-winding hook in the engine (spec §9: hook + end-effect calibration); comparison table with error and an uncertainty budget (material grade, mesh estimate from M5a, end-effect correction, digitisation); apply the end-effect hook to TEAM 24 (`tests/validation/test_team24.py`) as an independent check (TEAM 24 is not used for calibration).
- **Done:** report table before and after the end-effect correction, each with uncertainty; hook tested; spec §11 entry.
- **Size:** medium.

## M5e1: label logic and uncertainty budget (engine)

**Done 2026-10-05:** spec `docs/superpowers/specs/2026-10-05-m5e1-label-budget-design.md`, decisions in core spec §11. `srmcore.maps.validation.em_validate(design, result)` returns the §8.5 checks (point convergence on `full` vs `reference`, held-out checks, no filled points, preset, material grade, engine version) and the §8.4 worst-case budget (mesh, material with the Js ±2 % check, end effect, digitisation) on the end-winding-corrected key numbers. `VALIDATED_VERSIONS` is empty, so no label is awarded yet. `b_peak` is now the area-weighted 99.9th percentile of iron |B| and the `iron_b_peak` check compares it with the last stacked B-H point (the band-noise and `iron_b_peak` owner items are closed). Example: `examples/em_validate_8_6.py`.

## M5e2: library, report, validated version, CI, speed

**Done 2026-10-06 (slow suite green on CI for the `v0.4.0` tag, Linux 59 min, Windows 91 min; report verdict PASS):** spec `docs/superpowers/specs/2026-10-05-m5e2-validated-release-design.md`, report `docs/validation-report.md`. srmcore 0.4.0 is in `VALIDATED_VERSIONS`; the 8/6 `full` map earns "EM-validated". Library adds 10JNEX900 (B), Hiperco 50A (B), Hiperco 50HS 720/740/760 °C (C), M43 (C). Speed budgets re-baselined: `screening` < 430 s, `full` < 44 min, `full` extras < 31 min. Slow suite locally 52 passed in 38 min (peak 5.1 GB per process).

- **Goal:** close M5: the engine version is "EM-validated".
- **Scope (spec §8.4–8.6, §9):**
  1. Library adds: JFE 10JNEX900, Hiperco 50A and 50HS (grade B, digitised; `digitisation_error`), M43 (grade C) if not done in M5c/M5d.
  2. Validation report (markdown + plots): engine version, pinned dependency versions and licences, every comparison (M5a–M5d) with pass/fail or error ± uncertainty, and the `examples/em_validate_8_6.py` result.
  3. Add the engine version to `VALIDATED_VERSIONS` once the report passes.
  4. All fast and slow suites green on Windows and Linux (CI slow-suite runner).
  5. Speed budgets met on the owner's machine (after the owner re-baselines them).
  6. Revisit: adaptive `reference` preset only if a design fails the uniform `reference` point check.
- **Done:** M5 definition of done in `docs/handoff-2026-10-02-m5.md` met; spec §9 M5 row marked complete; then revisit the search margin and move to v0b. Handoff: `docs/handoff-2026-10-05-m5e2.md`.

## After M5: visualization (noted 2026-10-04, unscheduled)

- The core stays plot-free and returns arrays. Static figures use matplotlib (PNG); interactive charts use Plotly as an optional `[viz]` extra in examples and reports, and plotly.js in the web UI (sub-project #9).
- Queued: a rotating-rotor field animation (`examples/animate_rotation.py`, matplotlib to GIF/MP4 from `solve_point(..., keep_field=True)`) and an interactive map viewer (`examples/map_viewer.py`, HTML).
- ParaView only if interactive field inspection is ever needed (VTK export via meshio).
