# v0b-1: Web Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web tool that runs the requirements-driven search as a job with live progress, keeps past runs, and shows each run's 2D Pareto plot, candidate table and read-only candidate detail.

**Architecture:** One FastAPI process (`src/srmweb/`) serves a REST + SSE API and the built React app (`web/`). A single worker thread runs `srmapp.run_search`; jobs, progress and results live in SQLite; maps stay in the shared HDF5 cache. The engine is unchanged.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, stdlib `sqlite3`; React 19 + Vite + TypeScript, Tailwind v4, shadcn/ui, TanStack Query and Table, react-router 7, react-plotly.js, Lucide, openapi-typescript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-08-v0b-web-design.md` (v0b-1 row of §2; §3–§5, §6.1, §7.1–§7.3, §7.5, §7.8, §8–§11).

**Not in this plan (v0b-2/3):** cases, `/api/cases`, `/api/validate`, `/api/references`, `evaluate`/`sweep`/`validate` job kinds, setup-file import/export, the map-time history of spec §6.5, reference designs moving to `srmapp`.

## Global Constraints

- Package version stays `0.4.0` (`pyproject.toml`, `srmcore.__version__`). `srmweb.__version__ = "0.1.0"`; `web/package.json` `"version": "0.1.0"`.
- `srmweb` may import `srmapp` and `srmcore` public modules; `srmapp`/`srmcore` never import `srmweb`; `srmweb` never imports `gmsh`, `ngsolve`, `netgen`, `skfem`.
- New extra `web = ["fastapi>=0.115", "uvicorn>=0.30"]`; `httpx>=0.27` added to `dev` (TestClient). `srmapp`/`srmcore` import without the `web` extra.
- SI inside Python and in the API. The UI shows mm, rpm, kW, N·m, V, A, A/mm², kg, mH, mWb, degrees; one conversion table `web/src/lib/units.ts`.
- Defaults: `SRMWEB_HOST=127.0.0.1`, `SRMWEB_PORT=8000`, `SRMWEB_DB=srmweb.db`, `SRMWEB_CACHE_DIR=cache`, `SRMWEB_WORKERS` unset (None), `SRMWEB_TOKEN` unset, `SRMWEB_QUEUE_MAX=10`.
- Caps: `n_candidates` 1..2000, `shortlist` 1..200, `seed` ≥ 0.
- Every result page shows the banner text **"Unvalidated, peak-only"**.
- Tokens: primary `#1E3A5F`, secondary `#2563EB`, feasible `#059669`, error `#DC2626`, background light `#F8FAFC`; Fira Sans (text), Fira Code (numbers); semantic CSS variables only.
- Nav items exactly: **New search · Runs · Cases · Settings** ("Cases" disabled with tooltip "Comes in v0b-2").
- Python test files go in `tests/web/` with basenames `test_web_*.py` (basenames must be unique). Comments describe the code as it is, no plan history.
- `full` stays the default preset; `screening` selectable.

## Review Focus

1. A phone that sleeps mid-search reconnects the SSE stream and must see current progress at once, not zeros → test in Task 7 (`test_events_sends_current_state_first`).
2. The server stops while a search runs; on restart the job must read `interrupted` and **Resume** must start a new job with the same request → tests in Task 5 and Task 6.
3. Failed candidates carry NaN ratios; the API must send `null` (strict JSON) and the table must show "—" → tests in Task 3 and Task 13.
4. A second search submitted while one runs must queue, and the 11th queued must get HTTP 429 → test in Task 6.
5. Requirements whose power disagrees with torque × base speed by more than 10 % must come back as 422 with a field path the form can show inline → test in Task 6 (`test_inconsistent_requirements_422`) and Task 12 (form shows the message).

---

### Task 1: `srmapp` — preset choice and map arrays in `Evaluation`

**Files:**
- Modify: `src/srmapp/sizing/generator.py` (`sample_candidates`), `src/srmapp/pipeline.py` (`SearchSettings`, `run_search`), `src/srmapp/evaluate.py` (`Evaluation`, `evaluate_stage2`)
- Test: `tests/app/test_app_generator.py`, `tests/app/test_app_evaluate.py`

**Interfaces:**
- Produces: `sample_candidates(..., preset: Literal["screening", "full"] = "full")`; `SearchSettings.preset: Literal["screening", "full"] = "full"`, passed through by `run_search`.
- Produces: `@dataclass(frozen=True) class MapArrays: angles: np.ndarray; currents: np.ndarray; psi: np.ndarray; torque: np.ndarray` in `srmapp/evaluate.py` (psi = excited circuit only, shape (n_angles, n_currents), Wb-turns; torque = Arkkio, N·m; both at the chosen turns with the end-winding correction).
- Produces: `Evaluation.map: MapArrays | None = None` (last field); set on status `"ok"`, None otherwise.

- [ ] **Step 1: Write failing tests**

