# R3b Run Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One click on an evaluated case downloads one self-contained offline HTML report with rule-based findings.

**Architecture:** Findings are pure Python (`srmapp/report.py`) served by `GET /api/cases/{id}/report`. The browser collects every part (case, losses, compare, outline, animation frames), renders the animation frames to WebP with the existing field renderer, and fills a pure-TS template that inlines Plotly, CSS, data and a small vanilla player script.

**Tech Stack:** Python 3.12, FastAPI, pydantic; React 19, TypeScript, Vite, vitest (jsdom), plotly.js-dist-min, sonner.

**Spec:** `docs/superpowers/specs/2026-10-19-r3b-run-report-design.md`

## Global Constraints

- The report file makes no network request: no `http://` or `https://` in any `src`, `href` or CSS `url(`, no `fetch`/`import` of a URL. Fonts are the system stack (`ui-sans-serif, system-ui, sans-serif` and `ui-monospace, monospace`).
- Findings are rule-based only; each finding's `text` contains its number; a NaN or None value gives no finding and no "nan" text. Levels: `warn`, `note`, `ok`, `missing`. `warn` only for hard facts.
- Export never starts a job and never fails on an optional part (losses, validation, compare, outline, animation): that section shows "Not run" or "Unavailable: <reason>".
- srmweb and `web/` go 0.6.0 → 0.7.0. srmcore, srmapp and `pyproject.toml` stay 0.6.0.
- `srmcore` never imports `srmapp`; `srmweb` must not import gmsh, ngsolve, netgen or skfem (`tests/app/test_app_layering.py`).
- No blue colour literals or Tailwind blue/sky/indigo/cyan classes in `web/src` (`web/src/lib/noBlue.test.ts`). Colours from the Graphite tokens in `web/src/index.css`, `LINE_COLORS`, `INFERNO_SCALE`.
- Do not hand-edit `web/src/api/schema.ts`; regenerate it.
- Comments describe the code as it is; no task history in comments.
- The laptop is busy: run focused tests only (`python -m pytest <file>`, `npx vitest run <file>`); the full fast suite runs once before the PR, not per task. No `reference` solves.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. User text with HTML or `</script>` (case label, comment, material names) must not break or inject into the report → escaped in HTML, and every inline `<script>` body has `</script` and `<!--` neutralised (Task 3 test `escapes user text and script terminators`).
2. Plotly's own source contains `</script>`-like strings → inlined source must be escaped the same way (Task 3 test with a fake Plotly source containing `"</script>"`).
3. Evaluations stored before 0.6.0 (no `srmapp_version`, no waveforms, no `j_limit`) still produce a report → findings skip missing values (Task 1 test `old evaluation without optional fields`).
4. A case whose newest animate job had its frames cleared, while an older one is intact → the route picks the newest job with all frames cached; none → `missing` finding with reason (Task 2 test).
5. Infinite or zero denominators (mean torque 0, `la_unsat` 0, a limit of None) → no finding, no exception (Task 1 test `degenerate values give no finding`).

---

### Task 1: Findings rules (`srmapp/report.py`)

**Files:**
- Create: `src/srmapp/report.py`
- Test: `tests/app/test_report.py`

**Interfaces:**
- Produces:
  ```python
  Level = Literal["warn", "note", "ok", "missing"]

  @dataclass(frozen=True)
  class Finding:
      id: str            # stable rule id, e.g. "torque_ratio", "check:held_out"
      level: Level
      topic: str         # "requirements", "current density", "mass", "size", "saturation", "ripple", "efficiency",
                         # "losses", "validation", "budget", "dxf", "data"
      text: str
      value: float | None = None
      unit: str = ""

  def findings(inputs: CaseInputs, evaluation: Mapping, validation: Mapping | None, losses: Mapping | None,
               compare: Sequence[Mapping] | None, animation_missing: str | None) -> list[Finding]
  def torque_ripple(torque: np.ndarray, n_phases: int) -> float | None
  IRON_UNCERTAINTY_WARN = 0.30
  ```
  `evaluation`, `validation` and `losses` are the stored JSON dicts (same keys as `EvaluationOut`, `ValidationOut`, `LossesOut`); `compare` is the list of `CompareRowOut` dicts (`name`, `unit`, `before`, `after`) or None; `animation_missing` is None when an animation is available, else the reason text.
