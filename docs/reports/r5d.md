# R5d: Thermal tab

Merged 2026-11-22, PR #35. Versions after the merge: srmapp 0.9.0, srmweb and `web/` 0.12.0 (srmcore unchanged at 0.8.0).
Spec `docs/superpowers/specs/2026-11-21-r5d-thermal-tab-design.md`. Plan `docs/superpowers/plans/2026-11-21-r5d-thermal-tab.md`. Detailed results `docs/r5-thermal-results.md` (section R5d).

## Goal

Show every rated design's thermal rating in the web app, so the owner sees what limits a design, and count the rating in the evaluate estimate.

## What shipped

- Thermal tab on evaluated cases: verdict, speed table, torque curves, temperature map (steady or peak end, speed picker), tornado of the budget rows, rotor stress and cooling lines, notes.
- Chips for rating, cooling and iron band.
- Thermal section in the run report.
- Rated continuous and peak kW/kg and kW/L axes and columns in the options graph and the cases table.
- Evaluate estimate counts the rating time (store schema v3, table `rating_times`, `cases.RATING_BUDGET_S`).
- `examples/rating_timing.py`.

## Results

Rating time on the LattePanda (i5-1340P), 8/6 reference case, 2026-11-22.

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Rating span, `screening` | 850.0 s (evaluate total 1070.3 s) | `docs/validation/r5d_rating_screening.json` |
| Rating span, `full` | 1631.0 s (evaluate total 2738.0 s) | `docs/validation/r5d_rating_full.json` |
| `RATING_BUDGET_S`, screening / full / reference | 1063 / 2039 / 8155 s | `cases.py` |
| Fast suite | 1767 passed | merge |
| vitest | 343 passed | merge |
| Browser check at 1440 px and 375 px | passed | headless Chromium |
| Rating numbers | unchanged from R5c | same cases |

## Decisions

- 2026-11-22, builder: one requirement check is stored per evaluation.
- 2026-11-22, builder: a check-only evaluation shows "Edit, then Evaluate, for the full rating".
- 2026-11-22, builder: rating times are recorded only when the check held.
- 2026-11-22, builder: the iron chip text stays verbatim, so it reads "Iron x3.2-3.2 band" for a zero-width band.

## Open after this step

- The `HOT_SPOT_ABOVE` text was reached by unit tests only, not in the browser.
- The options graph and search were not run in the browser.
- The `reference` budget of 8155 s is 4 x `full`, not measured.
- srmcore 0.8.0 validation and R5e (gates V0, V2, V4, V5, demonstrations).

## Evidence

CI green 3/3 (fast on 3.12 and 3.14, web). Engine digest matches its pin. The browser check found one bug: a pre-R5d evaluation showed "no steady state" in the Rotor column. A missing value now reads "–" (test in `web/src/lib/thermal.test.ts`). The run report exported offline (5 MB, network blocked) with no page errors.
