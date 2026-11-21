# R5d Thermal tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every rated design's thermal rating in the web app (Thermal tab, chips, run report, options-graph
axes) so the owner sees what limits a design and where margin can be won, and count the rating in the evaluate
estimate.

**Architecture:** srmapp keeps the rating's temperature fields through a callback sink and adds a thermal summary
(verdict, binds, labels, hints) and an active volume; srmweb stores the full rating in the evaluation JSON, writes
the fields as one npz per rated evaluation under `<cache_dir>/thermal/`, serves them with the `frames` wire format
and times the rating for the estimate; `web/` renders the tab, the map (reusing the field renderer), the chips, the
report section and the new axes. srmcore does not change.

**Tech Stack:** Python 3.12+, numpy, FastAPI, SQLite; React 19, TypeScript, Plotly, WebGL2 (2D canvas fallback),
vitest.

**Spec:** `docs/superpowers/specs/2026-11-21-r5d-thermal-tab-design.md` (parent:
`docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md` §5, §11).

## Global Constraints

- srmcore unchanged: no edit under `src/srmcore/`, no `ENGINE_REVISION` bump, `python tools/engine_digest.py` passes.
- Rating numbers unchanged: every field of `Rating` equal before and after for the same context.
- Versions: srmapp 0.9.0 (`src/srmapp/__init__.py`); srmweb 0.12.0 (`src/srmweb/__init__.py`, `web/package.json`,
  `web/package-lock.json`, `tests/web/test_report_route.py`); srmcore stays 0.8.0 (`pyproject.toml` untouched).
- Layering (`tests/app/test_app_layering.py`): srmapp never imports srmweb; srmweb never imports gmsh, ngsolve,
  netgen, skfem.
- Web theme: dark only, no blue (`web/src/lib/noBlue.test.ts`), temperature colour map inferno, Plotly through
  `plotTheme`.
- kW/L volume = π/4 × `stator_outer_diameter`² × (`stack_length` + 2 × overhang), overhang =
  `maps.end_winding.coil_geometry(machine).build + machine.slot_liner_thickness`; litres in the UI.
- Chip texts verbatim: "Rated · class {insulation_class} {limit_c:.0f} °C", "Not thermally rated",
  "Cooling: {kind} (placeholder)" (no suffix when not a placeholder), "Iron ×{lo:g}–{hi:g} band".
- Map messages verbatim: "Edit, then Evaluate, for full detail", "Re-evaluate to see the map" (cache cleared),
  "hot spot: end winding (lumped, not in this section)".
- Comments describe the code as it is, never task or plan history (CLAUDE.md Conventions).
- Regenerate `web/src/api/schema.ts` after any API model change:
  `python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`.

## Review Focus

1. A rated evaluation stored before R5d (summary-only `rating`, no `thermal_check`, no `thermal_fields`) opened in
   the tab and in the run report: the table shows, verdict/map/tornado/rotor/cooling say "Edit, then Evaluate, for
   full detail"; no crash. Test in Task 6 (`ThermalTab.test.tsx: renders a pre-R5d summary`) and Task 9.
2. Cache cleared after the evaluation: `GET /api/cases/{id}/thermal/fields` returns 410 and the map panel says
   "Re-evaluate to see the map" while the rest renders. Tests in Task 4 and Task 7.