```python
def test_sample_candidates_preset():
    req = make_requirements()            # existing helper in this file, or build Requirements inline
    kept, _ = sample_candidates(req, 4, seed=0, preset="screening")
    assert kept and all(c.design.mesh.preset == "screening" for c in kept)

def test_evaluation_carries_rescaled_map(...):   # reuse the file's existing ok-path fixture
    ev = evaluate_stage2(...)
    assert ev.status == "ok"
    k = turns_scale(machine, ev.winding)
    expected = rescale_turns(with_end_winding(result, l_end), k)
    e = expected.circuits.index(expected.excited)
    np.testing.assert_allclose(ev.map.psi, expected.psi[..., e])
    np.testing.assert_allclose(ev.map.currents, expected.currents)
    np.testing.assert_allclose(ev.map.torque, expected.torque_arkkio)
```

Failed evaluations: `assert _failed(...).map is None`.

- [ ] **Step 2: Run** `python -m pytest tests/app -m "not slow" -q` → the new tests FAIL.
- [ ] **Step 3: Implement.** `sample_candidates` builds `MeshSettings(preset=preset)`. In `evaluate_stage2`, build `rescaled = rescale_turns(result, turns_scale(machine, w))` once, use it for `key_numbers` and `MapArrays`.
- [ ] **Step 4: Run** `python -m pytest tests/app -m "not slow" -q` → PASS.
- [ ] **Step 5: Commit** `feat(srmapp): preset choice in the search, map arrays in Evaluation`.

---

### Task 2: `srmweb` package, config and the exposure guard

**Files:**
- Modify: `pyproject.toml` (extras `web`, `dev` gets `httpx>=0.27`; `[project.scripts] srmweb = "srmweb.__main__:main"`; wheel packages add `src/srmweb`), `tests/app/test_app_layering.py`
- Create: `src/srmweb/__init__.py` (`__version__ = "0.1.0"`), `src/srmweb/config.py`, `src/srmweb/__main__.py`
- Test: `tests/web/test_web_config.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Settings: host: str; port: int; db: Path; cache_dir: Path; workers: int | None; token: str | None; queue_max: int; static_dir: Path` and `load_settings(env: Mapping[str, str] = os.environ) -> Settings`. `static_dir` = `SRMWEB_STATIC` or `<repo>/web/dist` (`Path(__file__).resolve().parents[2] / "web" / "dist"`).
- Produces: `is_loopback(host: str) -> bool` (`ipaddress.ip_address(host).is_loopback`, plus `"localhost"`); `check_exposure(s: Settings) -> None` raises `SystemExit` with message `"SRMWEB_HOST=<host> is not loopback; set SRMWEB_TOKEN to expose the server"` when not loopback and no token.
- Produces: `main(argv: list[str] | None = None) -> None`: `--host`, `--port` override settings, then `check_exposure`, then `uvicorn.run(create_app(settings), host, port)` (`create_app` comes from Task 6; until then import lazily inside `main`).

- [ ] **Step 1: Failing tests** — `load_settings({})` gives the Global Constraints defaults; `load_settings({"SRMWEB_WORKERS": "6"}).workers == 6`; `check_exposure` passes for `127.0.0.1`, `::1`, `localhost`; raises `SystemExit` for `0.0.0.0` without token; passes for `0.0.0.0` with token. Layering: add `test_core_and_app_never_import_srmweb` (same AST walk as the existing test, over `srmcore` and `srmapp`) and `test_srmweb_imports_no_solver_or_mesher` (no `gmsh`, `ngsolve`, `netgen`, `skfem` under `src/srmweb`).
- [ ] **Step 2: Run** `python -m pip install -e ".[dev,ngsolve,web]"` then `python -m pytest tests/web tests/app/test_app_layering.py -q` → config tests FAIL.
- [ ] **Step 3: Implement** `config.py`, `__main__.py`, `__init__.py` as in Interfaces.
- [ ] **Step 4: Run** the same command → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): package, settings and the loopback exposure guard`.

---

### Task 3: JSON serialisation and electrical angles

**Files:**
- Create: `src/srmweb/serialize.py`
- Test: `tests/web/test_web_serialize.py`

**Interfaces:**
- Produces: `to_json(obj) -> Any` — Pydantic → `model_dump(mode="json")`; dataclass → dict of its fields (recursively); `np.ndarray` → nested lists via `.tolist()` after the float check; `float`/`np.floating` NaN or ±inf → `None`; tuples → lists; `Path` → str; everything else unchanged.
- Produces: `electrical_deg_from_unaligned(theta_mech: float, n_rotor_poles: int) -> float` = `degrees((theta_mech - pi / n_rotor_poles) * n_rotor_poles)`. The engine's θ = 0 is phase A aligned; unaligned is half a rotor pole pitch.
- Produces: `evaluation_json(ev: Evaluation) -> dict` = `to_json(ev)` plus `envelope.theta_on_el` and `envelope.theta_off_el` lists (electrical degrees) when `ev.envelope` is set, plus `efficiency` list.
- Produces: `search_result_json(r: SearchResult) -> dict` with keys `requirements, sampled, dropped, stage1_rejected, cancelled, evaluations` (each `evaluation_json`), `pareto_ids` (ids of `r.pareto()`).

- [ ] **Step 1: Failing tests**

```python
def test_nan_and_inf_become_null():
    assert to_json({"a": float("nan"), "b": np.array([1.0, np.inf])}) == {"a": None, "b": [1.0, None]}

