# R5c: Ratings Replace j_limit in the Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A winding is feasible when it holds the continuous and peak requirements under the rated (unfavourable) thermal model; every evaluation carries its `Rating`; the search ranks on rated continuous and peak kW/kg; versions bump.

**Architecture:** `srmapp.thermal` gains a rating core that works from (requirements, reference-turns design, end-corrected map, winding), used by the existing `rate(inputs, evaluation)` and by stage 2. `choose_turns` keeps its cheap EM scan (with `j_limit` demoted to a wide RMS screen) and returns the EM-feasible windings best-first. `evaluate_stage2` checks them best-first against the requirement at each rated speed, stops at the first that holds, and rates only that one in full.

**Tech Stack:** Python 3.12+, numpy, the existing srmcore/srmapp/srmweb stack. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md` §1 item 6, §4.1, §5, §11.

## Global Constraints

- Feasibility (§5): "rated continuous ≥ requirement and rated peak ≥ requirement. Same tie rule as today (wire mode lowest resistance, density mode most equivalent turns). Windings are rated best-first and the scan stops at the first feasible one."
- Required torque at a speed (§4.1): continuous `continuous_power_w / ω`, ω = max(rpm, base) (None: no continuous check, and the result says so); peak `peak_torque_nm` at or below base, `peak_power_w / ω` above.
- `j_peak_max`: "user cap only, default none. The peak rating replaces it."
- `j_limit`: a wide screen, labelled "screen". Value `J_SCREEN = 2 * J_LIMIT` (40 A/mm²), applied as the envelope RMS limit in the EM pass of the scan (stage 1 has no RMS estimate; deviation from §5's "Stage 1 filter" row, stated in the docs). Its false-drop rate is tracker item 11.
- Versions (§11): srmcore 0.7.0 → 0.8.0, srmapp 0.7.0 → 0.8.0, srmweb and `web/` 0.10.0 → 0.11.0. srmcore 0.8.0 is NOT added to `VALIDATED_VERSIONS`.
- Rankings use rated values only (§10, R7). No fitted constants; no comment carries task history (CLAUDE.md).
- Speeds rated: the base speed plus linspace(max/n, max, n), n = `n_speeds` (default 6), as `rate` does today.

## Review Focus

1. **No winding holds the thermal limit.** Expect status "ok", `feasible` False, the best EM winding reported unrated with the note "no winding holds the rated hot-spot limit", never an exception. Test in Task 3.
2. **Material without loss or thermal data** (a case on M19 or steel_1010). Expect an unrated evaluation (`rating` None) with the refusal text as a note, and `feasible` from the EM check only, labelled unrated. Test in Task 3.
3. **`continuous_power_w` None.** Expect only the peak check, and a note saying no continuous check ran. Test in Task 1 (`required_torques`) and Task 3.
4. **Cancel during the thermal checks.** Expect status "cancelled", as the map and scan do today. Test in Task 3.
5. **Slow-suite web search tests** (`tests/web`, wait 5400 s). With ratings, a real search job rates every shortlisted design. Expect the tests to keep their wait by running with `thermal=False` in `SearchSettings`, the only place that flag is public. Covered in Task 4.

---

### Task 1: Rating core and the requirement check (`srmapp/thermal.py`)

**Files:**
- Modify: `src/srmapp/thermal.py`
- Test: `tests/app/test_thermal_check.py` (new; fast tests plus one `@pytest.mark.slow`)

**Interfaces:**
- Produces:
  - `required_torques(req: Requirements, rpm: float) -> tuple[float | None, float]` (continuous or None, peak), N·m.
  - `rating_speeds(req: Requirements, n_speeds: int = 6) -> list[float]` (the current `speeds` expression, moved).
  - `@dataclass(frozen=True) class RequirementCheck: holds: bool; rpm: float | None` (first failing speed, None when it holds); `continuous_hot_c: tuple[float, ...]`; `peak_hot_c: tuple[float, ...]`; `notes: tuple[str, ...]`.
  - `class ThermalContext` built by `thermal_context(req, ref_design, result_ref, w, *, solver, workers, cache_dir, cancel, progress)` where `result_ref` is the reference-turns map WITH the end winding (as stage 2 holds it). It owns what `rate` builds today before the speed loop: hot winding, mesh, domain, coefficient/network cache, rescaled map, envelope, stroke cache, `load_at`, `solver_for`. Raises `MissingLossData`, `MissingCoolingData`, `ValueError` before any solve, as `rate` does.
  - `check_requirement(ctx: ThermalContext, n_speeds: int = 6) -> RequirementCheck`: the rated set (every row in `ROWS`) only; speeds in ascending order; at each speed the steady hot spot at the required continuous torque (skip when None) and the hot spot over a `peak_duration_s` transient at the required peak torque starting from that steady state (from zero load when continuous is None); stops at the first speed where either exceeds `limit_c`, or where no stroke reaches the torque (that counts as failing).
  - `rate_context(ctx: ThermalContext, *, em_budget=None, n_speeds=6, progress=None) -> Rating`: today's `rate` body from the speed loop on.
  - `rate(inputs, evaluation, ...)` keeps its signature and result: builds the map as today, then `rate_context(thermal_context(...))`.

- [ ] **Step 1: Write the failing fast tests**

```python
def test_required_torques_follow_the_requirements():
    req = Requirements(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                       continuous_power_w=15_000.0)
    w_base = 3000 * 2 * math.pi / 60
    assert required_torques(req, 1000.0) == pytest.approx((15_000 / w_base, 95.5))
    w9 = 9000 * 2 * math.pi / 60
    assert required_torques(req, 9000.0) == pytest.approx((15_000 / w9, 30_000 / w9))

