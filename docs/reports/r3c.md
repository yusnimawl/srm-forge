# R3c: Cut-edge build factor

Merged 2026-10-20, PR #7. Versions after the merge: srmcore and srmapp 0.7.0, srmweb and `web/` 0.9.0 (srmsil stays 0.8.0).
Spec `docs/superpowers/specs/2026-10-20-r3c-cut-edge-design.md`. Plan `docs/superpowers/plans/2026-10-20-r3c-cut-edge.md`. Detailed results `docs/r3-loss-results.md`.

## Goal

Add the extra iron loss near cut edges, to test whether a missing build factor explains the Materu iron-loss gap of R3.

## What shipped

- `srmcore.post.cut_edge`: `CUT_PROCESSES` (wedm, punching, laser), `cut_edges`, `band_fraction` (share of each element within delta of a cut edge) and `edge_multiplier`. The factor multiplies hysteresis plus excess loss only.
- `srmapp.losses.stroke_losses(cut_process=...)` returns `cut_edge_rel` and a per-region `cut_edge_factor`.
- `Requirements.cut_process`, default `unspecified`: the nominal loss is unchanged and the spread over processes shows as a one-sided uncertainty row.
- Web input for the process. Source: Huynh et al. 2026, Results in Engineering 32, 112686.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Change in Materu iron loss, WEDM | -1 to -2 % | `screening`, T4.1 and T5.5 |
| Change in Materu iron loss, punching | +5 to +7 % | same |
| Change in Materu iron loss, laser | +8 to +10 % | same |
| Rows closed over the laser range | 3 of 10 (T4.1, T4.5, T5.3, already inside the uncertainty) | all 10 rows at `screening`, 2026-10-20 |
| 8/6 factors, punching and laser | 1.03 to 1.11 and 1.05 to 1.15 per region | 10JNEX900 |
| Fast suite | 1375 passed, vitest 264 | after merging main |

## Decisions

- 2026-10-20, owner: the factor changes iron loss only. B-H, maps and 2D-verified stay untouched.
- 2026-10-20, owner: the cutting process is undecided, so the default is `unspecified`.
- 2026-10-20, owner: Materu is a check only. Nothing is fitted to it.
- 2026-10-20, builder: adaptive sub-sampling for the band fraction (6 fixed samples per triangle made it depend on the mesh and it could drop to 0).

## Open after this step

- 7 of 10 Materu rows are not explained by cut edges. The M19 substitute for Materu's E140 steel and the subtracted measurement stay the main suspects.
- All process coefficients are grade C for 10JNEX900 (no 0.10 mm cut data).
- `full` was not run for this check (`screening` is within about 5 % of `full`).

## Evidence

Four tasks plus a final-review fix wave, subagent-driven. An Opus review approved the merge. Main (R3, R3b, R8a) was merged into the branch, and the only conflict was CLAUDE.md. Bench references re-checked at 0.7.0 and passed unchanged (bench tests 164 passed). 0.7.0 was not yet in `VALIDATED_VERSIONS` at merge. CI result: not recorded.