- Consumes: `srmapp.case.CaseInputs` (`.requirements`, `.design.machine`, `.search_settings().resolved_margin`), `srmapp.drive.envelope.line_current(per_phase, n_phases)`.

Rules (in this order in the output; skip any whose inputs are missing, None, NaN or non-finite):

| id | level | rule |
|---|---|---|
| `feasible` | warn if `evaluation["feasible"]` is false, else ok | |
| `torque_ratio`, `power_ratio` | warn if ratio < resolved margin, else ok; value = ratio, text "×1.18 (margin ×1.05)" | |
| `j_rms` | warn if `j_rms > j_limit`, else ok; value in A/mm² (stored A/m²) | |
| `mass` | warn if `mass_kg > max_mass_kg`, else note with % of limit | skip when no limit |
| `outer_diameter` | note: 2·`stator_outer_radius` / `max_outer_diameter_m` in % | skip when no limit |
| `saturation` | note: `curves["la_sat"][-1] / curves["la_unsat"]` in % ("La at I_max is 46 % of unsaturated La") | |
| `la_lu` | note: `key["la_lu"]` | |
| `ripple` | note: `torque_ripple(envelope.waveforms.torque[base], machine.n_phases)` in % | base = argmin \|speeds − base_speed\| |
| `efficiency_base` | note: `efficiency_base` in % | |
| `loss_split` | note at the rated point (highest speed index whose top-torque point is reached; points are `points[i*nt + j]`): copper DC, copper AC, iron as % of the sum; value = iron % | |
| `iron_region` | note: the (region, term) with the largest W at the rated point | |
| `losses_unreached` | warn with the count of points not reached, else ok | |
| `beyond_fit` | warn with the count of `beyond_fit_range` points, else ok | |
| `iron_uncertainty` | warn if max `iron_uncertainty_rel` > `IRON_UNCERTAINTY_WARN`, else note; value in % | |
| `check:<name>` | warn for each check with status `fail` or `warn` (text includes value, limit, detail) | |
| `checks` | ok "all N checks pass" when no check is fail/warn | |
| `label` | warn when validation exists and `label` is None | |
| `budget:<quantity>` | note per key of `budget["total"]`: the row with the largest `rel[quantity]`, value in % | |
| `dxf` | note per row of the three largest \|after/before − 1\| (before ≠ 0) | |
| `losses_missing`, `validation_missing`, `animation_missing` | missing | when the part is None |
| `losses_stale` | missing when `losses["srmapp_version"]` < `evaluation["srmapp_version"]` (compare as int tuples of major.minor.patch; unparsable → skip) | |

`torque_ripple`: `total = line_current(torque, n_phases)`; return `(total.max() − total.min()) / total.mean()`, or None when the mean is not > 0 or any value is non-finite.

