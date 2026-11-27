# R5e gate V4 (Bike v1, part 2): peak-heat check

Merged 2026-11-28, PR #46. Versions after the merge: srmapp 0.11.0 (srmcore stays 0.8.0, srmweb 0.12.1, `web/` 0.12.0).
Spec `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md`. Plan `docs/superpowers/plans/2026-11-26-r5e-v4-v5.md`. Detailed results `docs/r5-thermal-results.md` (V4 section), sources `docs/r5-sources.md` section 9.

## Goal

Check the rating's peak transient against a measured one: Kiyota 2014 Fig. 8, the coil-end rise of an 18/12 machine in a 14 s pulse. Done when: V4 has a verdict on main, its residual is in the `end_winding_model` row, and iron has heat capacity in the rating.

## What shipped

- 10JNEX900 thermal block: `specific_heat` 438 J/(kg K), carried over from Faiz 2009 Table II (grade C). Map hashes are unchanged.
- `srmapp.thermal_network`: iron capacity is c x density x stacking factor (0.90), per gross m3 like the iron heat load.
- `srmapp.cooling.END_WINDING_PEAK_RESIDUAL` 0.007159: when the `end_winding_model` row is unfavourable, the rated set divides each end-winding lump capacity by 1 + this. The row moves the peak only, so its budget share stays 0 K.
- `examples/kiyota_thermal_check.py`, `tests/kiyota_thermal.py`, `tests/thermal/test_thermal_kiyota.py`, and the `stator_arc`, `rotor_arc` and `rotor_yoke` parameters of `tests/kiyota_18_12.py`.
- Record `docs/validation/r5_v4_kiyota.json`.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| V4, measured 39.5 +- 0.4 K trace | pass: nominal 39.22 K, 0.7 % cold (r = +0.00716) | LattePanda, `full`, `r5_v4_kiyota.json` |
| V4, printed 41 K | pass: 4.5 % cold (r = +0.0454), inside the band only through the resistance row | same |
| Band (rows plus numerical error) | 36.53 to 42.48 K | same |
| Presets and numerical error | `screening`, `full` and `reference` within 0.005 K; time step and mesh 0.014 K | same |
| Without iron capacity | 49.2 K (+25 %) | `docs/r5-thermal-results.md` |
| Closed-form adiabatic copper rise | 40.60 K | `r5_v4_kiyota.json` |
| 8/6 fixture, hot spot at the peak end | 1.9 to 2.9 K lower with iron capacity (peaks bound by the envelope, unchanged); recorded before the stacking factor | `docs/r5-thermal-results.md`, first rating |
| V4 run | 57.5 min, 2.6 GB | LattePanda, unit kiyota-v4b |

Against the 10 to 15 % target: V4 checks the copper heating of a short pulse. It does not check the cooling paths, a 30 s peak from warm, or the continuous rating.

## Decisions

- 2026-11-27, owner: 10JNEX900 specific heat 438 J/(kg K) from Faiz 2009, grade C; V5 is not a gate.
- 2026-11-27, builder: nominal resistance is the winding-only 92.5 mOhm, with a row up to the 97.8 mOhm terminal value.
- 2026-11-27, builder: the residual goes into the row although it is inside the 0.4 K reading error (the safe side).
- 2026-11-27, builder: V4's own rated set leaves out `end_winding_model` (it would correct itself).
- 2026-11-27, builder: iron capacity takes the stacking factor, and V4 was re-run (the error was on the unsafe side).

## Open after this step

- 10JNEX900 thermal expansion and through-stack conductivity: the lamination-data row of the tracker (jystator email).
- The rest of R5e, the 8/6 and bench-target demonstration: tracker row 10k.
- Cooling paths and a 30 s peak from warm have no measured check: before the bike search ranks on peak ratings.
- `RATING_BUDGET_S` not re-timed (one fewer solve per speed): tracker, Later.
- Cases evaluated at srmapp 0.10.0 show beside 0.11.0 cases with no stale chip: tracker.
- The bike-gates plan rebases on this step and takes srmapp 0.12.0: Bike motor v1, step 0.

## Evidence

- PR #46: fast CI green, run 46035824269 (7 jobs). Main after PRs #46 and #45: fast CI green, run 46054418918 (9 jobs, 18 min wall time). Fast suite locally on 6ac43d7: 1816 passed, 1 skipped.
- Built from the plan, one implementer and one review per task, then a final whole-branch review, one fix wave (with the V4 re-run) and its scoped re-review.
