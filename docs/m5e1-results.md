# M5e1 results: `em_validate` on the 8/6 `full` map

`em_validate` on the 8/6 golden design (`full` preset, default 48 × 20 grid, I_max 20 A, NGSolve) passes every label check except `engine_version`, so the label is withheld only because no engine version is validated yet (M5e2 adds 0.3.0 after the validation report). The worst-case uncertainty of every key number is about ±10 %, and almost all of it is the grade C allowance of the M19 library curve.

Run: `.venv\Scripts\python -u examples\em_validate_8_6.py` on the owner's laptop, 2026-10-05, srmcore 0.3.0 (commit cdb39a8). Map 1755 s (8 workers), `em_validate` 400 s. Raw output: `docs/m5e1-data/em_validate_8_6.txt` (ASCII log; "??" stands for ψ and −).

## Checks

| Check | Status | Value | Limit |
|---|---|---|---|
| engine_version | fail | srmcore 0.3.0, none validated | — |
| preset | pass | full | full or reference |
| no_filled_points | pass | 0 | 0 |
| map_matches_design | pass | 0 | 0.001 |
| point_convergence_psi | pass | 0.168 % (worst at Lu) | 0.5 % |
| point_convergence_torque | pass | 0.113 % of peak | 1 % |
| held_out_psi | pass | 0.117 % of ψ_max | 0.5 % |
| held_out_torque | pass | 0.543 % of peak | 1.7 % |
| held_out_converged | pass | 0 skipped | 0 |
| band_radius | pass | 0.160 % of peak | 1 % |
| material_grade | pass | stator C, rotor C | recorded |
| budget_finite | pass | all finite | — |

## Uncertainty budget (relative half-spread, % of the end-corrected value)

| Row | La | Lu | Peak torque | ψ_max |
|---|---|---|---|---|
| mesh (`full` vs `reference`) | 0.118 | 0.163 | 0.113 | 0.032 |
| material (Js +2 % only, + grade C 10 %) | 9.961 | 9.652 | 10.003 | 9.920 |
| end effect (image factor 1 to 2) | 0.131 | 1.162 | 0 | 0.268 |
| digitisation | 0 | 0 | 0 | 0 |
| **total** | **10.209** | **10.976** | **10.117** | **10.220** |

| Key number | 2D map | End-corrected (image factor 1.5) |
|---|---|---|
| La (mH, at 1 A) | 32.869 | 32.999 |
| Lu (mH, at 1 A) | 3.5887 | 3.7183 |
| Peak torque (N·m) | 12.436 | 12.436 |
| ψ_max (Wb-turns, 20 A) | 0.3203 | 0.32289 |

## Reading

- Js −2 % is impossible for M19 (its data already reach J = 2.006 T > 0.98 · Js), so the Js part uses +2 % only. That part is near zero at the 1 A La/Lu points (linear) and small at 20 A. The material row is in effect the grade C allowance (10 %, scaled by 2D / corrected value).
- The mesh and held-out errors are a factor 3–30 below their limits on this design; the M5a presets hold.
- Iron-end 3D fringing is not modelled and is not in the budget; the end-effect row covers only the end-winding model spread.
- With a grade A or B steel (M5e2 library adds) the total would drop to 0.1–1.3 % (A; Lu largest, from the end-winding row) or 3.1–4.2 % (B) for this machine.