def test_dataclass_and_model_nest(): ...      # a Winding inside a dict, a Requirements with a RoundWire
@pytest.mark.parametrize("nr,theta_deg,el", [(6, 30, 0), (6, 45, 90), (6, 60, 180), (6, 15, -90),
                                             (4, 45, 0), (4, 90, 180), (8, 22.5, 0)])
def test_electrical_angle(nr, theta_deg, el):
    assert electrical_deg_from_unaligned(math.radians(theta_deg), nr) == pytest.approx(el)
def test_search_result_json_is_strict(): # build a SearchResult with one ok and one failed Evaluation (NaNs)
    text = json.dumps(search_result_json(r), allow_nan=False)    # must not raise
```

- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_serialize.py -q` → FAIL.
- [ ] **Step 3: Implement** in `serialize.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): strict JSON serialisation and electrical angles`.

---

### Task 4: SQLite store

**Files:**
- Create: `src/srmweb/store.py`
- Test: `tests/web/test_web_store.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION = 1`; `class Store: __init__(self, path: Path)`; creates tables `jobs`, `cases`, `results` exactly as spec §5 (cases unused until v0b-2), WAL mode, `PRAGMA user_version = 1`; raises `RuntimeError("database schema <found> != expected 1")` on a mismatch.
- Produces methods (a fresh `sqlite3.connect` per call; parameterised SQL only; JSON columns via `json.dumps(..., allow_nan=False)`):
  - `create_job(kind: str, request: dict) -> str` (UUID4 str, status `queued`, `created` ISO-8601 UTC)
  - `get_job(job_id: str) -> dict | None` (keys: `id, kind, request, status, progress, error, created, started, finished`; JSON decoded)
  - `list_jobs() -> list[dict]` newest first (without `request`)
  - `set_status(job_id, status, *, error: str | None = None)` (sets `started` on `running`, `finished` on `done|failed|cancelled|interrupted`)
  - `set_progress(job_id, progress: dict)`
  - `put_result(job_id, body: dict, case_id: str | None = None)`; `get_result(job_id) -> dict | None`
  - `delete_job(job_id) -> bool` (removes its results and cases)
  - `mark_running_interrupted() -> int`