3. A rated speed with no steady state or rated continuous 0 (`HotSpot(nan, "none")`, NaN temperatures, note "no
   steady state…"): JSON nulls, the row shows "0" and the note text, the verdict still forms. Tests in Task 3 and
   Task 6.
4. A budget share stored as `BIG_K` (runaway): the summary marks it `runaway: true`, the tornado draws it as a
   labelled "runaway" bar off-scale. Tests in Task 3 and Task 6.
5. The same design hash in two searches with different requirements: two distinct npz files, each case shows its
   own map. Test in Task 4.

---

### Task 1: Rating keeps its temperature fields

**Files:**
- Create: `src/srmapp/thermal_fields.py`
- Modify: `src/srmapp/thermal.py` (`rate_speed`, `rate_context`)
- Test: `tests/app/test_thermal_fields.py`; extend `tests/app/test_thermal_rating_core.py`; extend
  `tests/app/test_thermal_check.py` (slow)

**Interfaces:**
- Produces, in `srmapp.thermal_fields`:
  - `KINDS = ("stator_iron", "rotor_iron", "shaft", "coil", "liner", "air")`
  - `@dataclass(frozen=True) class ThermalFields: nodes: np.ndarray (n, 2) float32 m; triangles: np.ndarray (m, 3)
    int32; kind: np.ndarray (m,) uint8 (index into KINDS); rpm: np.ndarray (s,) float64; steady: np.ndarray (s, n)
    float32 °C, rated set at the rated continuous torque; peak: np.ndarray (s, n) float32 °C, end of peak (NaN row
    when there is no peak state); end_winding_steady_c: np.ndarray (s,); end_winding_peak_c: np.ndarray (s,)` (max
    over the end-winding lumps; NaN when unknown)
  - `write_fields(path: Path, f: ThermalFields) -> None` (writes `path.with_suffix(".tmp.npz")` then renames)
  - `read_fields(path: Path) -> ThermalFields`
- Produces, in `srmapp.thermal`:
  - `rate_speed(..., keep: list | None = None)`: when given, appends `(t_c, t_p)` (`Temperatures | None` each) once,
    for the states behind the returned `SpeedRating`.
  - `rate_context(ctx, *, em_budget=None, n_speeds=6, progress=None,
    fields_out: Callable[[ThermalFields], None] | None = None) -> Rating`: when given, calls `fields_out` once with
    the rated set's fields (nominal set not kept).

- [ ] **Step 1: Write failing tests**
  - `test_thermal_fields.py::test_round_trip(tmp_path)`: a 4-node, 2-triangle `ThermalFields` with 2 speeds, one
    peak row all NaN → `read_fields(write_fields(...))` equal arrays (`np.testing.assert_array_equal`, NaN equal),
    dtypes float32/int32/uint8 kept, and no `*.tmp.npz` left in `tmp_path`.
  - `test_thermal_rating_core.py::test_keep_returns_the_states`: using the module's existing synthetic solver setup,
    `rate_speed(..., keep=k)` returns a `SpeedRating` equal to the call without `keep`, and `len(k) == 1`,
    `k[0][0] is not None`; for the envelope-within-limit case `k[0][1] is None`.
  - `test_thermal_check.py::test_fields_out_leaves_the_rating_unchanged(tmp_path)` (`@pytest.mark.slow`, same 8/6
    setup as `test_check_matches_rating_8_6`): `rate_context(ctx)` equals `rate_context(ctx, fields_out=got.append)`
    (`dataclasses.asdict` compare, NaN-aware), `len(got) == 1`, `got[0].steady.shape == (len(speeds),
    len(ctx.domain.nodes))`, `got[0].kind.max() < len(KINDS)`.
- [ ] **Step 2: Run** `python -m pytest tests/app/test_thermal_fields.py tests/app/test_thermal_rating_core.py -q`
  → FAIL (module missing, `keep` unknown).
- [ ] **Step 3: Implement** `thermal_fields.py` and the two parameters. `kind` maps `ctx.domain.element_kind`
  strings to KINDS indices. End-winding values: max of `t.lumps[name]` over `ctx.network.end_lumps.values()` (read
  the attribute names on `ThermalContext` first; use what it exposes). The peak state is the `t_p` that
  `result(...)` receives.
- [ ] **Step 4: Run** the three tests (the slow one with `-m slow` or by node id) → PASS; then
  `python -m pytest tests/app -m "not slow" -q` → PASS.
- [ ] **Step 5: Commit** `R5d: the rating keeps its temperature fields`.

### Task 2: Evaluation keeps the check, rates failing cases, gets kW/L

**Files:**
- Modify: `src/srmapp/evaluate.py` (`Evaluation`, `evaluate_stage2`), `src/srmapp/case.py` (`evaluate_design`),
  `src/srmapp/pipeline.py` (`run_search`), `src/srmapp/sizing/estimates.py`, `src/srmapp/__init__.py` (0.9.0)
- Test: extend `tests/app/test_app_evaluate.py`, `tests/app/test_app_case_evaluate.py`; new
  `tests/app/test_app_volume.py`

**Interfaces:**
- Consumes: Task 1 `ThermalFields`, `rate_context(..., fields_out=)`.
- Produces:
  - `Evaluation` new fields (all defaulted, appended after `srmcore_version`): `thermal_check: RequirementCheck |
    None = None` (the chosen winding's check when one holds, else the first failing check), `active_volume_l: float
    = nan`, `rated_continuous_kw_per_l: float = nan`, `rated_peak_kw_per_l: float = nan`.
  - `evaluate_stage2(..., rate_failed: bool = False, fields_out: Callable[[ThermalFields], None] | None = None)`:
    with `rate_failed`, when no checked winding holds, rate `checks[0]` (rebuild its context if the loop moved on),
    keep `feasible = False`, store the rating and the kW/kg and kW/L; `fields_out` is passed to every
    `rate_context` call.
  - `evaluate_design(..., fields_out=None)` passes `rate_failed=True` and `fields_out`.
  - `run_search(..., on_fields: Callable[[str, ThermalFields], None] | None = None)`: calls
    `on_fields(candidate.id, fields)`; `rate_failed` stays False.
  - `estimates.active_volume(p: RadialSRMParams) -> float` (m³), per the Global Constraints formula.
  - kW/L = the same lowest-power-over-base..max rule as `_rated_kw_per_kg`, divided by litres.
  - `SearchResult.pareto()` unchanged: it already keeps feasible designs only; a test pins that a rated infeasible
    evaluation stays out.

- [ ] **Step 1: Write failing tests**
  - `test_app_volume.py::test_volume_of_the_8_6`: `active_volume(make_8_6().machine)` equals
    `math.pi / 4 * od**2 * (stack + 2 * (coil_geometry(m).build + m.slot_liner_thickness))` to 1e-12 and is larger
    than `math.pi / 4 * od**2 * stack`.
  - `test_app_evaluate.py::test_failing_case_is_rated_when_asked` (monkeypatch `thermal.check_requirement` to return
    a failing `RequirementCheck(False, 6000.0, (), (), ("6000 rpm: HOT_SPOT_ABOVE",), "HOT_SPOT_ABOVE")` and
    `thermal.rate_context` to return a stub `Rating`, as the existing R5c evaluate tests stub them): with
    `rate_failed=True` → `feasible is False`, `rating` is the stub, `thermal_check.reason == "HOT_SPOT_ABOVE"`,
    `rated_continuous_kw_per_l` finite; with `rate_failed=False` → `rating is None`, `thermal_check` set.
  - `test_app_evaluate.py::test_fields_reach_the_sink`: the stubbed `rate_context` calls its `fields_out`; the sink
    receives exactly one object.
  - `test_app_evaluate.py::test_rated_infeasible_stays_off_the_front`: a `SearchResult` with one rated infeasible
    and one rated feasible evaluation → `pareto()` holds only the feasible one.
- [ ] **Step 2: Run** `python -m pytest tests/app/test_app_volume.py tests/app/test_app_evaluate.py -q` → FAIL.
- [ ] **Step 3: Implement** as in Interfaces; bump srmapp to 0.9.0.
- [ ] **Step 4: Run** `python -m pytest tests/app -m "not slow" -q` → PASS.
- [ ] **Step 5: Commit** `R5d: evaluations keep the thermal check, rate failing cases, and carry kW/L`.

### Task 3: Thermal summary in srmapp

**Files:**
- Create: `src/srmapp/thermal_summary.py`
- Test: `tests/app/test_thermal_summary.py`

**Interfaces:**
- Consumes: `Rating`, `SpeedRating`, `RequirementCheck`, `required_torques`, `rating_speeds`, `K_IRON_HI`.
- Produces (pure functions, no solves):
  - `BINDS_HEAT = "heat"`, `BINDS_EM = "EM"`; `binds(s: SpeedRating, which: str) -> str` (`which` is
    `"continuous"` or `"peak"`; EM when the torque ≥ `s.envelope_nm` − `_TORQUE_TOL`, else heat).
  - `ROW_LABELS: dict[str, str]` for every name in `srmapp.cooling.ROWS` (plain words: "Liner conductivity",
    "Contact gap", "Iron loss band", "Cooling h", "Winding conductivity", "Lamination conductivity", "Air-gap h",
    "EM torque uncertainty", "Mechanical loss band", "Thermal mesh", "End-winding model", …; every row present, a
    test checks the keys equal `ROWS`).
  - `HINTS: dict[str, str]` one sentence per row a design or a measurement can change; `hint(row: str) -> str | None`.
  - `location_text(location: str) -> str`: `"end_<coil>"` → "end winding, <coil>", a coil region name → "slot
    winding, <coil>", `"none"` → "no steady state".
  - `@dataclass(frozen=True) class Verdict: holds: bool | None; rpm: float | None; margin_pct: float | None;
    which: str | None; binds: str | None; hot_spot_c: float | None; hot_spot_at: str | None; reason: str | None;
    text: str`. `holds` None when there is no check.
  - `verdict(rating: Rating | None, check: RequirementCheck | None, req: Requirements) -> Verdict`: holds from the
    check; with a rating, the smallest margin (rated / required − 1, continuous and peak, over the rated speeds,
    continuous skipped when not required) with its speed and binds; failing: the check's speed, reason and hot spot
    at the required torque. `text` examples (tests pin these forms): "✓ Meets the requirement · smallest margin
    +4 % at 6000 r/min (continuous, binds heat)" and "✗ Short at 6000 r/min: hot spot above the limit
    (159 °C of 160 °C)" / "✗ Short at 6000 r/min: no stroke reaches the required torque".
  - `shares_at(rating: Rating, rpm: float) -> list[dict]`: rows at that speed, zero-width rows (`thermal_mesh`,
    `end_winding_model`) left out, sorted by K descending, each `{"row", "label", "k", "runaway": k >= BIG_K}`.
  - `iron_band(rating: Rating) -> tuple[float, float]`: (`K_IRON_HI[0][1]`, `K_IRON_HI[-1][1]`).
  - `summary(rating: Rating | None, check: RequirementCheck | None, req: Requirements) -> dict`: JSON-ready
    `{"verdict": asdict(Verdict), "speeds": [{"rpm", "need_continuous_nm", "need_peak_nm", "binds_continuous",
    "binds_peak", "hot_spot_text", "headroom_k"}], "least_margin_rpm", "iron_band": [lo, hi]}`; `headroom_k` = limit
    − hot spot at speeds where continuous binds EM, else None.

- [ ] **Step 1: Write failing tests** (synthetic `SpeedRating`/`Rating` as built in `tests/web/test_web_results.py`
  `sr(...)`): `test_binds_em_at_envelope`, `test_binds_heat_below_envelope`, `test_labels_cover_rows`,
  `test_location_text` (three cases above), `test_verdict_holds_smallest_margin`,
  `test_verdict_failing_hot_spot`, `test_verdict_failing_no_stroke`, `test_verdict_no_check_is_none`,
  `test_no_continuous_requirement_skips_continuous`, `test_shares_sorted_and_runaway` (a `BIG_K` share →
  `runaway is True`, zero-width rows absent), `test_nan_speed_is_null_safe` (a speed with `HotSpot(nan, "none")` and
  continuous 0: `summary` gives "no steady state" and `json.dumps(to_json(...))` succeeds).
- [ ] **Step 2: Run** `python -m pytest tests/app/test_thermal_summary.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the test file → PASS.
- [ ] **Step 5: Commit** `R5d: thermal summary (verdict, binds, labels, hints)`.

### Task 4: srmweb stores the full rating and serves the fields

**Files:**
- Create: `src/srmweb/thermal_files.py`
- Modify: `src/srmweb/serialize.py` (`rating_summary` → `rating_json`, `evaluation_json`), `src/srmweb/results.py`
  (`SpeedRatingOut`, `RatingOut`, new `BudgetShareOut`, `GapOut`, `StressOut`, `CoolingOut`, `ThermalCheckOut`,
  `ThermalSummaryOut`; `EvaluationOut`), `src/srmweb/jobs.py` (`run_evaluate_job`, `run_search_job`),
  `src/srmweb/api.py` (route, `cache_files`)
- Test: `tests/web/test_web_thermal.py`; extend `tests/web/test_web_results.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `thermal_files.THERMAL_DIR = "thermal"`; `fields_key(job_id: str, evaluation_id: str) -> str` (filesystem-safe
    `f"{job_id}_{evaluation_id}"`); `write(cache_dir: Path, key: str, f: ThermalFields) -> None`;
    `path(cache_dir: Path, key: str) -> Path`.
  - `serialize.rating_json(r: Rating) -> dict`: every field of spec §9 (per speed nominal and rated with
    `envelope_nm`, temperatures, `start_nm`, `note`; `shares`, `gap` (the four cases plus `air_gap_m`), `stress`
    (`status`, `safety_factor`, `governing`, `speed_limit_rpm`, `check_speed_rpm`, `note`; read the `RotorStress`
    field names first), `torque_factor`, `limit_c`, `insulation_class`, `cooling` (`kind`, `placeholder`, and the
    setup fields the cooling line shows; `kind` = the enabled options joined by " + ", e.g. "jacket" or "jacket + end
    spray"), `notes`, `srmapp_version`), NaN → null via `to_json`.
  - `evaluation_json(ev, *, waveforms=True, fields_key: str | None = None)` adds `"thermal_check"`,
    `"thermal_summary"` (`thermal_summary.summary`), `"thermal_fields"` (the key or None), and the kW/L fields.
  - `RatingOut` keeps its R5c fields and gains the new ones, every new field optional (`= None` / `= []`) so a
    pre-R5d body validates.
  - `GET /api/cases/{case_id}/thermal/fields` → `application/octet-stream` `frames.pack(meta, arrays)`:
    meta `{"rpm": [...], "end_winding_steady_c": [...], "end_winding_peak_c": [...], "kinds": KINDS}`, arrays
    `nodes`, `triangles`, `kind`, `steady`, `peak`. 404 when the case has no evaluation or no `thermal_fields` key;
    410 when the key's file is missing.
  - Jobs: the evaluate job writes the sink's fields under `fields_key(job_id, ev.id)`; the search job writes one per
    rated candidate via `on_fields` under `fields_key(job_id, candidate_id)` and puts each key on its evaluation's
    JSON. Read how `run_job` reaches the job id (add it to the call if the runner does not pass it yet).
  - `cache_files()` includes `thermal/*.npz`; cache size and clear count and delete them.

- [ ] **Step 1: Write failing tests** in `test_web_thermal.py` (use the store/client fixtures the other
  `tests/web` files use; build a synthetic rated `Evaluation` with a small `ThermalFields`):
  - `test_rating_json_round_trips_through_rating_out`: `RatingOut.model_validate(rating_json(r))` succeeds and
    keeps shares, gap, stress, cooling.
  - `test_pre_r5d_rating_still_loads`: the R5c `rating_summary` dict shape validates as `RatingOut`.
  - `test_fields_route_serves_pack`: attach an evaluation whose key file exists → 200, header meta `rpm` equals the
    speeds, `steady` shape `(s, n)`.
  - `test_fields_route_410_after_clear`: same, delete the file → 410.
  - `test_fields_route_404_unrated`: no key → 404.
  - `test_cache_counts_thermal`: a file in `thermal/` raises `GET /api/settings/cache` `files` by one; `DELETE`
    removes it.
  - `test_same_design_two_searches_two_files`: `fields_key("jobA", "abc123")` ≠ `fields_key("jobB", "abc123")`,
    both written, both readable.
- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_thermal.py -q` → FAIL.
- [ ] **Step 3: Implement**; regenerate `web/openapi.json` and `web/src/api/schema.ts`.
- [ ] **Step 4: Run** `python -m pytest tests/web -m "not slow" -q` → PASS.
- [ ] **Step 5: Commit** `R5d: store the full rating and serve the temperature fields`.

### Task 5: Evaluate estimate counts the rating

**Files:**
- Modify: `src/srmweb/store.py` (schema v3), `src/srmweb/jobs.py` (`run_evaluate_job`), `src/srmweb/cases.py`
  (`estimate`, `RATING_BUDGET_S`), `src/srmweb/__init__.py` (0.12.0), `web/package.json`, `web/package-lock.json`,
  `tests/web/test_report_route.py` (version)
- Test: extend `tests/web/test_job_steps.py`, the store and estimate tests in `tests/web/`

**Interfaces:**
- Produces:
  - `SCHEMA_VERSION = 3`; table `rating_times (preset TEXT NOT NULL, seconds REAL NOT NULL, finished TEXT NOT NULL)`
    with index `rating_times_preset`; a v2 file migrates by creating only that table and index (v0 and v1 paths
    unchanged); `Store.add_rating_time(preset: str, seconds: float)`, `Store.recent_rating_times(preset: str,
    n: int = 5) -> list[float]`.
  - The evaluate job records the span from the first `on_thermal` call to the end when a rating was made
    (`ev.rating is not None`).
  - `cases.RATING_BUDGET_S: dict[str, float]` per preset (`screening`, `full`, `reference`); `estimate` adds the
    rating part when the request rates (`thermal` true; read how the estimate route learns it and add the parameter
    if missing) and the basis text gains "longer if the design fails the thermal check".
  - Initial `RATING_BUDGET_S` values: screening 600, full 2400, reference 9600 (s); Task 10 replaces the screening
    and full values with LattePanda measurements × 1.25.

- [ ] **Step 1: Write failing tests**: `test_v2_store_migrates_to_v3` (create a v2 file with the R5c schema,
  open `Store` → `PRAGMA user_version` 3, existing rows kept, `recent_rating_times("screening") == []`);
  `test_rating_time_recorded` (in `test_job_steps.py`, extend the R5c `rated` timing test: the rating span lands in
  `rating_times`, the scan span is unchanged); `test_estimate_adds_rating` (history present → mean added;
  absent → budget; `thermal=False` → not added).
- [ ] **Step 2: Run** those tests → FAIL.
- [ ] **Step 3: Implement**; bump srmweb and `web/` to 0.12.0.
- [ ] **Step 4: Run** `python -m pytest tests/web -m "not slow" -q` → PASS.
- [ ] **Step 5: Commit** `R5d: the evaluate estimate counts the rating; srmweb 0.12.0`.

### Task 6: Thermal tab (without the map)

**Files:**
- Create: `web/src/components/analysis/ThermalTab.tsx`, `web/src/lib/thermal.ts`,
  `web/src/components/analysis/ThermalTab.test.tsx`, `web/src/lib/thermal.test.ts`
- Modify: `web/src/components/analysis/AnalysisTabs.tsx` (tab "Thermal" after "Losses", shown when
  `evaluation.status === "ok"`; lazy like `LossesTab`)

**Interfaces:**
- Consumes: `Evaluation` from `@/api/types` with `rating`, `thermal_check`, `thermal_summary`, `thermal_fields`.
- Produces: `ThermalTab({ evaluation, caseId }: { evaluation: Evaluation; caseId?: string })`;
  `thermal.ts`: `tabState(ev: Evaluation): "unrated" | "summary-only" | "check-only" | "full"` (unrated: no rating
  and no check; summary-only: rating without `shares`; check-only: check without rating; full), `curveSpec(rating,
  summary)` (Plotly traces: continuous and peak, rated lines, nominal→rated band as `fill: "tonexty"`, requirement
  dashed), `tornadoSpec(shares)` (horizontal bars, runaway bars capped at the largest finite value × 1.2 with text
  "runaway").
- Layout per spec §5.2–§5.4: verdict line (`thermal_summary.verdict.text`), table (Speed, Need cont/peak, Cont,
  Peak, Binds cont/peak, Hot spot, Rotor; headroom shown in the hot-spot cell when present), curves, a map slot
  (filled in Task 7), tornado at the selected speed with the top row's hint under it, rotor line (SF, check speed,
  speed limit, status words when not `ok`, gap closure for the four cases against `air_gap_m` and against 0.3 mm),
  cooling line, notes collapsed. At `max-width: 640px` the table shows Speed, Cont, Peak, Binds; tapping a row
  expands need, hot spot, headroom, rotor.

- [ ] **Step 1: Write failing tests** (vitest + Testing Library, as `LossesTab.test.tsx`): `tabState` for the four
  shapes; `renders a full rating` (verdict text, one row per speed, "heat"/"EM" cells, tornado present);
  `renders a pre-R5d summary` (table present, "Edit, then Evaluate, for full detail" shown, no tornado);
  `renders check-only` (✗ verdict, failing speed, "Make a case and Evaluate for the full rating");
  `renders unrated` (the evaluation's note, nothing else); `nan speed row` (null temperatures → "no steady state",
  no crash); `runaway share labelled`.
- [ ] **Step 2: Run** `cd web; npx vitest run src/components/analysis/ThermalTab.test.tsx src/lib/thermal.test.ts`
  → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web; npx vitest run; npm run build` → PASS, build clean.
- [ ] **Step 5: Commit** `R5d: Thermal tab`.

### Task 7: Temperature map

**Files:**
- Create: `web/src/components/analysis/ThermalMap.tsx`, `web/src/lib/thermalWire.ts`,
  `web/src/lib/thermalWire.test.ts`
- Modify: `web/src/lib/fieldGl.ts` (add a scalar scene), `web/src/components/analysis/ThermalTab.tsx` (map slot)

**Interfaces:**
- Consumes: Task 4 route; `fieldWire.ts` unpack helper (read its name); `Scene`, `createGlRenderer`, `draw2d`,
  `canRender`, `viewMatrix`, `OUTLINE`.
- Produces:
  - `thermalWire.ts`: `type ThermalFieldsData = { rpm: number[]; kinds: string[]; nodes: Float32Array; triangles:
    Uint32Array; kind: Uint8Array; steady: Float32Array[]; peak: Float32Array[]; endWindingSteadyC: (number |
    null)[]; endWindingPeakC: (number | null)[] }`; `decodeThermalFields(buf: ArrayBuffer): ThermalFieldsData`;
    `fetchThermalFields(caseId: string): Promise<ThermalFieldsData | "gone">` (410 → "gone").
  - `fieldGl.ts`: `buildScalarScene(xy: Float32Array, tris: Uint32Array, region: Uint8Array, values: Float32Array
    (per node), lo: number, hi: number): Scene` (per-vertex inferno colours, region outlines, `bMax` = hi).
  - `ThermalMap({ caseId, rpm, state, hotSpotAt, endWindingC, onSpeeds }: { caseId: string; rpm: number; state:
    "steady" | "peak"; hotSpotAt: string; endWindingC: number | null; onSpeeds?: (rpm: number[]) => void })` with a
    °C colour bar (`ColorBar` takes `bMax`; pass the scale explicitly, add a `unit` prop if needed), one scale over
    both states of the selected speed, NaN nodes drawn in the background colour.
  - Speed picker (defaults to `thermal_summary.least_margin_rpm`) and steady / peak-end toggle live in `ThermalTab`
    and also drive the tornado's speed.
- [ ] **Step 1: Write failing tests**: `decodeThermalFields` on a buffer built with the same layout as
  `frames.pack` (reuse the helper `fieldWire.test.ts` uses) → arrays and shapes; `buildScalarScene` colours the
  hottest node with inferno(1) and the coolest with inferno(0); `ThermalTab` with the route mocked to 410 shows
  "Re-evaluate to see the map" and still renders the table; an end-winding hot spot shows
  "hot spot: end winding (lumped, not in this section)".
- [ ] **Step 2: Run** `cd web; npx vitest run src/lib/thermalWire.test.ts src/components/analysis` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web; npx vitest run; npm run build` → PASS.
- [ ] **Step 5: Commit** `R5d: temperature map`.

### Task 8: Chips, options-graph axes and table columns

**Files:**
- Modify: `web/src/lib/chips.ts`, `web/src/components/StatusChips.tsx`, `web/src/lib/candidates.ts` (`AXES`,
  `CandidateRow`), `web/src/components/run/ParetoPlot.tsx` (defaults), `web/src/components/run/CandidateTable.tsx`,
  `web/src/components/cases/CaseTable.tsx`
- Test: `web/src/lib/chips.test.ts` (create or extend), `web/src/lib/candidates.test.ts` (create or extend)

**Interfaces:**
- Produces: `thermalChips(ev: Evaluation): { text: string; tone: ChipTone }[]` (texts per Global Constraints;
  unrated → `[jLimitChip(ev.j_limit), {text: "Not thermally rated", tone: "warn"}]`; rated → the three rated chips);
  `StatusChips` uses it in place of the lone `jLimitChip`. `AXES` gains `rated_continuous_kw_per_kg: "Rated
  continuous (kW/kg)"`, `rated_peak_kw_per_kg: "Rated peak (kW/kg)"`, `rated_continuous_kw_per_l: "Rated continuous
  (kW/L)"`, `rated_peak_kw_per_l: "Rated peak (kW/L)"`; defaults x = rated peak kW/kg, y = rated continuous kW/kg;
  rows without a value on a chosen axis are left out and the legend says "n unrated not shown".
- [ ] **Step 1: Write failing tests**: chip texts for rated, placeholder and non-placeholder cooling, unrated,
  pre-R5d (no `cooling` → no cooling chip); `AXES` keys present and row values mapped from the evaluation fields;
  the unrated count.
- [ ] **Step 2: Run** `cd web; npx vitest run src/lib` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web; npx vitest run; npm run build` → PASS.
- [ ] **Step 5: Commit** `R5d: thermal chips and rated axes`.

### Task 9: Run report Thermal section

**Files:**
- Modify: `web/src/report/types.ts`, `web/src/report/collect.ts`, `web/src/report/template.ts`,
  `web/src/report/frames.ts` (offscreen render of one temperature map)
- Test: extend the report tests in `web/src/report/` (read their names; add beside them)

**Interfaces:**
- Consumes: Tasks 6–7 (`thermal.ts` specs, `decodeThermalFields`, `buildScalarScene`).
- Produces: `ReportData.thermal: { evaluation fields needed; mapPng: string | null; mapGone: boolean } | null`;
  `template.ts` section id `thermal`, title "Thermal": verdict, full table, curves (Plotly, static), the map at
  `least_margin_rpm` steady (image), uncertainties as an HTML table (row label, K), rotor and gap, cooling, notes;
  "Not run" when unrated; the §5.4 texts for summary-only, check-only and a gone map. The export never starts a job.
- [ ] **Step 1: Write failing tests**: `buildReport` with a full thermal block contains the section, the verdict
  text and a `<table>` of uncertainties; with `thermal: null` it says "Not run"; summary-only shows "Edit, then
  Evaluate, for full detail"; `mapGone` shows "Re-evaluate to see the map".
- [ ] **Step 2: Run** `cd web; npx vitest run src/report` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web; npx vitest run; npm run build` → PASS.
- [ ] **Step 5: Commit** `R5d: Thermal section in the run report`.

### Task 10: Measure, check in the browser, record

**Files:**
- Modify: `src/srmweb/cases.py` (`RATING_BUDGET_S` measured values), `docs/r5-thermal-results.md` (R5d section),
  `CLAUDE.md` (Web layer and R5 lines: Thermal tab, routes, schema v3, versions)
- Create: `examples/rating_timing.py`

**Interfaces:**
- `examples/rating_timing.py [--preset screening|full] [--cache-dir DIR] [--json PATH]`: runs `evaluate_design` on
  the 8/6 reference case (`srmapp.references`) with `thermal=True`, timestamps the first `thermal_progress` call and
  the return, prints and writes `{"preset", "rating_s", "srmapp"}`.

- [ ] **Step 1: Measure** on the LattePanda: `python examples/rating_timing.py --preset screening --json
  docs/validation/r5d_rating_screening.json` and the same with `full`; set `RATING_BUDGET_S` screening and full to
  measured × 1.25 (reference stays 4 × full); run `python -m pytest tests/web -m "not slow" -q` → PASS.
- [ ] **Step 2: Browser check** (`srmweb`, `web` built): a rated 8/6 case, a failing case (requirements raised until
  the check fails), a pre-R5d evaluated case and a case after clearing the cache; desktop and 375 px; the run report
  exported and opened offline. Record what was checked in `docs/r5-thermal-results.md`.
- [ ] **Step 3: Full fast suite** `python -m pytest -m "not slow" -q` and `cd web; npx vitest run; npm run build` →
  PASS; `python tools/engine_digest.py` → matches its pin.
- [ ] **Step 4: Docs**: R5d section in `docs/r5-thermal-results.md` (what shipped, the budgets, the browser
  check); CLAUDE.md lines updated.
- [ ] **Step 5: Commit** `R5d: rating budgets measured, docs`; open the PR with
  `superpowers:finishing-a-development-branch`; after merge with CI green, update the Notion project doc (milestone
  row) and the tracker (R5d row 10j and the estimate row Done, Roadmap R5d Done with date and PR).