- [ ] **Step 1: Write the failing tests** in `tests/app/test_report.py`. Build `inputs` from `conftest.make_8_6()` and `tests/web_support.py` `REQ` (plus `max_mass_kg`, `max_outer_diameter_m` where a test needs them); build `evaluation` as `to_json(web_support.evaluation("c1"))` (`srmweb.serialize`/the store's JSON form) and edit keys per test. Tests:
  - `test_torque_ratio_below_margin_warns`: torque_ratio 0.9 → finding `torque_ratio` level warn, value 0.9, `"0.9"` in text.
  - `test_requirements_met_give_ok`: ratios 1.2, feasible → `torque_ratio`, `power_ratio`, `feasible` all ok.
  - `test_j_rms_above_limit_warns`: j_rms 7e6, j_limit 6e6 → warn, value 7.0, unit "A/mm²".
  - `test_mass_limit`: mass 12, limit 10 → warn; mass 8, limit 10 → note value 80.
  - `test_torque_ripple_hand_made`: `torque_ripple(np.array([2.0, 0, 0, 0]), 4) == 0.0` (total constant 2); `torque_ripple(np.array([2.0, 0, 0, 0, 0, 0, 0, 0]), 2) == pytest.approx(4.0)` (total `[2,0,0,0,2,0,0,0]`, (2−0)/0.5); `torque_ripple(np.zeros(8), 2) is None`.
  - `test_losses_rules`: a losses dict with 2 speeds × 2 torques, one point unreached, one `beyond_fit_range`, max uncertainty 0.4 → `losses_unreached` warn value 1, `beyond_fit` warn value 1, `iron_uncertainty` warn value 40; `loss_split` uses the rated point (speed index 1 if its top-torque point is reached, else 0).
  - `test_validation_rules`: one check `fail`, one `pass`, label None → `check:<name>` warn, `label` warn, no `checks` ok; all pass with label → `checks` ok, no `label`.
  - `test_budget_largest_row`: two rows, `rel={"peak_torque": 0.02}` and `{"peak_torque": 0.06}` → `budget:peak_torque` note value 6, text names the second row's `source`.
  - `test_dxf_top_three`: five compare rows → exactly three `dxf` findings, largest first; a row with before 0 or None skipped.
  - `test_missing_parts`: losses, validation None, `animation_missing="frames cleared"` → three missing findings, the animation text contains "frames cleared".
  - `test_losses_stale`: losses version "0.5.9", evaluation "0.6.0" → `losses_stale` missing.
  - `test_old_evaluation_without_optional_fields`: delete `srmapp_version`, `j_limit`, `envelope["waveforms"]`, `curves` → no exception, no `ripple`, `saturation` or `j_rms` finding.
  - `test_degenerate_values_give_no_finding`: `la_unsat` 0, torque waveform all zeros, efficiency NaN → none of `saturation`, `ripple`, `efficiency_base`; no finding text contains "nan" or "inf" (case-insensitive).

- [ ] **Step 2: Run** `python -m pytest tests/app/test_report.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement** `src/srmapp/report.py` per the table. Number formatting: ratios `×{:.2f}`, percentages `{:.0f} %` (one decimal below 10 %), A/mm² `{:.2f}`.
- [ ] **Step 4: Run** `python -m pytest tests/app/test_report.py tests/app/test_app_layering.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(app): rule-based report findings`.

---

### Task 2: Report route, version bump, schema

**Files:**
- Modify: `src/srmweb/api.py` (new route; extract helpers from `compare` and `job_frames`)
- Modify: `src/srmweb/results.py` (`FindingOut`, `ReportOut`)
- Modify: `src/srmweb/__init__.py` (`0.7.0`), `web/package.json` and `web/package-lock.json` top-level version (`0.7.0`)
- Regenerate: `web/openapi.json`, `web/src/api/schema.ts`
- Test: `tests/web/test_report_route.py`

**Interfaces:**
- Consumes: Task 1 `findings(...)`, `Finding`.
- Produces:
  ```python
  class FindingOut(_Out): id: str; level: Literal["warn","note","ok","missing"]; topic: str; text: str; value: F = None; unit: str = ""
  class ReportOut(_Out):
      findings: list[FindingOut]
      versions: dict[str, str]          # {"srmcore", "srmapp", "srmweb"}
      generated: str                    # ISO 8601 UTC
      animation_job_id: str | None      # the newest done animate job of the case whose frames are all cached
      animation_current_a: F = None     # its phase current
  ```
  `GET /api/cases/{case_id}/report` → `ReportOut`; 404 unknown case; 409 `"the case has no evaluation"` when there is no stored evaluation.
  Helpers in `api.py`: `compare_rows(case: dict) -> list[dict] | None` (the body of `compare` after the parent lookup; None when `parent_case_id` is None; the `compare` route uses it) and `frames_cached(job: dict) -> bool` (the cached-frame lookup of `job_frames`; `job_frames` uses it for its 410).
  Animation choice: walk `store.case_jobs(case_id)` newest first, kind `animate`, status `done`, result not cancelled; the first with `frames_cached` wins. `animation_missing` = None when found, `"no animation run"` when no done animate job exists, `"the frames were cleared from the cache; animate again"` otherwise.
  `inputs` for `findings` = `CaseInputs.model_validate(case["inputs"])`; losses from `store.case_result(id, "losses")` (None when absent or cancelled); validation from `store.case_result(id, "validate")`.

- [ ] **Step 1: Write failing tests** in `tests/web/test_report_route.py` using `tests/web/test_web_animate.py`'s client setup (`Settings(..., tmp_path/"nostatic")`, `JobRunner(store, st, quick=QuickLane(spawn=False))`) and `web_support.store_search` + `evaluation("c1")` to make an evaluated case (as `test_losses_job.py` `_case`):
  - `test_report_unknown_case_404`.
  - `test_report_draft_without_evaluation_409`: a case created from a reference (`{"origin": "reference", ...}`) never evaluated → 409.
  - `test_report_findings_and_versions`: 200; `versions == {"srmcore": srmcore.__version__, "srmapp": srmapp.__version__, "srmweb": "0.7.0"}`; findings include `losses_missing`, `validation_missing`, `animation_missing` with text "no animation run"; `animation_job_id` is None.
  - `test_report_picks_newest_cached_animation`: monkeypatch `srmapp.field.cached_frame` (as `test_web_animate.py` `fake`) so frames of the newer job return None and the older job's return a frame; insert two done animate jobs with results (`store.create_job`, `put_result(job_id, {...angles...}, kind="animate")`, `set_status`) → `animation_job_id` = the older id, `animation_current_a` = its `current_a`, no `animation_missing`.
  - `test_report_frames_cleared_reason`: all frames None → `animation_missing` text contains "cleared".
  - `test_compare_route_unchanged`: existing compare tests still pass (run `tests/web/test_web_dxf.py` or the file holding the compare tests — find it with `grep -rl "/compare" tests/web`).
- [ ] **Step 2: Run** `python -m pytest tests/web/test_report_route.py -q` → FAIL.
- [ ] **Step 3: Implement** the models, helpers, route; bump the versions.
- [ ] **Step 4: Regenerate** `python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`.
- [ ] **Step 5: Run** `python -m pytest tests/web/test_report_route.py tests/web/test_web_api.py tests/app/test_app_layering.py <the compare test file> -q` → PASS.
- [ ] **Step 6: Commit** `feat(web): report findings route; srmweb 0.7.0`.

---

### Task 3: Report template and player (pure TS)

**Files:**
- Create: `web/src/report/template.ts`, `web/src/report/player.ts`, `web/src/report/types.ts`
- Modify: `web/src/components/PlotlyPlot.tsx` (export the pieces below; `LinePlot` keeps its behaviour)
- Test: `web/src/report/template.test.ts`, `web/src/report/player.test.ts`

**Interfaces:**
- Produces (`types.ts`):
  ```ts
  export type Part<T> = { ok: true; value: T } | { ok: false; reason: string }
  export type Finding = components["schemas"]["FindingOut"]
  export type Report = components["schemas"]["ReportOut"]
  export type ReportFrame = { src: string; angle: number; currentA: number; psi: number; torque: number; status: string }
  export type ReportAnimation = { frames: ReportFrame[]; probes: Trace[]; currentA: number; bMax: number }
  export interface ReportData {
    caseOut: Case                        // GET /api/cases/{id}
    report: Report
    outline: Part<string>                // SVG text
    losses: Part<LossesResult>
    compare: Part<CompareOut> | null     // null when the case has no parent
    animation: Part<ReportAnimation>
  }
  ```
  `template.ts`: `export function buildReport(data: ReportData, plotlySource: string): string` and `export const escapeHtml = (s: string) => string` and `export const scriptSafe = (s: string) => string` (replaces `</script` with `<\/script` case-insensitively and `<!--` with `<\!--`).
  `player.ts`: `export const PLAYER_SOURCE: string` (the inline script text) and `export function stepFrame(index: number, count: number, delta: number): number` (wraps both ways; `PLAYER_SOURCE` embeds the same logic via `stepFrame.toString()`).
  `PlotlyPlot.tsx` exports: `toPlotData(traces: Trace[]): Data[]` (the Trace→Plotly mapping `LinePlot` uses) and `lineLayout(theme: Partial<Layout>, xTitle: string, yTitle: string, y2Title?: string, legend?: boolean): Partial<Layout>`.
- Consumes: trace builders in `web/src/lib/` — `psiCurves`, `torqueGrid` (`mapCurves.ts`), `torqueCurves`, `inductanceCurves`, `performanceSeries`, `designFactorTraces` (`analysis.ts`), `waveformSeries`, `defaultSpeedIndex` (`waveforms.ts`), `contourData`, `splitBars`, `lossKeyNumbers`, `ratedPoint`, `pointLabel` (`losses.ts`), `compareRows` (`compare.ts`), `verifiedChip`, `jLimitChip`, `madeWithText` (`chips.ts`), `fmt`, `fmtSI` (`format.ts`), `INFERNO_SCALE` (`inferno.ts`), `plotTheme` (`PlotlyPlot.tsx`) called with the Graphite token values read from `web/src/index.css` (define them once as a constant in `template.ts`).

Document layout (spec §4, sections in this order, each `<section id="...">` with an `<h2>`): `header`, `findings`, `inputs`, `outline`, `key-numbers`, `map`, `performance`, `losses`, `validation`, `before-after` (only when `compare` is not null), `animation`. A missing part renders `<div class="not-run">Not run — <what to press in the app></div>` (losses: "run Losses on the Losses tab"; validation: "press Validate (needs the full preset)"; animation: "press Animate stroke on the Field tab"; plus the reason) or `Unavailable: <reason>` for a failed fetch. A pre-0.6.0 evaluation's losses section says "re-evaluate the case, then run Losses".
Plots: one `<div class="plot" id="p<N>">` per figure; all figures go in one `<script type="application/json" id="figures">` (`[{id, data, layout}]`, `scriptSafe(JSON.stringify(...))`); the player script calls `Plotly.newPlot(id, data, layout, {displaylogo: false, responsive: true})` for each, and before `window.print` nothing extra is needed.
Animation: `<img id="anim-frame">` showing `frames[0].src`, controls (Play/Pause button, speed select `0.5×/1×/2×` from `SPEEDS`, range scrubber, readout "Frame k of n at I A", ψ in mWb, torque N·m), frame meta in `<script type="application/json" id="frames">`; the B(θ) probe plot is one more figure.
CSS: Graphite dark on screen; `@media print` light background, dark text, `.controls {display:none}`, `section {break-before: page}` except the first, plots `break-inside: avoid`. 375 px: single column, tables scroll inside their own `overflow-x:auto` box.
Order of the inline scripts at the end of `<body>`: Plotly source, figures JSON, frames JSON, player.

- [ ] **Step 1: Write failing tests** in `template.test.ts` with a small hand-made `ReportData` fixture (`fixture()` in the test file; reuse the vitest data helpers that `web/src/lib/analysis.test.ts` and `losses.test.ts` use for an `Evaluation` and `LossesResult` if they export any, else build minimal objects) and `plotlySource = "/*plotly*/ var x = '</script>';"`:
  - `has no network loads`: output has no match for `/(src|href)\s*=\s*["']?\s*(https?:)?\/\//i` and no `url\(\s*["']?(https?:)?\/\//i`, and no `fetch(`.
  - `escapes user text and script terminators`: case label `<img src=x onerror=alert(1)></script>` → output contains `&lt;img` and does not contain `<img src=x`; the fake Plotly `'</script>'` appears only as `<\/script`; exactly as many `</script>` as `<script` tags.
  - `every section present`: all ids above present (`before-after` only with compare); with losses, validation and animation `{ok:false, reason:"r"}` each of those sections contains `Not run` and `r`.
  - `findings grouped by level`: four findings, one per level → they appear in order warn, note, ok, missing, each with its text.
  - `header stamps versions`: srmcore, srmapp, srmweb versions and the verified/unvalidated chip text appear.
  - `old evaluation losses text`: evaluation `srmapp_version: null` and losses missing → losses section contains "re-evaluate".
  - `figures json parses`: extract the `#figures` script content, `JSON.parse` succeeds, every `id` has a matching `<div id>`.
  `player.test.ts`: `stepFrame(35, 36, 1) === 0`, `stepFrame(0, 36, -1) === 35`, `stepFrame(3, 36, 1) === 4`; `PLAYER_SOURCE` contains no `import`, `fetch` or `http`.
- [ ] **Step 2: Run** `cd web; npx vitest run src/report` → FAIL.
- [ ] **Step 3: Implement** `types.ts`, `player.ts`, `template.ts`, and the two `PlotlyPlot.tsx` exports (refactor `LinePlot` to use them).
- [ ] **Step 4: Run** `cd web; npx vitest run src/report src/components src/lib/noBlue.test.ts` → PASS; `npx tsc -b` → no errors.
- [ ] **Step 5: Commit** `feat(web): self-contained run report template and player`.

---

### Task 4: Collect, frame rendering, Export button

**Files:**
- Create: `web/src/report/collect.ts`, `web/src/report/frames.ts`, `web/src/report/export.ts`
- Modify: `web/src/components/case/CaseActions.tsx` (Export menu item)
- Modify: `web/src/vite-env.d.ts` or `tsconfig` types only if `?raw` needs `vite/client` (check first)
- Test: `web/src/report/collect.test.ts`, `web/src/components/case/CaseActions.test.tsx` (create if absent)

**Interfaces:**
- Consumes: Task 2 route (`ReportOut` incl. `animation_job_id`, `animation_current_a`), Task 3 `ReportData`, `Part`, `ReportAnimation`, `buildReport`.
- Produces:
  ```ts
  // collect.ts
  export async function collect(caseId: string, onStep: (msg: string) => void,
                                renderFrames: (mesh: FieldMeshData, frames: FieldFrameData[], onFrame: (k: number, n: number) => void) => Promise<string[]>
                               ): Promise<ReportData>
  // frames.ts
  export async function renderFrames(mesh: FieldMeshData, frames: FieldFrameData[], onFrame: (k: number, n: number) => void,
                                     size?: number /* 640 */): Promise<string[]>   // data URIs
  // export.ts
  export async function exportReport(caseId: string, fileStem: string, onStep: (msg: string) => void): Promise<void>
  ```
  `collect`: `api<Case>("/api/cases/{id}")` and `api<Report>("/api/cases/{id}/report")` are required (errors propagate). Optional parts each become `Part` (`{ok:false, reason: errorMessage(e)}` on error): losses via `GET /api/cases/{id}/losses` (404 → reason "not run"); compare only when `caseOut.parent_case_id` is set; outline via `POST /api/geometry` with `caseOut.inputs.design.machine` returning SVG text (use `fetch` with `credentials: "same-origin"` like `apiBlob`, or `apiBlob(...).text()` if it supports POST — check `client.ts`); animation only when `report.animation_job_id` is set: fetch mesh (`GET /api/cases/{id}/field/mesh` → `meshFromWire`) and frames (`GET /api/jobs/{job}/frames` → `framesFromWire`), `bMax = bMaxOfFrames(mesh, frames)`, `probes = probeSeries(frames, mesh.nRotorPoles)`, `src`s from `renderFrames`; when `animation_job_id` is null → `{ok:false, reason: <the report's animation_missing finding text>}`.
  `renderFrames`: one detached `<canvas width=size height=size>`; `createGlRenderer(canvas)`, else a fresh canvas with `getContext("2d")` and `draw2d`; per frame `buildScene(mesh, frame, {bmap:true, flux:false, mesh:false, outlines:true}, bMax)`, `viewMatrix(boundsOf(mesh.nodes), size, size, 1, [0, 0])`, draw, `canvas.toDataURL("image/webp", 0.85)`; if the result does not start with `data:image/webp` use `toDataURL("image/png")`; throws `Error("no canvas renderer")` when neither context exists (collect turns it into a missing part). `dispose()` the GL renderer at the end.
  `export.ts`: `const plotly = (await import("plotly.js-dist-min/plotly.min.js?raw")).default`; `download(\`${fileStem}-report.html\`, new Blob([buildReport(await collect(...), plotly)], {type: "text/html;charset=utf-8"}))`.
  `CaseActions.tsx`: menu item `Run report (HTML)` after "Geometry (DXF)", disabled unless `data.evaluation` is set; on click `const { exportReport } = await import("@/report/export")` (lazy chunk), a sonner `toast.loading` whose text follows `onStep` ("Collecting the results", "Rendering frames k/n", "Building the file"), `toast.success("Report saved")` or the existing `report(e)` error path.

- [ ] **Step 1: Write failing tests**:
  `collect.test.ts` (mock `global.fetch` with a URL→response table; pass a fake `renderFrames` returning `["data:image/png;base64,AA"]` per frame):
  - `required parts propagate errors`: report route 409 → `collect` rejects.
  - `missing losses becomes a part`: losses 404 → `losses.ok === false`, reason contains "not run"; the rest ok.
  - `frames cleared becomes a part`: frames 410 → `animation.ok === false`.
  - `no animation job skips frame fetch`: `animation_job_id: null` → no request to `/frames`, reason is the `animation_missing` finding text.
  - `compare only for child cases`: `parent_case_id: null` → `compare === null` and no `/compare` request.
  `CaseActions.test.tsx`:
  - `run report disabled without evaluation` and `enabled with evaluation` (render inside the providers the existing component tests use — copy the setup from `web/src/components/case/ValidationPanel.test.tsx`).
- [ ] **Step 2: Run** `cd web; npx vitest run src/report/collect.test.ts src/components/case/CaseActions.test.tsx` → FAIL.
- [ ] **Step 3: Implement** `collect.ts`, `frames.ts`, `export.ts`, the menu item.
- [ ] **Step 4: Run** `cd web; npx vitest run src/report src/components/case src/lib/noBlue.test.ts` → PASS; `npm run build` → succeeds, and the main entry chunk does not contain plotly's raw source (the `?raw` import is only in the lazy `export` chunk: check `web/dist/assets/index-*.js` size is within 5 % of the previous build).
- [ ] **Step 5: Commit** `feat(web): Run report export with offline animation frames`.

---

### Task 5: Docs and the offline check

**Files:**
- Modify: `CLAUDE.md` (Web layer: the report route, `srmapp/report.py`, `web/src/report/`; current state: R3b), `docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md` (tick R3b boxes once the check passes)

- [ ] **Step 1:** Update `CLAUDE.md` and the roadmap.
- [ ] **Step 2 (coordinator, on the laptop):** start `srmweb` on a copy of the smoke database, export a case with evaluation, validation, losses and an animation and one DXF case; stop the server; open both files from disk; check desktop and 375 px, play the animation, print preview to PDF. Record the file size.
- [ ] **Step 3: Commit** `docs: R3b run report`.