- [ ] **Step 1: Failing tests** — round trip of create/get/list order; status timestamps; `put_result` rejects NaN (`ValueError`); `delete_job` removes the result; `mark_running_interrupted` flips only `running`; reopening a file with `user_version = 2` raises `RuntimeError`. Use `tmp_path`.
- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_store.py -q` → FAIL.
- [ ] **Step 3: Implement** `store.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): SQLite store for jobs, cases and results`.

---

### Task 5: Job runner

**Files:**
- Create: `src/srmweb/jobs.py`, `src/srmweb/schemas.py` (search request models only)
- Test: `tests/web/test_web_jobs.py`

**Interfaces:**
- Consumes: `Store` (Task 4), `search_result_json` (Task 3), `run_search`, `SearchSettings`, `StageTwoGrid` (Task 1).
- Produces in `schemas.py` (all `ConfigDict(extra="forbid")`):
  - `SearchSettingsIn`: `n_candidates: int = Field(200, ge=1, le=2000)`, `shortlist: int = Field(40, ge=1, le=200)`, `seed: int = Field(0, ge=0)`, `stator: str = "10JNEX900"`, `rotor: str = "10JNEX900"` (validator: name in `available_materials()` and the material is soft-magnetic), `preset: Literal["screening", "full"] = "full"`, `margin: float | None = Field(None, gt=0)`, `j_peak: float | None = Field(None, gt=0)`, `j_limit: float | None = Field(None, gt=0)`, `j_peak_max: float | None = Field(None, gt=0)` (None → `SearchSettings` defaults).
  - `SearchRequest`: `requirements: Requirements`, `settings: SearchSettingsIn = SearchSettingsIn()`, `grid: tuple[int, int] | None = None` (angles, currents → `StageTwoGrid`; only for tests, hidden from the UI).
- Produces: `Progress = dict` with keys `status, designs_done, designs_total, points_done, points_total, elapsed_s, message`.
- Produces: `class QueueFull(Exception)`; `class JobRunner: __init__(self, store: Store, settings: Settings, run_fn: Callable[[str, dict, Reporter], dict] | None = None)`. `run_fn(kind, request, reporter)` returns the result body; default `run_job` dispatches `kind == "search"` to `run_search_job`.
- Produces: `class Reporter` with `progress(**fields)`, `cancelled() -> bool`; in-memory latest progress per job behind a `threading.Lock` with a version counter; store writes at most once per second plus once at the end.
- Produces: `JobRunner.start()` (calls `store.mark_running_interrupted()`, starts one daemon worker thread), `submit(kind, request) -> str` (raises `QueueFull` when `queue_max` jobs are already `queued`), `cancel(job_id) -> bool`, `progress(job_id) -> tuple[int, Progress] | None` (version, progress; None when the job is not running), `stop()`.
- Produces: `run_search_job(request: dict, reporter: Reporter, settings: Settings) -> dict`: validates `SearchRequest`, builds `SearchSettings` (materials, preset, grid, current-density fields when set), calls `run_search(req, ss, workers=settings.workers, cache_dir=settings.cache_dir, progress=..., point_progress=..., cancel=reporter.cancelled)`, returns `search_result_json(...)`. Message `"sampling candidates"` before the call, `"design i/n"` during stage 2.
- Status rules: exception → `failed` with `f"{type(exc).__name__}: {exc}"`; result with `cancelled` true → result stored, status `cancelled`; else `done`.

- [ ] **Step 1: Failing tests** (fake `run_fn`, `tmp_path` store)
  - `test_job_runs_and_stores_result` — fake returns `{"ok": 1}`; poll until `done`; `store.get_result` equals it.
  - `test_jobs_run_one_at_a_time_fifo` — two submits; the fake records start order and asserts no overlap.
  - `test_cancel_sets_cancelled` — fake loops on `reporter.cancelled()`, returns `{"cancelled": True}`.
  - `test_failure_records_error` — fake raises `ValueError("boom")` → `failed`, error `"ValueError: boom"`.
  - `test_queue_full` — `queue_max=1`, a blocking fake; second queued submit raises `QueueFull`.
  - `test_restart_marks_interrupted` — set a job `running` in the store, `JobRunner(...).start()` → `interrupted`.
  - `test_progress_version_increments` — fake calls `reporter.progress(points_done=1)` then `2`.
  - `@pytest.mark.slow test_real_search_job_in_thread` — `run_search_job` with `n_candidates=2, shortlist=1`, `preset="screening"`, a `StageTwoGrid(n_angles=4, n_currents=3)` override (request field `grid`, test-only), `workers=2`: the spawn pool starts from the worker thread and the job ends `done` (Windows risk in spec §4.3).
- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_jobs.py -m "not slow" -q` → FAIL.
- [ ] **Step 3: Implement** `jobs.py`.
- [ ] **Step 4: Run** `python -m pytest tests/web/test_web_jobs.py -q` (includes slow) → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): single-thread job runner with cancel, queue cap and interrupted jobs`.

---

### Task 6: Request schemas, app factory and job routes

**Files:**
- Create: `src/srmweb/api.py`
- Modify: `src/srmweb/schemas.py`
- Test: `tests/web/test_web_api.py`

**Interfaces:**
- Consumes: `Store`, `JobRunner`, `QueueFull`, `Settings`, `SearchRequest` (Task 5).
- Produces in `schemas.py`:
  - `JobIn`: `kind: Literal["search"]`, `payload: SearchRequest`. (Other kinds come with v0b-2.)
  - `JobOut`: `id, kind, status, progress: dict | None, error: str | None, created, started, finished`.
- Produces in `api.py`: `create_app(settings: Settings, runner_factory=JobRunner) -> FastAPI` — builds `Store(settings.db)`, the runner, starts it on startup (lifespan), stops on shutdown; all routes on an `APIRouter(prefix="/api")`.
- Routes (this task): `POST /api/jobs` → 201 `{"id"}`, 429 on `QueueFull`; `GET /api/jobs` → `list[JobOut]`; `GET /api/jobs/{id}` → `JobOut` (live progress from `runner.progress` when running) or 404; `GET /api/jobs/{id}/result` → body or 404; `POST /api/jobs/{id}/cancel` → 202 or 404/409 (not queued/running); `POST /api/jobs/{id}/resume` → 201 `{"id"}` new job with the same request, only for `interrupted|cancelled|failed`, else 409; `DELETE /api/jobs/{id}` → 204, 409 while queued or running.
- Produces: `GET /api/health` → `{"version": srmweb.__version__, "srmcore": srmcore.__version__}`.

- [ ] **Step 1: Failing tests** (`TestClient(create_app(settings, runner_factory=FakeRunnerFactory))`, settings from `tmp_path`)
  - `test_submit_and_poll_search` — 201; job reaches `done`; result returned.
  - `test_unknown_kind_422`, `test_extra_field_422`, `test_caps_422` (`n_candidates=2001`, `shortlist=0`).
  - `test_inconsistent_requirements_422` — power 10 kW, torque 50 N·m, base 3000 rpm → 422 whose `detail[0]["loc"]` starts with `["body", "payload", "requirements"]`.
  - `test_unknown_material_422` — `stator="unobtainium"`; also `stator="copper"` → 422.
  - `test_queue_full_429` — `queue_max=1` with a blocking fake.
  - `test_resume_creates_new_job` — mark a job `interrupted` in the store; resume → new id, same `request`.
  - `test_delete_running_409`, `test_delete_done_204`, `test_cancel_done_409`, `test_missing_job_404`.
- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_api.py -q` → FAIL.
- [ ] **Step 3: Implement** `JobIn`/`JobOut` and `api.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): app factory, request schemas and job routes`.

---

### Task 7: Live progress over SSE

**Files:**
- Modify: `src/srmweb/api.py`
- Test: `tests/web/test_web_events.py`

