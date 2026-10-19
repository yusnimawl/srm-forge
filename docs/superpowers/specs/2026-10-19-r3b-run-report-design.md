# R3b — Run report (design)

Date: 2026-10-19. Roadmap: `2026-10-12-roadmap-r1-r10-design.md` §3 R3b. Builds on R3 (branch `r3-iron-loss`, PR #4).

## 1. Goal

One self-contained HTML file per evaluated case, made with one click in the web app. It opens offline with the server stopped, can be copied or emailed, and reads like a detailed datasheet for the owner's own analysis. It includes a list of rule-based findings computed from the numbers. A print layout lets the static parts save as PDF from the browser.

Audience: the owner (personal project). Look: the app's Graphite dark theme on screen; a light print layout.

Done when: one click on an evaluated case gives the file, and it renders the same with the server stopped.

## 2. Decisions (owner, 2026-10-19)

- **Findings are rule-based** (no LLM, no physics advice): deterministic, offline, each finding cites its number.
- **Parts not yet computed are left out and marked** ("Not run"). Export never starts a job and never waits on one. The owner runs Evaluate, Validate, Losses and Animate first if they want a full report.
- **Built in the browser** (approach 1): the app already has the data and the field renderer. The findings are computed in Python, next to the physics.
- **One file, no separate assets**: Plotly, CSS, fonts, data, the outline SVG and the animation frames are all inline. The file makes no network request.
- **Storage stays SQLite** (asked and answered: a single-user tool, so Postgres adds setup with no gain).

## 3. Architecture

```
CasePage Export menu ── "Run report (HTML)" (evaluated cases only)
   │
   ├─ fetch: GET /api/cases/{id}            (case, evaluation, validation)
   │         GET /api/cases/{id}/losses     (404 → "Not run")
   │         GET /api/cases/{id}/compare    (DXF cases only)
   │         POST /api/geometry             (outline SVG)
   │         GET /api/cases/{id}/report     (findings, new)
   │         GET /api/cases/{id}/field/mesh + GET /api/jobs/{last animate}/frames  (410/none → "No animation")
   │
   ├─ render the animation frames offscreen with the existing field renderer (WebGL2, 2D canvas fallback) → WebP data URIs
   ├─ fill the template: inline CSS + Geist woff2, inline plotly.min.js, report data JSON, a small vanilla player script
   └─ download("<label or id>-report.html")
```

### 3.1 Server

- `src/srmapp/report.py` (new, pure functions, no I/O): `findings(inputs, evaluation, validation, losses, compare, has_animation) -> list[Finding]`. `Finding` is a frozen dataclass `{level, topic, text, value, unit}`; `level` is one of `warn`, `note`, `ok`, `missing`. The thresholds are named module constants.
- `GET /api/cases/{id}/report` in `src/srmweb/api.py` → `ReportOut {findings: list[FindingOut], versions: {srmcore, srmapp, srmweb}, generated: ISO time}`. 404 for an unknown case, 409 for a case without an evaluation. It reads the stored evaluation, validation, losses and compare data and whether the newest done animate job still has frames; it runs no solve.
- `srmweb` keeps its layering (no gmsh, ngsolve, netgen, skfem).

### 3.2 Browser

- `web/src/report/` (new):
  - `collect.ts`: fetches every part; an optional part that fails becomes `{missing: reason}` instead of failing the export.
  - `frames.ts`: renders each animation frame offscreen with the colour scale shared by all frames (`bMaxOfFrames`), the inferno map and the rotor at the frame angle, and encodes it as WebP (`canvas.toDataURL("image/webp", 0.85)`; PNG where WebP encoding is not supported).
  - `template.ts`: `buildReport(data) -> string`, a pure function. All user text (label, comment, case names) is HTML-escaped. Plot specs use the app's `plotTheme`, `LINE_COLORS` and `INFERNO_SCALE`.
  - `player.ts`: the inline player script source (play/pause, speed, scrubber, frame readout of ψ and torque), plain DOM, no React.
- `plotly.min.js` is loaded with a Vite `?raw` import inside a lazy chunk, so the app's main bundle does not grow.
- Progress shows in a toast ("Rendering frames 12/36", "Building the file"). Errors use `errorMessage`.

## 4. Report contents

Sections, top to bottom. Each optional section either has its content or a "Not run" box that says which button in the app makes it.

1. **Header**: case label and id, poles, preset, origin, export date, versions (srmcore, srmapp, srmweb), the status chips ("2D-verified · srmcore x" or "Unvalidated"; "Peak only · assumes j_limit N A/mm²").
2. **Findings**: the list from §5, grouped by level (warn, note, ok, missing), each with its topic.
3. **Inputs**: requirements, geometry, materials, winding, drive limits, in the app's units (mm, A, A/mm², rpm).
4. **Outline**: the SVG from `/api/geometry`.
5. **Key numbers and winding**: La, Lu, La/Lu, peak torque, ψ_max, I_max; turns, strands, paths, wire, resistance, copper mass; mass, torque ratio, power ratio, peak power, power density, efficiency at base speed.
6. **Map plots**: ψ(i) at all angles, T(θ) at all currents, inductance and saturation curves (as the Map and Design factors tabs).
7. **Performance and waveforms**: torque, power and efficiency against speed, turn-on and turn-off angles; phase current, voltage, torque and line current at base speed.
8. **Losses** (R3): a table per operating point (speed, torque, reached, power, copper DC and AC, iron per region and term, efficiency, iron uncertainty, beyond-fit flag), the efficiency map, the R3 notes.
9. **Validation**: the checks table (name, status, value, limit, detail) and the uncertainty budget.
10. **Before/after**: DXF cases only, the compare table.
11. **Flux animation**: the player and the B(θ) probe plot (stator pole, yoke, rotor pole), with the phase current the animation was run at.

Print layout (`@media print`): light colours, the player hidden and the first frame shown as a still, a page break before each section, plots kept static (Plotly renders them before print).

## 5. Findings rules

Each finding's `text` contains its number. A `warn` is only for hard facts; heuristic observations are `note`.

**warn**
- Torque ratio or power ratio below the resolved margin; the design is infeasible.
- j_rms above j_limit; mass above `max_mass_kg`.
- Losses: an operating point not reached; a point beyond the loss-fit range; iron uncertainty above `IRON_UNCERTAINTY_WARN` (0.30).
- Validation: each check with status `fail` or `warn` (by name); validated but no label.

**note**
- Margins: torque ratio, power ratio, mass as a fraction of its limit, outer diameter as a fraction of its limit.
- Saturation: La at I_max as a percentage of the unsaturated La; La/Lu.
- Torque ripple at base speed: the per-phase torque waveform summed over the phases shifted by the stroke (the same shift as `drive.envelope.line_current`), as (max − min) / mean.
- Efficiency at base speed; the loss split at the base-speed full-torque point into copper DC, copper AC and iron; the largest iron region and term.
- Validation budget: the largest row per quantity.
- DXF: the three largest relative changes in the compare table.

**ok**: one line for each warn rule that passes ("Torque requirement met, ×1.18").

**missing**: losses not run; not validated; no animation (none run, or its frames were cleared from the cache); losses made by an srmapp older than the evaluation.

A value that is NaN or None gives no finding (and no "nan" text).

## 6. Errors

- The button is enabled only for an evaluated case. An evaluation older than 0.6.0 still exports; its losses section says to re-evaluate before running Losses.
- Optional parts that fail to load (404 losses, 410 frames, a failed compare) become "Not run" or "Unavailable: <reason>". The export fails only when the case or the report route fails.
- No WebGL2: the 2D canvas renderer is used. If neither works, the animation section says so.

## 7. Testing

- pytest `tests/app/test_report.py`: each rule on small synthetic inputs (warn, note, ok, missing), the NaN rule, and the torque-ripple number on a hand-made waveform.
- pytest `tests/web/test_report_route.py`: 200 with findings, 404 unknown case, 409 unevaluated case, `missing` for cleared frames.
- vitest: `buildReport` output has no `http://` or `https://` in any `src`/`href`/`url(` and no `import`/`fetch` to a URL; every section is present or marked "Not run"; label and comment are escaped; the player script steps and wraps frames; `collect` turns a 404/410 into a missing part.
- Manual on the laptop: export a real case with all parts, stop the server, open the file offline, check desktop and 375 px, print preview to PDF. Keep solves small (the laptop is shared with a long run).
- `web/src/lib/noBlue.test.ts` covers the new files.

## 8. Versions and docs

- srmweb and `web/` 0.6.0 → 0.7.0. srmcore and srmapp stay 0.6.0 (no engine change; a srmcore bump would change map provenance and `VALIDATED_VERSIONS` handling). Regenerate `web/openapi.json` and `web/src/api/schema.ts`.
- CLAUDE.md: the report route, `srmapp/report.py` and `web/src/report/`. Roadmap: tick R3b once done. Living project doc: R3b section.

## 9. Out of scope

- LLM commentary or design advice.
- Running missing jobs from the export.
- A PDF of the animation; server-side rendering; batch export of many cases.
