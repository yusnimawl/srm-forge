# R3b: Run report

Merged 2026-10-20, PR #5. Versions after the merge: srmweb and `web/` 0.7.0 (srmcore and srmapp stay 0.6.0).
Spec `docs/superpowers/specs/2026-10-19-r3b-run-report-design.md`. Plan `docs/superpowers/plans/2026-10-19-r3b-run-report.md`. Detailed results: none.

## Goal

One click on an evaluated case gives one HTML file with the case's inputs, plots and findings. Done when it renders the same with the server stopped.

## What shipped

- Case Export menu item "Run report (HTML)". The file is built in the browser: Plotly, data and WebP animation frames inline, system fonts, a light print layout.
- `srmapp/report.py`: rule-based findings with levels `warn`, `note`, `ok` and `missing`, each citing its number. Route `GET /api/cases/{id}/report`.
- `web/src/report/` (template, player, collect, frames, export). Parts not run show as "Not run". The export never starts a job.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Offline export, screening 8/6 with losses and 12-frame animation | 5.9 MB | laptop, srmweb stopped, 2026-10-20 |
| Offline export, pre-0.6.0 DXF case | 5.0 MB | same |
| Network requests per page | 1 (itself) | same |
| Owner's Chrome PDF, first try | 20 pages, clipped plots | owner, 2026-10-20 |
| Headless Edge PDF after the fixes | 8 pages, nothing clipped | same day |
| Web tests | 241 passed | pre-merge |
| Fast suite | 1271 passed | pre-merge |

## Decisions

- 2026-10-19, owner: build the report in the browser as one offline file (no server rendering).
- 2026-10-19, owner: findings are computed in Python from rules (so each states its own number).
- 2026-10-20, builder: no forced page breaks, two plots per row, and plots relaid out to A4 widths for print (the first PDF had clipped plots).
- 2026-10-20, owner: keep SQLite (single-user tool, Postgres gives no gain).

## Open after this step

- Plot sizes assume A4.
- The report does not show the cut-edge range (an optional gap after R3c).
- The Thermal section came with R5d.

## Evidence

Five tasks, subagent-driven, all reviewed clean after fix rounds. Reviews caught invalid JSON from script escaping, a dark print layout, a 404 when a parent case was deleted and an outline drawn in light colours. Offline check on 2026-10-20: no console errors, the animation plays from WebP, no horizontal scroll at 375 px, and an HTML label is escaped. PR #5 merged right after PR #4. CI result: not recorded.