**Interfaces:**
- Produces: `GET /api/jobs/{id}/events` → `text/event-stream`. Each event: `event: progress\ndata: <JobOut JSON>\n\n`. Sends the current state at once; then, while the job is queued or running, polls `runner.progress` every 0.5 s and sends when the version changes, plus `: keep-alive\n\n` every 15 s; when the job reaches a terminal status sends one final `event: end` with the `JobOut` and closes. For a job already terminal: one `end` event, close. 404 for an unknown id. Headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

- [ ] **Step 1: Failing tests** (fake runner whose progress the test drives)
  - `test_events_sends_current_state_first` — job mid-run with `points_done=7`; first event's data has `progress.points_done == 7`.
  - `test_events_end_on_done` — fake finishes; stream ends with `event: end` and status `done`.
  - `test_events_terminal_job_single_end`, `test_events_404`.
  Read the stream with `client.stream("GET", ...)` and `iter_lines()`.
- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_events.py -q` → FAIL.
- [ ] **Step 3: Implement** with `StreamingResponse` and an `async` generator (`await asyncio.sleep(0.5)`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): job progress over server-sent events`.

---

### Task 8: Token login and session cookie

**Files:**
- Create: `src/srmweb/auth.py`
- Modify: `src/srmweb/api.py`
- Test: `tests/web/test_web_auth.py`

**Interfaces:**
- Produces: `class Sessions` (in-memory `set[str]` of `secrets.token_urlsafe(32)` ids, lock-guarded); `require_auth(request) -> None` dependency: no-op when `settings.token is None` (only possible on loopback, Task 2), else 401 unless cookie `srmweb_session` is a live session.
- Routes: `POST /api/login` body `{"token": str}` → 204 + `Set-Cookie: srmweb_session=<id>; HttpOnly; SameSite=Strict; Path=/`, 401 on mismatch (`hmac.compare_digest`); `POST /api/logout` → 204, session removed, cookie cleared; `GET /api/session` → `{"auth_required": bool, "logged_in": bool}` (open, so the page knows whether to show login). Every other `/api` route depends on `require_auth`.

- [ ] **Step 1: Failing tests** — no token: `GET /api/jobs` is 200; with token `"t0k"`: `GET /api/jobs` 401, wrong token 401, right token 204 and then 200; cookie header contains `HttpOnly` and `SameSite=Strict`; logout then 401; `/api/session` reflects both states.
- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_auth.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python -m pytest tests/web -m "not slow" -q` → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): token login with an HttpOnly SameSite=Strict session`.

---

### Task 9: Geometry, materials, cache settings, static app, Swagger and the OpenAPI dump

**Files:**
- Create: `src/srmweb/geometry.py`, `src/srmweb/openapi.py`
- Modify: `src/srmweb/api.py`
- Test: `tests/web/test_web_geometry.py`, `tests/web/test_web_misc_routes.py`

**Interfaces:**
- Produces: `outline_svg(machine: RadialSRMParams) -> dict` from `srmcore.topology.radial.build_outline`: `{"view_box": [x, y, w, h], "stator": d, "rotor": d, "shaft": d, "coils": [{"name", "phase", "sign", "d"}]}`. Path data in **mm**, y flipped (SVG y down). `Line` → `L`; `Arc` → `A r r 0 0 sweep x y` with `sweep = 1` when the cross product (start − center) × (end − center) is negative after the flip; circles as two half arcs. Stator path = outer circle + `stator_inner_boundary` (draw with `fill-rule="evenodd"`); rotor = `rotor_outer_boundary` + shaft circle.
- Routes: `POST /api/geometry` body `RadialSRMParams` → `outline_svg` (422 with the `InputError` parameter and rule on a fit failure); `GET /api/materials` → `[{"name", "grade", "thickness_mm", "js"}]` soft-magnetic library entries; `GET /api/settings/cache` → `{"path", "files", "bytes"}`; `DELETE /api/settings/cache` → 204 (deletes `*.h5` in `cache_dir`, 409 while a job runs).
- Swagger: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`; `GET /api/openapi.json` and `GET /api/docs` (`get_swagger_ui_html(openapi_url="/api/openapi.json")`) behind `require_auth`.
- Static: when `settings.static_dir/index.html` exists, mount `/assets` from it and serve `index.html` for any non-`/api` GET (SPA fallback); otherwise `/` returns 200 text `"Frontend not built: cd web && npm ci && npm run build"`.
- `python -m srmweb.openapi [path]` writes `create_app(...).openapi()` as sorted, indented JSON to `path` (default `web/openapi.json`).

- [ ] **Step 1: Failing tests** — `outline_svg(make_8_6())`: 16 coil sides (`len(coils) == 16`, a `+` and a `-` side per pole), every `d` starts with `M`, `view_box` width ≈ stator OD in mm (160 ± 1); geometry route 200 for `make_8_6()` and 422 for an overlapping-pole design (`stator_pole_arc=math.radians(40)`); materials list contains `10JNEX900` grade `B` and no `copper`; cache size counts a dummy `.h5`; `DELETE` removes it; `/api/docs` 200 without token and 401 with token and no session; SPA fallback serves `index.html` for `/runs/abc` when `static_dir` holds one; `python -m srmweb.openapi <tmp>` writes JSON with `"/api/jobs"` in `paths`.
- [ ] **Step 2: Run** `python -m pytest tests/web -m "not slow" -q` → new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(srmweb): motor outline SVG, materials, cache settings, static app and Swagger`.

