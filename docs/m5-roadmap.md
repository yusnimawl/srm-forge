# M5 roadmap: M5b–M5e

M5 earns `srmcore` the **"EM-validated"** label (core spec §2.3, §8.2–8.6, §9). M5a (mesh convergence, presets, angle grid) is done: see `docs/m5a-results.md` and spec §11 (2026-10-03). Each remaining sub-milestone runs in its own session with the usual cycle: brainstorm → spec → plan → subagent-driven build → final review → local merge on the owner's yes.

Order: **M5b → M5c → M5d → M5e.** M5b and M5c are independent (either can go first). M5d needs the end-winding hook (built in M5d). M5e comes last and closes M5.

## Cross-cutting owner items (decide when the milestone that needs them starts)

| Item | Needed by | Where |
|---|---|---|
| Speed budgets re-baseline (`full` maps now 27–68 min) | M5e (exit criterion "speed budgets met") | spec §10 [M5a→M5] |
| Band noise in `full` (dominates held-out error; option: more band divisions) | M5c (FEMM ±2 %/±3 % comparisons), M5e | spec §10 [M5a→M5] |
| `iron_b_peak` check definition (corner singularity, warns on the 8/6 golden) | any milestone; best before M5e | spec §10 [M5a→M5] |
| Material data: M19 / steel_1010 Js and densities are unchecked FEMM/handbook values (grade C) | M5c, M5d (uncertainty), M5e (±2 % Js check) | spec §10 [M2→M5] |
| Outer air ring default (`outer_air_thickness` = 0 now) | M5c (FEMM boundary must match) | spec §11 2026-09-29 |
| Search margin 1.05 revisit | after M5e | handoff 2026-10-02 |

## M5b: TEAM Problem 24

- **Goal:** the magnetostatic TEAM 24 comparison counts as validation evidence (spec §2.3, §8.2 suite 5).
- **Have:** `tests/team24_fixture.py`, `examples/team24_check.py`, `docs/team24-feasibility.md` (static torque +6.4 % vs measured; current rise within 12 %, faster than measured between 10 and 40 ms; both solvers agree to 1e-13).
- **Owner decisions first:**
  1. Table I H-column units: confirm 400–39634 A/m (the fixture's reading) against the printed table.
  2. Acceptance criterion: proposed static torque within 10 % at 7.41 A, current rise "follows the measured shape". Decide the shape criterion in numbers.
  3. The 2 ms (−12.5 %) and 10–40 ms (+12 %) current-rise deviations: investigate cause, or accept and put in the uncertainty budget.
- **Scope:** turn the feasibility script into a slow test with the agreed criteria; uncertainty budget entry (3D end effects, measured R 3.09 vs 3.12 Ω, assumed Js 2.6 T, digitisation); a section of the validation report. Optional: torque vs current at the same current (removes the time-axis error).
- **Done:** slow test green on Windows and Linux; result with error and uncertainty recorded; spec §10 TEAM 24 item closed in §11.
- **Size:** small (FEM runs are seconds).

## M5c: FEMM fixtures (cross-tool)

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

- **Goal:** measured-SRM comparison reported **with error and uncertainty, before and after end-effect correction** (spec §2.3).
- **Have:** Krishnan 6/4 measured La, Lu and stroke-averaged torque at 2 rotor positions × 3 currents (1, 10, 20 A), Table 2.3 (`docs/reference-machines.md`).
- **Owner decisions first:**
  1. Missing fields: `shaft_diameter`, `rotor_yoke_thickness` (the single "back iron" figure is assumed stator), `fill_factor`, `slot_liner_thickness`, `coil_inner_clearance`.
  2. Lamination grade and B-H source for the 6/4 (grade C library curve; M43 if named).
  3. End-winding model: which hook (analytic end-turn inductance added to ψ, an axial-length factor, or a calibrated correction), and what it may be calibrated on (calibrating on the same data it is judged against is circular).
- **Scope:** build the 6/4 inside `waive_rules("self_starting")`; maps at the measured points; end-winding hook in the engine (spec §9: hook + end-effect calibration); comparison table with error and an uncertainty budget (material grade, mesh estimate from M5a, end-effect correction, digitisation).
- **Done:** report table before and after the end-effect correction, each with uncertainty; hook tested; spec §11 entry.
- **Size:** medium.

## M5e: uncertainty budgets, report, label

- **Goal:** close M5: the engine version is "EM-validated".
- **Scope (spec §8.4–8.6, §9):**
  1. Uncertainty budget per key result (La, Lu, peak torque, ψ at I_max): material grade, mesh error (M5a: `full` ψ 0.25 %, torque 0.36 %; held-out 1.7 %), end-effect correction (M5d), digitisation.
  2. §5.2 ±2 % Js sensitivity check.
  3. Library adds: JFE 10JNEX900, Hiperco 50A and 50HS (grade B), M43 (grade C) if not done in M5c/M5d.
  4. Validation report (markdown + plots): engine version, pinned dependency versions and licences, every comparison (M5a–M5d) with pass/fail or error ± uncertainty.
  5. Label logic (§8.5): `reference`-preset convergence check per design, no interpolated NONCONVERGED points, material grade recorded.
  6. Speed budgets met on the owner's machine (after the owner re-baselines them).
  7. All fast and slow suites green on Windows and Linux (CI).
  8. Revisit: adaptive `reference` preset only if a design fails the uniform `reference` check.
- **Done:** M5 definition of done in `docs/handoff-2026-10-02-m5.md` met; spec §9 M5 row marked complete; then revisit the search margin and move to v0b.
