# R5c: Ratings replace j_limit

Merged 2026-11-19, PR #34. Versions after the merge: srmcore and srmapp 0.8.0, srmweb and `web/` 0.11.0.
Spec `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md`. Plan `docs/superpowers/plans/2026-11-18-r5c-ratings-in-search.md`. Detailed results `docs/r5-thermal-results.md`.

## Goal

A winding is feasible when it holds the continuous and peak requirements under the rated thermal model. Every evaluation carries its rating and the search ranks on rated kW/kg.

## What shipped

- `srmapp.thermal` rating core: `thermal_context`, `check_requirement`, `rate_context`.
- `turns.choose_turns` returns `TurnsChoice.ranked`, the EM-feasible windings best-first.
- `evaluate_stage2(thermal=True)` checks up to `MAX_THERMAL_CHECKS` (4) windings against the rated hot-spot limit and rates the first that holds (`Evaluation.rating`).
- The Pareto front is over rated continuous and peak kW/kg.
- `j_limit` becomes a wide RMS screen, `J_SCREEN` 40 A/mm². `j_peak_max` defaults to `J_PEAK_SCREEN`, 80 A/mm².
- Web: evaluate steps strokes and thermal, `EvaluationOut.rating`, thermal flags on search and evaluate requests.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Rated evaluation of the 8/6 screening case | 629 s | LattePanda i5-1340P |
| Same evaluation before R5c | about 1 min | same |
| Wire-mode map range without the peak screen | 88 A to 355 A (four times wider) | 8/6 |
| Rating numbers against R5b | unchanged | `docs/r5-thermal-results.md` |

## Decisions

- 2026-11-18, owner: approved the plan. `j_limit` stays only as a wide screen.
- 2026-11-18, builder: `J_PEAK_SCREEN` is 80 A/mm² because an uncapped default left about ten current points in the working range.
- 2026-11-19, builder: at most 4 thermal checks per design, and only the chosen winding gets the full rating (cost).
- 2026-11-19, builder: a runaway in a later check now fails the design (the final review found it could leave a winding marked feasible).

## Open after this step

- srmcore 0.8.0 is not in `VALIDATED_VERSIONS` (campaign, tracker row 10q).
- The evaluate estimate did not count rating time. R5d closed this.
- Gates V0, V2, V4, V5 and the Kiyota 18/12 V6 wait for R5e.

## Evidence

CI green 3/3 (Linux 3.12 and 3.14, web). Built subagent-driven in six reviewed tasks, then a whole-branch review and one fix wave. Fast suite count: not recorded.