---

### Task 10: End-to-end search through the API and CI

**Files:**
- Test: `tests/web/test_web_e2e.py`
- Modify: `.github/workflows/ci.yml`, `.github/workflows/slow.yml`, `.gitignore` (`srmweb.db*`, `cache/`, `web/node_modules/`, `web/dist/`)

**Interfaces:**
- Consumes: everything above with the real `JobRunner`.

- [ ] **Step 1: Write** `@pytest.mark.slow test_search_job_end_to_end` — real app, `tmp_path` db and cache, `SearchRequest` with `n_candidates=2, shortlist=1, preset="screening", grid=(4, 3)`; poll `/api/jobs/{id}` to `done` (timeout 30 min); result has `sampled >= 1`, `len(evaluations) == 1`, `json.dumps(..., allow_nan=False)` works, and an `ok` evaluation has `map.psi` of shape 4 × 3 and `envelope.theta_on_el`.
- [ ] **Step 2: Run** `python -m pytest tests/web/test_web_e2e.py -q` → PASS (it exercises finished code; a failure here is a bug in Tasks 1–9).
- [ ] **Step 3: CI.** The Python jobs in `ci.yml` and `slow.yml` install `".[dev,ngsolve,web]"`. (The Node job comes in Task 12.)
- [ ] **Step 4: Run** `python -m pytest -m "not slow" -q` → PASS, fast-suite time noted.
- [ ] **Step 5: Commit** `test(srmweb): end-to-end search job; CI installs web and builds the frontend`.

---

### Task 11: Frontend scaffold, theme, layout and units

**Files:**
- Create: `web/` (Vite React-TS template), `web/vite.config.ts` (React plugin, `@tailwindcss/vite`, alias `@` → `src`, dev proxy `/api` → `http://127.0.0.1:8000`, Vitest `environment: "jsdom"`), `web/src/index.css` (tokens), `web/src/main.tsx`, `web/src/App.tsx` (router), `web/src/components/layout/AppShell.tsx`, `web/src/components/layout/ThemeToggle.tsx`, `web/src/components/Banner.tsx`, `web/src/lib/units.ts`, `web/src/lib/format.ts`, shadcn components via CLI (`button card input label select tabs table badge progress tooltip sonner separator sheet`)
- Test: `web/src/lib/units.test.ts`, `web/src/lib/format.test.ts`

**Interfaces:**
- Produces: `units.ts` — `type Unit = "mm" | "rpm" | "kW" | "Nm" | "V" | "A" | "A/mm2" | "kg" | "mH" | "mWb" | "deg" | "m" | "W"`; `toSI(value: number, unit: Unit): number`, `fromSI(value: number, unit: Unit): number` (mm ↔ m ×1e-3, kW ↔ W ×1e3, A/mm² ↔ A/m² ×1e6, mH ↔ H ×1e-3, mWb ↔ Wb ×1e-3, deg ↔ rad π/180, rpm, N·m, V, A, kg identity); `UNIT_LABEL: Record<Unit, string>` (`"A/mm²"`, `"N·m"`, …).
- Produces: `format.ts` — `fmt(value: number | null | undefined, digits = 3): string` returns `"—"` for null/undefined/NaN, else `toPrecision`-style with thin-space thousands; `fmtSI(value, unit, digits)` = `fmt(fromSI(value, unit), digits)`.
- Produces: routes `/` → redirect `/search`, `/search`, `/runs`, `/runs/:jobId`, `/runs/:jobId/candidates/:candidateId`, `/settings`, `/login`; `AppShell` with sidebar ≥ 768 px and a bottom bar < 768 px (four items, Lucide icons `Search`, `List`, `Layers`, `Settings`, labels visible, 44 px targets); theme follows `prefers-color-scheme`, toggle stored in `localStorage` (try/catch), `.dark` class on `<html>`.
- `index.css` defines light and dark semantic variables from the Global Constraints colours and loads Fira Sans + Fira Code from Google Fonts; `.num` class uses Fira Code with `font-variant-numeric: tabular-nums`.
- `package.json` scripts: `dev`, `build` (`tsc -b && vite build`), `test` (`vitest run`), `gen:api` (`openapi-typescript openapi.json -o src/api/schema.ts`).

- [ ] **Step 1: Failing tests** — `toSI(160, "mm") === 0.16`; `fromSI(2e7, "A/mm2") === 20`; `toSI(90, "deg") ≈ π/2`; round trip for every unit; `fmt(NaN) === "—"`, `fmt(null) === "—"`, `fmt(12.436, 3) === "12.4"`.
- [ ] **Step 2: Run** `cd web && npx vitest run` → FAIL.
- [ ] **Step 3: Implement** scaffold, tokens, shell, units, format; placeholder pages for each route showing the page title.
- [ ] **Step 4: Run** `npx vitest run && npm run build` → PASS, `web/dist/index.html` exists; `srmweb` serves it at `/`.
- [ ] **Step 5: Commit** `feat(web): Vite React shadcn scaffold, theme, app shell and units`.

