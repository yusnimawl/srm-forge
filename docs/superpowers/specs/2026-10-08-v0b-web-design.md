# v0b: Web Tool — Design Spec

Owner-approved in chat 2026-10-08; written spec awaiting review. Parent: `2026-09-30-v0-walking-skeleton-design.md` §5 (web layer), which this spec replaces. Workflow reference: `docs/jmag-express-srm-reference.md`. Correctness first; run time is not a constraint.

## 1. Purpose

A web tool for the owner, used from a laptop or a phone: run a requirements-driven search with live progress, reopen past runs, open any candidate as an editable JMAG-style case, re-evaluate it, sweep one parameter, EM-validate it, and compare cases. It runs locally now and on a home server later.

The engine (`srmcore`, M1–M5) is not changed. `srmapp` gets small additions (§6). The new code is a web layer.

## 2. Scope and steps

One spec, built and merged in three steps. Each step is usable on its own.

| Step | Adds |
|---|---|
| **v0b-1** | server, job runner, store, security, search form, live progress, runs list, run results (Pareto + candidate table), read-only candidate detail, Swagger, generated TS types |
| **v0b-2** | cases: start from a candidate, a reference design or an imported setup; input tabs; live validation and motor diagram; Evaluate; Validate (EM); export/import; cases table with flags, comments and overlays; Field tab: interactive mesh, \|B\| and flux-line view, and a rotor animation (§7.9); analysis plots and drive waveforms (§6.7, §7.10) |
| **v0b-3** | one-parameter sweep (Range or Table) with a cost estimate; two-parameter design study with families of curves (§6.8, §7.7) |