def test_no_continuous_requirement_gives_none():
    req = Requirements(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    assert required_torques(req, 6000.0)[0] is None

def test_rating_speeds_hold_base_and_max():
    req = Requirements(peak_power_w=1.0, peak_torque_nm=1.0, base_speed_rpm=2000.0, max_speed_rpm=6000.0)
    s = rating_speeds(req, 6)
    assert s[0] == 1000.0 and 2000.0 in s and s[-1] == 6000.0 and s == sorted(s)
```

- [ ] **Step 2: Run them; expect ImportError** — `PYTHONPATH=src:tests python -m pytest tests/app/test_thermal_check.py -q`

- [ ] **Step 3: Implement** `required_torques`, `rating_speeds`, `RequirementCheck`, `ThermalContext`, `thermal_context`, `check_requirement`, `rate_context`, and `rate` as a wrapper. Move code, do not duplicate it: `rate_speed` stays the bisection; the steady/transient pieces `check_requirement` needs are the ones `rate_speed` already uses (factor them out if `rate_speed` inlines them).

- [ ] **Step 4: Slow test `test_check_matches_rating_8_6`** (reuse the `case`/`rating` fixture pattern of `tests/app/test_thermal_rate.py`, 8/6 screening): with `continuous_power_w` set to 0.9 × the rated continuous power at base speed of a full `rate`, `check_requirement(...).holds` is True; at 1.1 × it is False and `rpm` is a rated speed.

- [ ] **Step 5: Run** the new tests, then `tests/app/test_thermal_rate.py tests/app/test_thermal_rating_core.py` including slow (`-m ""`): all pass, `rate` numbers unchanged.

- [ ] **Step 6: Commit** `R5c: rating core, required torques and the requirement check`

### Task 2: EM scan returns windings best-first; `j_limit` becomes a screen (`srmapp/turns.py`, `sizing/estimates.py`, `sizing/stage1.py`)

**Files:**
- Modify: `src/srmapp/turns.py`, `src/srmapp/sizing/estimates.py`, `src/srmapp/sizing/stage1.py`
- Test: `tests/app/test_app_turns.py`, `tests/app/test_app_scan_equality.py` (must stay green unchanged except argument names)

**Interfaces:**
- Produces:
  - `J_SCREEN = 2 * J_LIMIT` in `sizing/estimates.py` (comment: wide RMS screen; tracker 11 measures its false drops).
  - `choose_turns(..., j_limit: float = J_SCREEN, j_peak_max: float | None = None, ...)`: `j_peak_max` None means no peak-density cap (`math.inf`) in wire mode.
  - `TurnsChoice.ranked: tuple[ScanPoint, ...]` — the EM-feasible points in best-first order: wire mode by (resistance, turns, paths) ascending, density mode by (turns/paths descending, paths ascending). `point` stays `ranked[0]` when any, else today's best-worst fallback.
  - `stage1(..., j_peak_max: float = math.inf)` and `Stage1.j_peak_max` default `math.inf`; `max_mmf` must accept `math.inf` (wire mode: the phase current times the most turns that fit).

- [ ] **Step 1: Failing tests** in `test_app_turns.py`: `test_ranked_is_best_first_wire` (ranked resistances non-decreasing, `point is ranked[0]`), `test_ranked_is_best_first_density` (turns/paths non-increasing), `test_default_peak_cap_is_none` (wire mode with the default `j_peak_max` scans as many windings as `wire_windings(..., math.inf)` gives and `capped` is False), `test_stage1_default_cap_is_inf` (`Stage1.j_peak_max == math.inf`, `i_map` finite).
- [ ] **Step 2: Run; expect failures.**
- [ ] **Step 3: Implement.** `test_app_scan_equality.py` passes `j_limit`/`j_peak_max` explicitly where it compares with the frozen old code, so its numbers stay bit-identical.
- [ ] **Step 4: Run** `tests/app -m "not slow" -q`; fix callers that relied on `2 * J_LIMIT` (`SearchSettings.peak_cap`, `case.py`) by passing None through.
- [ ] **Step 5: Commit** `R5c: EM scan ranks windings best-first; j_limit is a screen, j_peak_max a user cap`

### Task 3: Stage 2 rates best-first (`srmapp/evaluate.py`)

**Files:**
- Modify: `src/srmapp/evaluate.py`, `src/srmapp/case.py`
- Test: `tests/app/test_app_evaluate.py`, `tests/app/test_app_case_evaluate.py`, new slow `tests/app/test_app_rated_choice.py`

**Interfaces:**
- Consumes: Task 1 `thermal_context`, `check_requirement`, `rate_context`; Task 2 `TurnsChoice.ranked`.
- Produces on `Evaluation` (all defaulted, so stored evaluations still load): `rating: Rating | None = None`, `rated_continuous_kw_per_kg: float = NaN` (lowest rated continuous power over base..max speed / mass), `rated_peak_kw_per_kg: float = NaN` (same for rated peak), `srmcore_version: str = srmcore.__version__`.
- `evaluate_stage2(..., thermal: bool = True, n_speeds: int = 6, thermal_progress: Callable[[str, int, int], None] | None = None)`. `evaluate_design` passes them through.

Behaviour: after the scan, when `thermal` and `ranked` is non-empty: for each ranked point in order, `check_requirement`; the first that holds is chosen and gets `rate_context` → `rating`, `feasible` = True (mass limit still applies). None holds: choose `ranked[0]`, `rating` None, `feasible` False, note "no winding holds the rated hot-spot limit". A refusal (`MissingLossData`, `MissingCoolingData`, `ValueError`) from `thermal_context`: chosen as today from the EM scan, `rating` None, note = the refusal text plus "not thermally rated", `feasible` = EM result. `cancel` during checks: status "cancelled". `thermal=False`: today's behaviour plus `rating` None and the note "not thermally rated". `thermal_progress(step, done, total)` reports "strokes" and "thermal" as `rate` does, and "windings" (rated windings checked).

- [ ] **Step 1: Failing fast tests** (mocked `build_map` as the existing tests do, `thermal=False`): `test_unrated_evaluation_says_so` (rating None, "not thermally rated" in error, srmcore_version set). Mocked `check_requirement`/`rate_context` (monkeypatch in `srmapp.evaluate`): `test_first_holding_winding_is_chosen` (first ranked fails, second holds → second chosen, `rate_context` called once), `test_no_winding_holds` (all fail → `ranked[0]`, feasible False, the note), `test_refusal_keeps_em_choice` (`thermal_context` raises `MissingLossData` → rating None, note contains its text), `test_cancel_during_checks` (cancel True after the first check → status "cancelled").
- [ ] **Step 2: Run; expect failures.**
- [ ] **Step 3: Implement** in `evaluate.py`; `case.evaluate_design` passes `thermal`, `n_speeds`, `thermal_progress`.
- [ ] **Step 4: Slow test** `test_rated_choice_8_6` (8/6 screening, 10JNEX900, `continuous_power_w` 100 W as in `tests/app/test_thermal_rate.py`): status ok, rating not None, `rated_continuous_kw_per_kg` finite and > 0, the chosen winding's `check_requirement` holds.
- [ ] **Step 5: Run** `tests/app -q` (fast) and the new slow test.
- [ ] **Step 6: Commit** `R5c: stage 2 checks windings best-first against the rated hot-spot limit`

### Task 4: Search ranks on rated values (`srmapp/pipeline.py`)

**Files:**
- Modify: `src/srmapp/pipeline.py`, `tests/web/` search-job tests (settings only)
- Test: `tests/app/test_app_pipeline.py` (or the existing pipeline test file; find it with `grep -l run_search tests/app`)

**Interfaces:**
- `SearchSettings`: `j_limit` default `J_SCREEN`; `j_peak_max` None means no cap (`peak_cap` returns `math.inf`); new `thermal: bool = True`, `n_speeds: int = 6`.
- `SearchResult.pareto(maximize=(True, True))` over (`rated_continuous_kw_per_kg`, `rated_peak_kw_per_kg`) of feasible evaluations with a rating. Unrated feasible evaluations are left out of the Pareto set.

- [ ] **Step 1: Failing test** `test_pareto_uses_rated_values`: three hand-built feasible `Evaluation`s (use `dataclasses.replace` on one from the mocked stage 2) with rated (cont, peak) = (1, 3), (2, 2), (1, 1) and one unrated → Pareto holds the first two only.
- [ ] **Step 2: Run; expect failure.**
- [ ] **Step 3: Implement**; `run_search` passes `thermal`, `n_speeds` to `evaluate_stage2`.
- [ ] **Step 4:** The real search-job web tests (`grep -rn "run_search\|/api/search" tests/web`) send `thermal: false` if the search request schema gets the field (Task 5), so their 5400 s wait still holds. Run `tests/app -q`.
- [ ] **Step 5: Commit** `R5c: search ranks on rated continuous and peak kW/kg`

### Task 5: Web keeps working (`srmweb`, `web/`)

**Files:**
- Modify: `src/srmweb/jobs.py` (evaluate `STEPS` become queued/mesh/mapping/winding/strokes/thermal/saved; `eta_s` in strokes), `src/srmweb/results.py` (`EvaluationOut.rating`: optional summary — per speed rpm, nominal and rated continuous and peak N·m, hot spot °C and where; limit_c, insulation class, stress status and safety factor, notes — None for older evaluations; `rated_continuous_kw_per_kg`, `rated_peak_kw_per_kg`, `srmcore_version` optional), `src/srmweb/schemas.py` (`SearchRequest.thermal: bool = True`), `web/src/lib/steps.ts` (the two new evaluate steps), `web/openapi.json` and `web/src/api/schema.ts` (regenerated: `python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`).
- Test: `tests/web/test_job_steps.py`, `tests/web/test_web_results.py`, `web/src/lib/steps.test.ts`

- [ ] **Step 1: Failing tests:** evaluate step ids equal the new tuple; `evaluation_json` of an evaluation with a `Rating` round-trips the summary; of an old stored body without `rating` gives `rating` None; `steps.test.ts` maps the strokes and thermal steps.
- [ ] **Step 2: Run; expect failures.**
- [ ] **Step 3: Implement**; no new UI (the Thermal tab and the chips are R5d).
- [ ] **Step 4: Run** `tests/web -m "not slow" -q` and `cd web && npx vitest run && npm run build`.
- [ ] **Step 5: Commit** `R5c: web evaluate steps and the rating in results`

### Task 6: Versions, docs, tracker

**Files:**
- Modify: `src/srmcore/__init__.py`, `src/srmapp/__init__.py`, `src/srmweb/__init__.py`, `web/package.json` (+ lock), `CLAUDE.md`, `docs/r5-thermal-results.md` (one line: R5c merged, what changed), `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` §11 (decision line: J_SCREEN placement and value, feasibility checked at the requirement)

- [ ] **Step 1:** Bump versions (Global Constraints). Run `python tools/engine_digest.py` — the pin must still match (no engine-number change); if a test pins `__version__`, update it. Do not touch `VALIDATED_VERSIONS`.
- [ ] **Step 2:** Run the full fast suite: `PYTHONPATH=src:tests python -m pytest -m "not slow" -q`. Expected: all pass.
- [ ] **Step 3:** CLAUDE.md: current-state line for R5c, the `srmapp` paragraph (scan ranks best-first, `J_SCREEN`, `j_peak_max` default none, rating in stage 2, Pareto on rated kW/kg), Thermal section item 8 (`thermal_context`, `check_requirement`, `rate_context`).
- [ ] **Step 4: Commit** `R5c: versions 0.8.0 / 0.11.0 and docs`. Tracker follow-ups (session, not plan): validation campaign for srmcore 0.8.0; the evaluate estimate does not count rating time (R5d).