---

### Task 12: API client, login and the New search page

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `web/openapi.json` (generated), `web/src/api/schema.ts` (generated), `web/src/api/client.ts`, `web/src/api/useJobEvents.ts`, `web/src/pages/LoginPage.tsx`, `web/src/pages/NewSearchPage.tsx`, `web/src/components/search/WireListEditor.tsx`, `web/src/lib/searchForm.ts`
- Test: `web/src/lib/searchForm.test.ts`

**Interfaces:**
- Consumes: `schema.ts` types (`components["schemas"]["SearchRequest"]`, `JobOut`), `units.ts`.
- Produces: `client.ts` — `api<T>(path: string, init?: RequestInit): Promise<T>` (`credentials: "same-origin"`, JSON body, throws `ApiError {status, detail}`; on 401 navigates to `/login?next=<path>`); `submitSearch(req: SearchRequest): Promise<{id: string}>`.
- Produces: `useJobEvents(jobId: string): { job: JobOut | null; connected: boolean }` — `EventSource("/api/jobs/<id>/events")`, updates on `progress` and `end`, closes on `end`, re-fetches `GET /api/jobs/<id>` on `error` then lets `EventSource` reconnect.
- Produces: `searchForm.ts` — `type SearchFormValues` (UI units: kW, N·m, rpm, V, mm, kg, A; wires in mm), `defaultSearchForm(): SearchFormValues` (10 kW, 32 N·m, 3000/9000 rpm, 400 V, no limits, density mode, 200/40/seed 0, 10JNEX900, `full`), `toSearchRequest(v: SearchFormValues): SearchRequest` (converts to SI), `fieldErrors(detail: ApiError["detail"]): Record<string, string>` (maps 422 `loc` paths like `body.payload.requirements.peak_power_w` to form field names).
- New search page: sections Requirements (power, torque, base and max speed, bus voltage, max OD, max mass, max slot fill), Winding (toggle Density / Wire list; wire list editor with round, rectangular and litz rows in mm; phase current shown in wire mode), Search (candidates, shortlist, seed, stator and rotor material from `GET /api/materials` with grade badge, preset `full` / `screening` with the note "screening is quicker and less accurate; results show their preset"). Visible labels, unit beside each field, `inputmode="decimal"`, inline error under a field from `fieldErrors`, a top error summary. Submit → `/runs/<id>`. Import/export of search setups comes with v0b-2.
- Login page: one token field, `POST /api/login`, then back to `next`.

- [ ] **Step 1: Failing tests** — `toSearchRequest(defaultSearchForm())` gives `peak_power_w = 10000`, `max_outer_diameter_m` null; a round wire `{diameter: 1.0, outer_diameter: 1.08}` mm becomes `0.001`/`0.00108` m; `fieldErrors([{loc: ["body","payload","requirements","peak_power_w"], msg: "x"}])` → `{"requirements.peak_power_w": "x"}`; a model-level requirements error (loc ends at `requirements`) maps to `"requirements"` and shows in the summary.
- [ ] **Step 2: Run** `npx vitest run` → FAIL.
- [ ] **Step 3: Implement**; run `python -m srmweb.openapi web/openapi.json && npm run gen:api` to generate the schema. Add CI job `web` to `ci.yml` (ubuntu-latest, Node 22, Python 3.12): `pip install -e ".[web]"`, `python -m srmweb.openapi web/openapi.json`, then in `web/`: `npm ci`, `npm run gen:api`, `git diff --exit-code src/api/schema.ts openapi.json`, `npm run build`, `npx vitest run`.
- [ ] **Step 4: Run** `npx vitest run && npm run build` → PASS.
- [ ] **Step 5: Commit** `feat(web): API client, login and the New search page`.

---

### Task 13: Runs list and Run page

**Files:**
- Create: `web/src/pages/RunsPage.tsx`, `web/src/pages/RunPage.tsx`, `web/src/components/run/RunProgress.tsx`, `web/src/components/run/ParetoPlot.tsx`, `web/src/components/run/CandidateTable.tsx`, `web/src/lib/candidates.ts`
- Test: `web/src/lib/candidates.test.ts`