Out of scope: an optimiser (NSGA, Bayesian or other; §13), fixed conduction angles, custom B-H upload, PDF reports, accounts, HTTPS, N-T efficiency maps, iron loss and thermal (no loss or thermal models exist; iron loss and iron-loss efficiency wait for sub-project #2).

Every result shows the banner **"unvalidated, peak-only"** unless the case carries an EM-validated label (§7.4).

## 3. Architecture

One process, a modular monolith. Folders are packages; no microservices.

```
browser (laptop, phone) ──HTTP──► uvicorn
                                    └─ srmweb (FastAPI)
                                         ├─ /api/...           REST + SSE
                                         ├─ /api/docs          Swagger UI
                                         ├─ /                  web/dist (built React app)
                                         └─ JobRunner ── 1 worker thread ──► srmapp (search, evaluate, sweep)
                                                                               └─ build_map spawn pool
                                    disk: srmweb.db (SQLite)   cache/ (HDF5 maps, shared)
```

Repository layout:

```
pyproject.toml     one distribution "srmcore" 0.4.0; extras dev, ngsolve, web (fastapi, uvicorn)
src/srmcore/       engine (unchanged)
src/srmapp/        search, evaluate, sweep, reference designs
src/srmweb/        server (own __version__)
web/               React + Vite + TypeScript + shadcn/ui + Tailwind + Plotly (own package.json)
tests/web/         API tests
```

- The package version stays **0.4.0** through v0b. It feeds the map provenance hash and `VALIDATED_VERSIONS`; bumping it for web-only work would invalidate the cache and drop the EM-validated label. Bump only when the engine changes. `srmweb.__version__` and `web/package.json` carry the web version.
- Layering, enforced by tests: `srmweb` may import `srmapp` and `srmcore` public modules; `srmapp` and `srmcore` never import `srmweb`. `tests/app/test_app_layering.py` is extended. `srmweb` must not import `gmsh`, `ngsolve`, `netgen` or `skfem`.
- `srmapp` and `srmcore` stay importable without the `web` extra.

## 4. Backend (`src/srmweb/`)

| Module | Job |
|---|---|
| `config.py` | Settings from environment: `SRMWEB_HOST` (default `127.0.0.1`), `SRMWEB_PORT` (8000), `SRMWEB_DB` (`srmweb.db`), `SRMWEB_CACHE_DIR` (`cache/`), `SRMWEB_WORKERS` (None = half the logical CPUs), `SRMWEB_TOKEN`, `SRMWEB_QUEUE_MAX` (10). |
| `store.py` | SQLite, stdlib `sqlite3`, WAL mode, parameterised SQL only, no ORM. Tables `jobs`, `cases`, `results` (§5). |
| `jobs.py` | `JobRunner`: FIFO queue, one worker thread, cancel through a `threading.Event`, progress kept in memory and written to the store. |
| `schemas.py` | Pydantic request and response models (`extra="forbid"`, bounded fields). They define the OpenAPI schema. |
| `serialize.py` | `to_json`: Pydantic `model_dump(mode="json")`, dataclass to dict, ndarray to list, NaN and ±inf to `null`. Electrical-angle fields added here (§7.5). |
| `geometry.py` | `Design` → SVG path data from `srmcore.topology.build_outline` (pure Python, no gmsh). |
| `auth.py` | Token login and session cookie (§8). |
| `api.py` | Routes (§4.1). Serves `web/dist` at `/`. |
| `__main__.py` | `srmweb` console script: `srmweb [--host] [--port]`. |

### 4.1 Routes

All under `/api`, all behind auth (§8).

| Route | Purpose |
|---|---|
| `POST /jobs` | submit a job: `kind` ∈ {`search`, `evaluate`, `sweep`, `validate`, `animate`, `study`} plus its payload |
| `GET /jobs` | list jobs (kind, status, created, finished, summary) |
| `GET /jobs/{id}` | one job with its latest progress |
| `GET /jobs/{id}/events` | SSE stream of progress (§4.2) |
| `GET /jobs/{id}/result` | the stored result |
| `POST /jobs/{id}/cancel` | request cancel |
| `POST /jobs/{id}/resume` | re-submit an `interrupted` or `cancelled` job's request |
| `DELETE /jobs/{id}` | delete a job and its results; the map cache is untouched |
| `GET /cases`, `GET /cases/{id}`, `PATCH /cases/{id}` | cases list, one case, set flag, comment, "show in graphs" |
| `POST /validate` | case inputs → field errors and warnings, instant |
| `POST /geometry` | design → SVG paths, instant |
| `GET /materials` | library materials with grade (A/B/C) and lamination thickness |
| `GET /references` | reference designs (8/6, 12/8, 24/16) |
| `POST /field` | case design, rotor angle, phase current → one field frame (§6.6), binary; runs on the quick lane (§4.3) |
| `GET /jobs/{id}/frames` | the frames of a finished `animate` job, binary |
| `GET /settings/cache`, `DELETE /settings/cache` | cache size; clear the map cache and the field-frame cache |
| `POST /login`, `POST /logout` | §8 |

### 4.2 Live progress: Server-Sent Events

Progress flows one way, server to page, every one to two seconds. SSE fits: plain HTTP, native `EventSource` in browsers with automatic reconnect, works with the session cookie, no new dependency (Starlette `StreamingResponse`). WebSocket (two-way), gRPC, ROS 2 and MQTT were considered and rejected: no two-way traffic is needed, and each adds a proxy, a broker or reconnect code.

- `GET /jobs/{id}/events` sends the current progress at once, then each change, then a final event with the terminal status, and closes.
- Event data: `{status, designs_done, designs_total, points_done, points_total, elapsed_s, message}`. For `evaluate` and `validate`, `designs_*` is 1; for `sweep`, it counts sweep values.
- The runner keeps the latest progress per job in memory (a lock-guarded dict with a version counter) and writes it to the store at most once per second, so a page opened mid-job or after a reconnect gets the current state.
- The page also re-reads `GET /jobs/{id}` when the stream closes.

### 4.3 Job runner

- One job runs at a time. A single map already fills the cores, and `build_map` starts its own spawn pool per design, whose start-up cost (seconds) is small next to a `full` map (26 min for the 8/6 and 35 min for the 12/8 with 8 workers, M5e2 speed budget; a search with a 40-design shortlist runs about a day). No long-lived pool.
- The worker thread calls `srmapp` with `cache_dir` always set, `workers` from config, and `cancel=event.is_set`. Callbacks update the in-memory progress.
- Job states: `queued` → `running` → `done` | `failed` | `cancelled`. On server start, any job left `running` becomes `interrupted`.
- **Resume** re-submits the stored request. Sampling is seeded and finished maps are cache hits, so a resumed search skips the designs already mapped.
- A failed job stores the exception type and message. Per-design failures inside a search are already `Evaluation.status` values and show as failed candidates, not as a failed job.
- The queue holds at most `SRMWEB_QUEUE_MAX` queued jobs; more are rejected with HTTP 429.
- Risk to test first: a spawn pool started from a worker thread under uvicorn, on Windows and Linux.
- **Quick lane.** Field work is short and interactive, so it does not wait behind a day-long search. A second runner lane (one thread, one worker process, single-threaded numerics) runs `POST /field` requests and `animate` jobs, one at a time, in arrival order. It competes with a running map for one core only. A field request times out after 120 s.

## 5. Storage

SQLite file `srmweb.db`. Back up by copying the file.

| Table | Columns |
|---|---|
| `jobs` | `id` (UUID text), `kind`, `request` (JSON), `status`, `progress` (JSON), `error`, `created`, `started`, `finished` |
| `cases` | `id` (UUID), `job_id`, `parent_case_id` (null), `origin` (`candidate` / `reference` / `import` / `edit` / `sweep`), `label`, `inputs` (JSON, §6.2), `flag` (null or text), `comment`, `show_in_graphs` (bool), `stale` (bool), `created` |
| `results` | `job_id`, `case_id` (null for a search summary), `body` (JSON: `SearchResult` or `Evaluation` or `EmValidation`) |

- Results are JSON text, typically 100 KB to a few MB per job.
- The HDF5 map cache (`SRMWEB_CACHE_DIR`) is shared by all jobs. It is never deleted automatically; the Settings page shows its size and offers "clear cache".
- Deleting a job deletes its rows and results, never maps.
- A schema version is stored in SQLite `user_version`; a mismatch at start refuses to run and names the expected version (no automatic migrations in v0b).

## 6. `srmapp` additions

### 6.1 Map arrays in `Evaluation`

`Evaluation` gains `map: MapArrays | None`: `angles`, `currents`, `psi`, `torque` of the map at the chosen turns, with the end-winding correction (what the drive envelope used). The detail view draws ψ-i curves and the torque map from it without touching the cache. A `full` map is 48 × 20 points.

### 6.2 Single-design evaluate

`evaluate_design(design, req, *, winding=None, settings, solver, workers, cache_dir, progress, cancel) -> Evaluation`:

- builds the reference-turns design, runs stage 1 for its mass and map current (`i_map`), then `evaluate_stage2`;
- `winding=None` is **Auto** (the turns scan chooses, as in the search); a `Winding` is **Fixed**: the envelope and scores are computed for that winding on the rescaled map, with no scan;
- a stage-1 rejection does not stop it: the owner asked for this design, so the map is built and the stage-1 reason is added to the notes.

Case inputs (`inputs` in §5): `Requirements`, `Design` (geometry, materials, preset), winding mode (`auto` or a fixed `Winding`), and search settings that set the map range (`j_peak`, `j_limit`, `j_peak_max`, `margin`).

### 6.3 Sweep

`sweep(inputs, parameter, values, ...) -> tuple[Evaluation, ...]` runs `evaluate_design` once per value. `parameter` is a dotted path into the case inputs (e.g. `design.machine.stack_length`, `winding.turns`, `requirements.bus_voltage_v`). Each value is validated before any solve; an invalid value is reported per value and skipped.

### 6.4 Reference designs

The `make_8_6`, `make_12_8`, `make_24_16` factories move from `tests/conftest.py` to `srmapp/references.py`; `conftest.py` imports them, so tests are unchanged.

### 6.6 Field frames

`field_frames(design, angles, coil_current, *, solver) -> FieldFrames` in `srmapp/field.py`. It builds the static mesh once (`build_machine_mesh`), then for each angle runs `solve_point(..., keep_field=True)` with phase A excited at `coil_current` (the reference-turns ampere-turns of the chosen winding at the asked phase current, so the field is exact for any turn count). Plain arrays only:

- Static part, sent once: node coordinates (float32, metres), a flag per node for rotor nodes, the iron and coil triangles (uint32), the region kind per triangle (stator iron, rotor iron, shaft, coil A+ … D−, slot air, band), the phase of each coil.
- Per frame: rotor angle (rad), the air-gap band triangles at that angle (the only triangles `mesh_at_angle` changes), \|B\| per element (float32, T) and A per node (float32, Wb/m), ψ and torque at that point, solver status.
- The browser rotates the rotor nodes by the frame angle itself, so a frame carries no coordinates. A `screening` frame is about 0.7 MB, a `full` frame about 1.3 MB.

Frames are cached on disk under `<cache_dir>/fields/` as compressed `.npz`, keyed by the map provenance (§6.5) plus angle and coil current, so a repeated view is instant. The binary wire format is a small JSON header (array names, dtypes, shapes, offsets) followed by the raw little-endian arrays.

### 6.7 Drive waveforms and derived curves (v0b-2)

`Evaluation` gains `waveforms`: for each speed of the envelope grid, the chosen stroke resampled on 180 points of one rotor pole pitch: rotor angle, phase current i(θ), phase flux linkage ψ(θ), phase voltage v(θ) and phase torque T(θ). `srmapp.drive.envelope` already integrates these to pick the stroke; it keeps them instead of discarding them. From them, per speed:

- **line current**: the dc-link current, the sum over phases of each phase's converter input current (+i while the phase is energised from the bus, −i while it returns energy, 0 while freewheeling), with its mean and RMS;
- **power factor**: output power / (q · V_rms · I_rms), phase quantities, copper loss only until iron loss exists (labelled so).

Derived from the map, computed in `srmapp` and stored with the evaluation (`map_curves`):

- **L(θ)** secant inductance ψ/i per map current;
- **k2(i) = 1 − 1/(σs·σu) = 1 − Lu(i)/La_sat(i)**, with σs = La_sat(i)/La_unsat and σu = La_unsat/Lu(i), La_unsat the aligned secant inductance at 5 % of I_max (Krishnan ch. 3);
- **B_sp(i)**, the aligned stator-pole flux density: aligned ψ / (series turns per phase × stator pole face area), the face area being (bore diameter / 2) × stator pole arc × stack length;
- **B_sp·k2** against stator current and against La_sat/Lu (the output-equation factor; Krishnan's design curves).

All at the chosen winding (the turns rescale is exact); currents in A of that winding.

### 6.8 Design study (v0b-3)

`design_study(inputs, x, y, x_values, y_values, ...)`: a two-parameter grid (each axis at most 12 values, at most 100 designs) over dotted case-input paths, for example `design.machine.stator_pole_arc` × `design.machine.rotor_pole_arc`. Enclosure inputs (pole arc / pole pitch) are accepted and converted to arcs. Each design gets a cheap two-position evaluation instead of a full map and drive: aligned and unaligned ψ-i curves on 10 currents (20 solves; about 1–2 min on `screening`, a 6 × 5 grid about an hour), giving La, Lu, La/Lu, k2, B_sp·k2, the co-energy per stroke δW and the average torque q·P_r·δW / (2π) at the peak current. Designs the validator rejects (self-starting, fit) are reported per point and drawn as gaps. A study is one `study` job with SSE progress; its result is one table (x, y, every quantity) and no cases.

### 6.5 What triggers a new map

A map is a cache hit when its provenance is unchanged: geometry, materials, mesh preset, grids, solver, srmcore version and `i_map`. `i_map` comes from the largest ampere-turns any allowed winding carries, so it depends on geometry, wires, `phase_current_a`, `j_peak` and `j_peak_max`.

| Change | New map |
|---|---|
| winding (Fixed mode), turns, strands, paths | no |
| bus voltage, speeds, power, torque, mass limit | no |
| wire list, phase current, current-density caps | only if `i_map` changes |
| any dimension, pole set, material, preset | yes |

The UI shows this before Evaluate and Sweep ("no new map, seconds" or "1 new map, about 26 min"). The time per map is the mean wall time of the last five completed maps of the same preset on this server (stored with each job), so it adapts when the server changes; with no history it falls back to the M5e2 budget figures (`screening` 228 s, `full` 26 min for the 8/6 at 8 workers).

## 7. Frontend (`web/`)

### 7.1 Stack

React + Vite + TypeScript, shadcn/ui on Tailwind, TanStack Query (server state), TanStack Table (candidate and case tables), react-hook-form + zod (input tabs), Plotly (charts), Lucide (icons). Node is needed only to build; `srmweb` serves `web/dist`.

API types are generated from the OpenAPI schema with `openapi-typescript` into `web/src/api/schema.ts`; CI fails when it is stale.

### 7.2 Visual direction

Swiss minimal, dense dashboard. Light and dark, following the system setting, with a toggle. Tokens: primary navy `#1E3A5F`, secondary `#2563EB`, feasible `#059669`, error `#DC2626`, background `#F8FAFC` (light). Fira Sans for text, Fira Code for numbers. Semantic CSS variables only; no raw colours in components.

### 7.3 Navigation and pages

Bottom bar on phone (four items), sidebar on laptop: **New search · Runs · Cases · Settings**. Every run, candidate and case has its own URL; back works.

| Page | Content |
|---|---|
| New search | requirements form (power, torque, base and max speed, bus voltage, OD and mass limits, wire list, phase current, slot fill), search settings (candidates, shortlist, seed, materials, preset, margin), import/export of a search setup |
| Runs | job list with status, progress bar for the running job, resume, cancel, delete; empty state "No runs yet → Start a search" |
| Run | live progress (designs done / shortlist, map points done / total for the current design, elapsed time, a screen-reader status line); when done: sampled / dropped / stage-1 rejected counts, a 2D Pareto plot and the candidate table |
| Candidate | read-only motor diagram, key numbers, winding, ψ-i curves, torque map, torque-speed curve, winding scan, notes; **Open as case** (v0b-2) |
| Case (v0b-2) | inputs left: Requirement · Dimension · Material · Winding · Drive; outputs right: Motor diagram · Characteristics; actions Evaluate, Sweep (v0b-3), Validate, Export. On phone the panels stack with a segmented control Input / Diagram / Results. |
| Cases (v0b-2) | JMAG-style case table: flag, comment, "show in graphs" (overlay at most 6), key columns; filter by flag; delete |
| Settings | theme, units note, cache size and clear, version info |

Plots:

- **Pareto**: 2D scatter by default; X and Y selectable from mass, peak power, power density, efficiency at base speed, torque ratio; colour is the third objective; marker shape is the pole set; infeasible points grey and hollow; the Pareto front highlighted. A 3D toggle on laptop widths only. The candidate table is always beside or below.
- Case overlays use colour **and** line style (solid, dashed, dotted).

### 7.4 Cases (v0b-2)

- **Start**: from a search candidate, a reference design, or an imported setup file.
- **Edit**: every input change is debounced 300 ms, then `POST /validate` shows errors inline under the field (the engine's `InputError` names the parameter and the rule) plus a summary at the top, and `POST /geometry` redraws the motor diagram. Evaluate is disabled while errors remain. An edited case is marked stale until evaluated.
- **Evaluate** creates a **new case** (`parent_case_id` set) instead of overwriting, so the history stays (JMAG behaviour).
- **Winding tab**: a toggle **Auto** (turns scan) / **Fixed** (turns, strands, paths, wire).
- **Drive tab**: bus voltage and current limit editable; the conduction angles chosen per speed are shown read-only (the envelope optimises them).
- **Material tab**: library materials only, with grade and the resulting margin.
- **Preset**: `full` by default, `screening` selectable; every result shows its preset.
- **Validate** runs `em_validate` as a `validate` job (about 1 h) and shows the label, the checks and the uncertainty budget. It needs a `full` or `reference` map of an evaluated (not stale) case. It validates the reference-turns design and its cached map, since `em_validate` checks the map's design hash; the turns rescale is exact (v0a-2 spec §2), so the label carries over to the chosen winding.
- **Export**: the setup file (§7.6), the case map as CSV and MAT (`srmcore.maps.export`), and a run's candidate table as CSV.

### 7.5 Units and angles

SI inside. The UI shows mm, rpm, kW, N·m, V, A, A/mm², kg, mH, mWb and degrees; one conversion table in the frontend. Number inputs use `inputmode="decimal"`, a visible label, and the unit beside the field.

Conduction angles are shown in **electrical degrees with 0° at the unaligned position** (the JMAG convention), so they compare across pole sets (one electrical cycle is 360°/N_r mechanical). The conversion is done in `serialize.py`, from the rotor pole count and the engine's convention (phase A aligned at θ = 0), and is unit-tested. Mechanical degrees show in a tooltip.

### 7.6 Setup files

JSON with `schema` (`"srm-setup"`), `version` and one or more sections: `requirements`, `search`, `geometry`, `materials`, `winding`, `drive`.

- A whole setup creates a case. A search setup fills the New search page.
- Each case tab imports and exports its own section, so a winding can be loaded onto another geometry.
- Import validates against the same Pydantic models and reports errors per field; unknown keys are rejected.

### 7.7 Sweep (v0b-3)

One parameter, as **Range** (start, end, divisions) or **Table** (values). Any numeric input of the case may be swept, plus materials by table. At most 20 values. Before running, the page shows the number of new maps and the estimated time (§6.5). Each value becomes a case with origin `sweep`; the sweep result plots the key numbers against the swept value and overlays the cases' torque-speed curves.

**Design study** (§6.8): two parameters, Range or Table each. The result draws families of curves: a quantity against x with one line per y (for example average torque against stator pole enclosure for several rotor enclosures; La against the rotor-to-stator pole arc ratio for several stator enclosures), plus a heatmap of the same table. Axes can show arcs, enclosures or the arc ratio βr/βs.

### 7.8 UX rules

- Touch targets at least 44 px; contrast at least 4.5:1; visible focus; keyboard reachable; `prefers-reduced-motion` respected.
- Tables become stacked cards below 768 px.
- Loading skeletons only for waits above about 300 ms; long jobs show explicit progress.
- Tested at 375, 768, 1024 and 1440 px widths.

### 7.9 Field tab (v0b-2)

On every evaluated case. Phase A only, as in the map.

- **Snapshot**: rotor angle (slider, mechanical degrees with electrical degrees beside it; aligned and unaligned marked) and phase current (A, default the winding's peak current). **Show** calls `POST /field`; the UI says "about 10 s (mesh + one solve)" the first time and is instant from the cache after.
- **Layers** (toggles): mesh wireframe, \|B\| colour map (viridis, colour bar in T, the material's last B-H point marked on the bar), flux lines (contours of A, 20 levels, drawn in the browser), region outlines. Zoom and pan with wheel, pinch and drag; hover shows \|B\| and the region.
- **Animation**: **Animate stroke** submits an `animate` job: the rotor from unaligned to aligned at the chosen current, 36 frames by default (12–72), with progress over SSE like other jobs; the UI estimates "36 solves, about 2–3 min". When done the frames load once and play with play/pause, a frame slider and a speed control; ψ and torque of the current frame are shown beside the plot.
- **Rendering**: WebGL2 (one small module, no new chart library): one draw call for the triangles with a per-element colour, lines for the wireframe and flux contours. Phones with no WebGL2 get the snapshot as a static image drawn on a 2D canvas, without the animation.

Later, not in v0b-2: a drive animation with the commutated phase currents from the envelope at a chosen speed (needs current waveforms from `srmapp.drive`), and all phases excited together.

### 7.10 Analysis plots (v0b-2)

On the candidate page and every evaluated case, grouped in tabs. All vs rpm plots share the envelope's speed grid.

| Tab | Plots |
|---|---|
| Performance | torque, power, efficiency (copper only, labelled), phase RMS current, line current (mean and RMS), power factor (copper only) — all against rpm |
| Waveforms | at a chosen speed: phase current, flux linkage, voltage and torque against rotor angle (electrical degrees), the line current, and the ψ-i loop on top of the map's aligned and unaligned curves |
| Map | ψ against current per angle, torque against rotor angle per current, the torque heatmap, L(θ) per current |
| Design factors | La, Lu, La/Lu, k2 against current, B_sp against current, B_sp·k2 against current and against La_sat/Lu |
| Field | §7.9: flux plot with Aligned and Unaligned buttons, \|B\| distribution, flux lines, B(θ) waveform in the stator pole, stator yoke and rotor pole at the chosen current |

## 8. Security

Built in v0b-1:

1. **Refuse unsafe exposure.** If `SRMWEB_HOST` is not a loopback address and `SRMWEB_TOKEN` is unset, the server exits with a message saying so. To reach it from a phone on the same network: set `SRMWEB_HOST=0.0.0.0` and a token.
2. **Token login.** `POST /login` compares the token in constant time (`hmac.compare_digest`) and sets an HttpOnly, `SameSite=Strict` session cookie (a random session id held in memory; server restart logs out). Every `/api` route requires it, except `/login`. With a loopback host and no token, auth is off.
3. **Bounded inputs.** Request models use `extra="forbid"` and caps: `n_candidates` ≤ 2000, `shortlist` ≤ 200, sweep values ≤ 20, numeric ranges as in `Requirements` and the validator.
4. **No user-controlled paths or code.** Job and case ids are server-made UUIDs; SQL is parameterised; materials are chosen by library name; no `eval`; uploaded setup files are parsed as JSON into Pydantic models only.
5. **Queue cap** (`SRMWEB_QUEUE_MAX`).

Later, documented, not built: HTTPS (Tailscale or a reverse proxy such as Caddy; on a plain LAN the token travels in clear text) and multiple user accounts.

## 9. Documentation

FastAPI's built-in Swagger UI at `/api/docs` (behind auth), from the OpenAPI schema. No extra dependency; Scalar is a later swap if wanted.

## 10. Error handling

| Situation | Behaviour |
|---|---|
| invalid request | HTTP 422 with field paths; the page shows them inline |
| design rejected by the validator | field errors from `InputError` (parameter, rule) |
| one design fails inside a search | stored as a failed candidate (`Evaluation.status`), shown grey with its message |
| job raises | job `failed`, exception type and message stored and shown |
| server stops mid-job | job `interrupted`, **Resume** offered |
| map cancelled | job `cancelled`, partial search results kept |
| queue full | HTTP 429 |
| SSE drops | `EventSource` reconnects; the page re-reads the job |

## 11. Testing

- `srmapp`: waveforms integrate back to the envelope's torque and power at each speed (work per stroke); the line current's mean times the bus voltage equals the input power; power factor is 1 for a synthetic sinusoidal case; k2 equals 1 − Lu/La on a linear synthetic map; `design_study` reproduces La and Lu of `key_numbers` on the 8/6 and reports a self-starting violation as a gap.
- `srmapp`: `field_frames` on the 8/6 `screening` mesh: ψ and torque of a frame equal `solve_point` at the same angle and current; the band triangles plus the static triangles cover the mesh exactly; rotating the rotor nodes by the frame angle reproduces `mesh_at_angle`'s nodes; frame cache hit on a repeat.
- `srmapp`: `evaluate_design` Auto and Fixed on the existing small fixtures; Fixed with the Auto winding reproduces the Auto result; `sweep` validation per value; `MapArrays` matches the rescaled map; reference designs unchanged for tests.
- `srmweb` (pytest, FastAPI `TestClient`, fast suite): job lifecycle with a fake runner (submit, progress, SSE events, cancel, resume after `interrupted`, delete); store round trip; `to_json` for NaN, inf, ndarray and nested dataclasses; electrical-angle conversion on 6/4, 8/6, 12/8; auth (no token on loopback is open, non-loopback without token refuses to start, wrong token rejected, cookie flags); bounded inputs; setup-file import errors.
- One slow end-to-end test: a real `search` job on one small design with a tiny grid through the API.
- `web/`: Vitest for unit conversion, angle display, API client helpers, the binary frame decoder and the A-contour (marching triangles) on a small known field. CI gets a Node job: `npm ci`, schema freshness check, `npm run build`, `vitest`.
- Before each merge: a manual smoke test in the in-app browser at phone and laptop widths, light and dark.
- Before each merge: an architecture review with the `mattpocock-skills:codebase-design` skill (replaces `/code-review ultra` from the handoff).

## 12. Risks

| Risk | Handling |
|---|---|
| spawn pool from a worker thread under uvicorn misbehaves (Windows) | test first in v0b-1; fallback is a runner subprocess behind the same `JobRunner` interface |
| results JSON grows large (many candidates with scans and maps) | measure in v0b-1; store `MapArrays` as float32 lists if needed |
| plain-HTTP token on a LAN | documented; HTTPS later |
| field frames heavy on a phone (36 × 1.3 MB on `full`) | frames load once per animation and stay cached on the server; the snapshot is one frame; measure in v0b-2 and drop A (flux lines) to float16 if needed |
| engine numbers taken as validated | banner on every unvalidated result; Validate action shows the label |

## 13. Open items

- **Optimiser**: a later session researches methods (NSGA-II/III, Bayesian multi-objective such as qNEHVI, surrogate-assisted evolutionary methods and others), prototypes the best one or two on cheap synthetic maps, then writes its own spec. The case model and job runner are built so an `optimise` job kind slots in.
- Fixed conduction angles (needs a fixed-angle path in `srmapp.drive`).
- Custom B-H upload (needs `process_bh` checks and a grade decision).
- HTTPS and accounts; a systemd or Windows service when the server moves to the home Xeon.