**Interfaces:**
- Consumes: `useJobEvents`, `api`, `fmt`/`fmtSI`, result JSON shape from Task 3 (`search_result_json`).
- Produces: `candidates.ts` — `type CandidateRow = {id, poles: string, od_mm, mass_kg, torque_ratio, power_ratio, peak_power_kw, power_density, efficiency_base, feasible: boolean, status, pareto: boolean}` and `toRows(result): CandidateRow[]`; `AXES` = `{mass_kg: "Mass (kg)", peak_power_kw: "Peak power (kW)", power_density: "Power density (kW/kg)", efficiency_base: "Efficiency at base speed", torque_ratio: "Torque ratio"}`.
- Runs page: table (cards < 768 px) of jobs: status badge, created, progress bar for the running job, actions Open, Cancel (queued/running), Resume (interrupted/cancelled/failed), Delete (terminal, with a confirm dialog). Empty state: "No runs yet" + button "Start a search".
- Run page: banner "Unvalidated, peak-only"; while queued/running: `RunProgress` with two bars (designs done / shortlist; map points done / total for the current design), elapsed time `h:mm:ss`, message, and an `aria-live="polite"` status line such as "Design 3 of 40, map 120 of 960 points"; Cancel button. When done or cancelled: counts (sampled, dropped by validator and fit, stage-1 rejected, evaluated), `ParetoPlot` and `CandidateTable`.
- `ParetoPlot`: Plotly 2D scatter; X and Y selects from `AXES` (default mass vs power density); colour = efficiency at base speed (continuous); marker symbol per pole set (`circle`, `square`, `diamond`, `triangle-up`); infeasible and failed points grey hollow; Pareto points outlined in the primary colour; click → candidate page. A "3D" toggle only at ≥ 1024 px (Z select). Below it the axis legend text.
- `CandidateTable`: TanStack Table, sortable, columns id, poles, OD (mm), mass (kg), torque ratio, power ratio, peak power (kW), kW/kg, efficiency, status; `fmt` shows "—" for null; failed rows show their status and error in a tooltip; cards < 768 px.

- [ ] **Step 1: Failing tests** — `toRows` on a fixture result with one ok and one failed evaluation: failed row has `feasible === false`, `torque_ratio === null`, and `fmt(row.torque_ratio) === "—"`; `pareto` true exactly for ids in `pareto_ids`; `od_mm` = 1000 × `stator_outer_diameter`.
- [ ] **Step 2: Run** `npx vitest run` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npx vitest run && npm run build` → PASS.
- [ ] **Step 5: Commit** `feat(web): runs list and run page with live progress, Pareto plot and candidate table`.

---

### Task 14: Candidate detail page

**Files:**
- Create: `web/src/pages/CandidatePage.tsx`, `web/src/components/candidate/MotorDiagram.tsx`, `web/src/components/candidate/MapCharts.tsx`, `web/src/components/candidate/EnvelopeChart.tsx`, `web/src/components/candidate/WindingScan.tsx`, `web/src/lib/mapCurves.ts`
- Test: `web/src/lib/mapCurves.test.ts`

**Interfaces:**
- Consumes: run result (cached by TanStack Query from Task 13), `POST /api/geometry`.
- Produces: `mapCurves.ts` — `psiCurves(map): {angleDeg: number, i: number[], psi_mWb: number[]}[]` (one curve per map angle, angle in mechanical degrees); `torqueGrid(map): {angleDeg: number[], i: number[], torque: number[][]}`.
- Page sections: banner; key numbers (La, Lu in mH, La/Lu, peak torque, ψ_max in mWb, I_max) with `.num`; `MotorDiagram` (SVG from `/api/geometry` with the design's machine: stator and rotor in muted fill with `fill-rule="evenodd"`, coils coloured per phase with a legend, phase letter labels, scales to its container); winding (turns, strands, paths, wire kind, R in mΩ, J_rms in A/mm², I_rms); ψ-i curves (Plotly lines, up to 6 angles selected evenly incl. aligned and unaligned, line style varies with colour); torque map (Plotly heatmap θ × i); torque-speed and power-speed (`EnvelopeChart`) with turn-on and turn-off angles in electrical degrees in the hover text; winding scan table (turns × paths, torque ratio, power ratio, feasible); notes (`error` text) and status.

- [ ] **Step 1: Failing tests** — on a 3 × 2 fixture map, `psiCurves` returns 3 curves of 2 points with ψ in mWb (×1000) and angles in degrees; `torqueGrid` keeps the (angles × currents) orientation.
- [ ] **Step 2: Run** `npx vitest run` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npx vitest run && npm run build` → PASS.
- [ ] **Step 5: Commit** `feat(web): candidate detail with motor diagram, map charts, envelope and winding scan`.

---

### Task 15: Settings page, docs and the smoke test

**Files:**
- Create: `web/src/pages/SettingsPage.tsx`
- Modify: `CLAUDE.md` (Commands: `srmweb`, `cd web && npm run dev`, `python -m srmweb.openapi`; a short "Web layer (v0b)" section: modules, routes, security rule, SQLite file, layering), `README` section if one exists

**Interfaces:**
- Settings page: theme (system / light / dark), cache size with "Clear cache" (confirm dialog; disabled while a job runs), versions from `/api/health`, a note on units, Logout when auth is on.

- [ ] **Step 1: Implement** the page; `npm run build`.
- [ ] **Step 2: Smoke test** in the in-app browser against `srmweb` serving the build: run a search with `n_candidates=4, shortlist=1, preset=screening`; check live progress, results, Pareto click → candidate page, light and dark, widths 375, 768, 1024, 1440. With `SRMWEB_HOST=0.0.0.0` and no token the server refuses to start; with a token the login page appears. Record what was checked in the commit body.
- [ ] **Step 3: Run** `python -m pytest -m "not slow" -q` and `cd web && npx vitest run` → PASS.
- [ ] **Step 4: Commit** `feat(web): settings page; docs for the web layer`.
- [ ] **Step 5: Review gate** — run the `mattpocock-skills:codebase-design` review on the branch, fix findings, update the living project doc (v0b section: v0b-1 done), then hand the merge decision to the owner.
