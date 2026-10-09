# v0b-2b: Drive Waveforms and Field Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the drive waveforms (phase current, flux linkage, voltage, torque, line current, power factor) of every evaluated case, and a Field tab that draws the |B| map and flux lines of the case at any rotor angle and current, with a stroke animation, all solved on a quick lane that does not wait behind a long search.

**Architecture:** `srmapp.drive.envelope` keeps the chosen stroke per speed (`Waveforms`) and derives the line current and power factor. `srmapp.field` builds the static mesh and one field frame per call, as plain arrays cached on disk. `srmweb` runs field work on a second lane: a thread inside `JobRunner` for `animate` jobs, and `QuickLane`, one spawn worker process that solves one frame at a time in arrival order. The browser decodes a small binary format and draws it with WebGL2 (a 2D canvas when WebGL2 is missing).

**Tech Stack:** Python 3.12+, numpy, scipy, FastAPI, stdlib `multiprocessing` (spawn `Pool`); React 19, TypeScript, Plotly (already installed), hand-written WebGL2; pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-08-v0b-web-design.md` (§2 v0b-2b row, §4.1, §4.3 quick lane, §6.6, §6.7, §7.9, §7.10, §11). Context: `CLAUDE.md` "Web layer (v0b)".

## Global Constraints

- The `srmcore` package version stays **0.4.0**. `srmweb.__version__`, the OpenAPI version and `web/package.json` go from 0.2.0 to **0.3.0** (Task 10).
- Layering (`tests/app/test_app_layering.py`): `srmapp` and `srmcore` never import `srmweb`. `srmweb` source must not import `gmsh`, `ngsolve`, `netgen` or `skfem` (importing `srmapp.field` is allowed).
- SI inside. The UI shows rpm, kW, N·m, V, A, mH, mWb, T and degrees (`web/src/lib/units.ts`).
- Electrical angles are degrees from the unaligned position: θ_el = (θ − π/N_r)·N_r (`srmweb.serialize.electrical_deg_from_unaligned`).
- Every result view keeps the existing "unvalidated, peak-only" `Banner`.
- Efficiency and power factor are labelled "copper loss only".
- Field work is phase A only, as in the map.
- UX: touch targets at least 44 px, contrast at least 4.5:1, visible focus, keyboard reachable, `prefers-reduced-motion` respected (no autoplay). Semantic CSS variables only in components; the viridis table and the plot line colours (`LINE_COLORS`) are data.
- No new npm or Python dependency.
- `web/src/api/schema.ts` is generated (`python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`); never edit it by hand.
- Test file basenames are unique. Fast tests are deterministic; tests that build a real mesh and solve with NGSolve, or spawn a process for more than a few seconds, are `@pytest.mark.slow`.
- Comments explain the code as it is, without task or plan history. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Rulings made while writing this plan

- **R1 waveform grid.** The waveforms use the envelope's own simulation grid without its last point: `n_theta − 1` samples (180 at the default `N_THETA = 181`) at θ_k = k·τ/(n_theta − 1), τ = 2π/N_r. Nothing is resampled, so the waveforms integrate back to the envelope. The dropped point is the periodic image of θ = 0.
- **R2 voltage and line current.** The phase voltage of interval k is the converter's average voltage over it: v_k = ω·(ψ_{k+1} − ψ_k)/Δθ + R·ī_k, with ī_k = (i_k + i_{k+1})/2. Each phase draws v_k·ī_k / V_bus from the bus. That is +i while the phase is energised, −i while it returns energy, 0 while freewheeling, and the duty-averaged value under the current limit. The line current is the sum over the q phases, each shifted by τ/q.
- **R3 search results stay small.** `search_result_json` leaves out `envelope.waveforms` (about 300 kB per evaluation). The per-speed line current and power factor stay in. The Waveforms tab shows on cases only.
- **R4 field API.** The field routes are case-scoped (`/api/cases/{id}/field`, `/field/mesh`, `/animate`) because they need an evaluated case's winding. `srmapp.field` exposes one frame per call (`field_frame`) instead of `field_frames(angles)`, so that a snapshot request can run between the frames of an animation.
- **R5 quick lane.** `QuickLane` uses `multiprocessing.get_context("spawn").Pool(1)`, because `Pool.terminate()` can stop a solve that times out. `animate` jobs run on a second lane thread inside `JobRunner`, so the job routes, SSE, cancel and resume work unchanged.
- **R6 B(θ) probes.** The probe value is the area-weighted mean |B| over three element zones, computed in `srmapp.field`: phase A's stator pole, the stator yoke behind it, and rotor pole 0.
- **R7 turns.** Field solves use the reference-turns design, which is the map's mesh and cache key, at coil current = phase current · k, with k = turns / (paths · REFERENCE_TURNS). The ψ reported to the UI is multiplied by k, so it is at the chosen winding.
- **R8 store.** No schema change. `results.kind` is free text, and `RESULT_KINDS` gains `"animate"`.

## Review Focus

1. **A snapshot asked for while an animation runs.** It runs between two frames and returns within 120 s. Test: Task 5, `test_request_runs_between_the_tasks_of_a_loop`.
2. **The cache was cleared after an animation.** `GET /jobs/{id}/frames` returns 410, and the Field tab says to animate again. Tests: Task 6, `test_frames_gone_after_cache_clear`, and Task 9's message.
3. **Speeds with no valid stroke** (fallback rows). The waveforms are all zero, the power factor is null, and the plots show gaps instead of crashing. Tests: Task 1, `test_no_stroke_rows_are_zero_with_nan_power_factor`, and Task 3, `waveformSeries` on a zero row.
4. **A phone without WebGL2.** The snapshot draws on a 2D canvas, and the animation controls are hidden with a note. Test: Task 8, `canRender` / fallback choice.
5. **A field solve that hangs.** The request gets 504, and the next request works on a fresh worker. Test: Task 5, `test_timeout_kills_the_worker_and_the_next_task_runs` (slow, spawn).

---

### Task 1: Stroke waveforms, line current and power factor in the envelope

**Files:**
- Modify: `src/srmapp/drive/envelope.py`
- Test: `tests/app/test_app_waveforms.py`

**Interfaces:**
- Produces:
  - `Waveforms` (frozen dataclass): `theta: np.ndarray` of shape (n,), mechanical rad, θ_k = k·τ/n; `current`, `psi`, `voltage`, `torque`, `line`, each of shape (n_speeds, n). Units are A, Wb-turns, V, N·m and A. `current`, `psi` and `torque` are phase A samples at θ_k. `voltage` is R2's v_k. `line` is the dc-link current of all phases.
  - `Envelope` gains `waveforms: Waveforms`, plus `line_mean`, `line_rms` and `power_factor`, each an `np.ndarray` of shape (n_speeds,).
  - `line_current(per_phase: np.ndarray, n_phases: int) -> np.ndarray`: per_phase has shape (..., n) over one period. It returns Σ_{j<q} per_phase shifted by j·n/q samples, using periodic linear interpolation when n/q is not an integer.
  - `power_factor(power: np.ndarray, voltage: np.ndarray, current: np.ndarray, n_phases: int) -> np.ndarray`: power / (q · rms(v) · rms(i)) along the last axis, NaN where the denominator is 0.

- [ ] **Step 1: Write the failing tests.** Use `_env` exactly as in `tests/app/test_app_envelope.py`: `envelope(synthetic_map(n_angles=24, **kw), make_8_6(), volts, r, SPEEDS)`, 4 phases.

```python
def test_waveform_shapes_and_grid():
    env = _env(r=0.5); w = env.waveforms
    assert w.theta.shape == (180,) and w.theta[0] == 0.0
    assert w.theta[1] == pytest.approx(PERIOD / 180)
    for name in ("current", "psi", "voltage", "torque", "line"):
        assert getattr(w, name).shape == (len(SPEEDS), 180), name

def test_waveforms_integrate_back_to_the_envelope():
    env = _env(r=0.5); w = env.waveforms
    np.testing.assert_allclose(4 * w.torque.mean(axis=1), env.torque, rtol=1e-3, atol=1e-9)
    np.testing.assert_allclose(4 * 0.5 * (w.current**2).mean(axis=1), env.copper_loss, rtol=1e-3, atol=1e-9)
    np.testing.assert_allclose(np.sqrt((w.current**2).mean(axis=1)), env.i_rms, rtol=1e-3, atol=1e-9)

def test_line_current_mean_times_bus_voltage_is_the_input_power():
    env = _env(r=0.5); ok = env.torque > 0
    np.testing.assert_allclose(env.line_mean[ok] * 400.0, (env.power + env.copper_loss)[ok], rtol=0.05)
    np.testing.assert_allclose(env.line_mean, env.waveforms.line.mean(axis=1))
    np.testing.assert_allclose(env.line_rms, np.sqrt((env.waveforms.line**2).mean(axis=1)))

def test_line_current_of_one_phase_is_its_bus_current():
    p = np.sin(np.linspace(0, 2 * np.pi, 180, endpoint=False))
    np.testing.assert_allclose(line_current(p, 1), p)

def test_line_current_sums_shifted_phases_for_any_phase_count():
    rng = np.random.default_rng(0); p = rng.random(180)
    for q in (3, 4, 7):                     # 180 / 7 is not an integer: interpolated shift
        out = line_current(p, q)
        assert out.mean() == pytest.approx(q * p.mean(), rel=1e-12)
    np.testing.assert_allclose(line_current(p, 4), sum(np.roll(p, 45 * j) for j in range(4)))

def test_power_factor_is_one_for_in_phase_sinusoids():
    v = 10 * np.sin(np.linspace(0, 2 * np.pi, 180, endpoint=False)); i = 2 * v / 10
    power = np.array([3 * np.mean(v * i)])
    assert power_factor(power, v[None], i[None], 3)[0] == pytest.approx(1.0, rel=1e-12)

def test_envelope_power_factor_is_output_over_phase_volt_amperes():
    env = _env(r=0.5); w = env.waveforms; ok = env.torque > 0
    rms = lambda x: np.sqrt((x**2).mean(axis=1))
    np.testing.assert_allclose(env.power_factor[ok], (env.power / (4 * rms(w.voltage) * rms(w.current)))[ok])
    assert np.all((env.power_factor[ok] > 0) & (env.power_factor[ok] <= 1))

def test_no_stroke_rows_are_zero_with_nan_power_factor():
    env = _env(volts=0.5, l1=0.0)
    for name in ("current", "psi", "voltage", "torque", "line"):
        assert np.all(getattr(env.waveforms, name) == 0), name
    assert np.all(np.isnan(env.power_factor)) and np.all(env.line_mean == 0)
```

- [ ] **Step 2: Run them and confirm they fail.** Run: `python -m pytest tests/app/test_app_waveforms.py -v`. Expected: FAIL (ImportError on `line_current`).
- [ ] **Step 3: Implement.** Give `_simulate` a `trace: bool = False` argument. When it is true, it also returns ψ and i at every grid point, shape (n_theta, n_pairs), using the same arithmetic. After `best` is picked for a speed, call `_simulate` again with `on[[best]], off[[best]], trace=True`. Build the samples k = 0..n_theta−2: T_k = `np.interp(i_k, t.current, t.torque[k])`, and v_k and ī_k as in R2. The phase bus current is v_k·ī_k/V. `line = line_current(bus, q)`. A fallback row (no valid stroke) gets zeros. `power_factor` uses `env.power`. Keep the `Envelope` docstring current. The scan in `choose_turns` calls `envelope` per winding, and the extra single-pair run per speed is cheap, so no switch is added.
- [ ] **Step 4: Run the tests and confirm they pass.** Run: `python -m pytest tests/app/test_app_waveforms.py tests/app/test_app_envelope.py tests/app/test_app_turns.py tests/app/test_app_evaluate.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(srmapp): stroke waveforms, line current and power factor in the envelope"`

### Task 2: Waveforms in the evaluation JSON and response models

**Files:**
- Modify: `src/srmweb/serialize.py`, `src/srmweb/results.py`, `web/openapi.json`, `web/src/api/schema.ts` (generated), `web/src/api/types.ts`
- Test: `tests/web/test_web_serialize.py`, `tests/web/test_web_results.py`

**Interfaces:**
- Consumes: Task 1 `Envelope.waveforms`, `line_mean`, `line_rms`, `power_factor`.
- Produces:
  - `evaluation_json(ev, *, waveforms: bool = True) -> dict`. With `waveforms=False`, `envelope.waveforms` is left out. With `True`, it gains `theta_el` (electrical degrees from unaligned, one per sample).
  - `search_result_json` calls it with `waveforms=False`.
  - `EnvelopeOut` gains `line_mean: Vec`, `line_rms: Vec`, `power_factor: Vec` and `waveforms: WaveformsOut | None = None`.
  - `WaveformsOut(theta: Vec, theta_el: Vec, current: Mat, psi: Mat, voltage: Mat, torque: Mat, line: Mat)`.
  - TS: `types.ts` exports `Waveforms = components["schemas"]["WaveformsOut"]`.

- [ ] **Step 1: Write the failing tests.**
  - `test_evaluation_json_has_waveforms_with_electrical_angles`: on an evaluation built the way the existing serialize tests build one, with an 8/6 synthetic envelope, `out["envelope"]["waveforms"]["theta_el"][0] == pytest.approx(-180.0)`. Its length is 180, and each row of `line` has length 180.
  - `test_search_result_json_leaves_out_waveforms`: `"waveforms" not in r["evaluations"][0]["envelope"]`, while `"power_factor"` is in it.
  - `test_evaluation_out_parses_waveforms`: `EvaluationOut.model_validate(evaluation_json(ev)).envelope.waveforms.theta_el[0] == pytest.approx(-180.0)`. A fallback row's power factor (NaN) arrives as `None`.
- [ ] **Step 2: Run them and confirm they fail.** Run: `python -m pytest tests/web/test_web_serialize.py tests/web/test_web_results.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the `serialize.py` and `results.py` changes above, then regenerate `web/openapi.json` and `schema.ts`, and add the `Waveforms` export.
- [ ] **Step 4: Run the tests and the type check.** Run: `python -m pytest tests/web -m "not slow" -q`, then `cd web; npx tsc -b`. Expected: PASS, no type errors.
- [ ] **Step 5: Commit.** `git commit -m "feat(srmweb): waveforms, line current and power factor in evaluation responses"`

### Task 3: Performance additions and the Waveforms tab

**Files:**
- Modify: `web/src/lib/analysis.ts`, `web/src/components/analysis/PerformanceTab.tsx`, `web/src/components/analysis/AnalysisTabs.tsx`, `web/src/pages/CasePage.tsx`
- Create: `web/src/lib/waveforms.ts`, `web/src/components/analysis/WaveformsTab.tsx`
- Test: `web/src/lib/analysis.test.ts`, `web/src/lib/waveforms.test.ts`

**Interfaces:**
- Consumes: Task 2 `EnvelopeOut.line_mean | line_rms | power_factor | waveforms`, and `MapCurves.la_sat`, `lu`, `currents`.
- Produces:
  - `PerformanceSeries` gains `lineCurrent: Trace[]` and `powerFactor: Trace[]`. `lineCurrent` has two traces per case: mean (circle markers) and RMS (square markers), named `"mean"`/`"RMS"` for one case and `"<label> mean"`/`"<label> RMS"` when overlays exist. `powerFactor` has one trace per case.
  - `waveformSeries(ev: Evaluation, speed: number): WaveformSeries | null`, with `{ current, psi, voltage, torque, line, loop: Trace[] }`. x is `theta_el` for all but `loop`. `loop` has the stroke's ψ (mWb) against i (A), plus `"aligned"` (la_sat·i) and `"unaligned"` (lu·i) from the curves, each starting at (0, 0). It returns null without waveforms.
  - `defaultSpeedIndex(ev: Evaluation, baseSpeedRpm?: number): number`: the speed nearest the base speed, else the index of the largest power.
  - `AnalysisTabs` gains props `baseSpeedRpm?: number` and `caseId?: string` (`caseId` is used by Task 8). A "Waveforms" tab shows only when `evaluation.envelope?.waveforms` exists.

- [ ] **Step 1: Write the failing Vitest tests.**
  - `performanceSeries` on a two-case fixture: `lineCurrent` has 4 traces named `"this case mean"`, `"this case RMS"`, …. `powerFactor[0].y` equals `envelope.power_factor`.
  - `waveformSeries(ev, 1).current[0].y` equals row 1 of `waveforms.current`, and x equals `theta_el`.
  - `loop` has 3 traces. The aligned trace's first point is (0, 0), and its y values in mWb equal la_sat·i·1e3.
  - A zero row gives all-zero y and does not throw.
  - `defaultSpeedIndex` with base 1500 on speeds `[100, 1500, 3000]` is 1. With no base speed it is the argmax of power.
- [ ] **Step 2: Run them and confirm they fail.** Run: `cd web; npx vitest run src/lib/waveforms.test.ts src/lib/analysis.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - PerformanceTab adds "Line current (A)" and "Power factor" plots. The note reads "Efficiency and power factor count copper loss only."
  - WaveformsTab has a labelled speed `<select>` (options "1500 rpm", min-h-11). It shows five LinePlots (phase current, flux linkage in mWb, phase voltage, phase torque, line current) against "Rotor angle (° electrical, 0 = unaligned)", plus the ψ-i loop plot.
  - Add a caption: "Phase A over one rotor pole pitch; line current sums all phases. Peak-only drive model."
  - CasePage passes `baseSpeedRpm={data.inputs.requirements?.base_speed_rpm}` and `caseId={data.id}`.
- [ ] **Step 4: Run tests, the build and the full web suite.** Run: `cd web; npx vitest run; npm run build`. Expected: PASS, clean build.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): line current, power factor and the Waveforms tab"`

### Task 4: Field mesh and field frames in `srmapp.field`

**Files:**
- Create: `src/srmapp/field.py`
- Test: `tests/app/test_app_field.py`

**Interfaces:**
- Consumes: `srmcore.mesh.build_machine_mesh`, `mesh_at_angle`, `srmcore.maps.point.solve_point`, `srmcore.maps.dataset.provenance` / `provenance_hash`, `srmcore.solvers.factory.make_solver`, `srmcore.materials.library.library_law` (`.bn` is the last stacked B-H point).
- Produces:
  - `RegionInfo` (frozen dataclass): `name: str`, `kind: str`, `part: str`, `phase: str | None`, `sign: int | None`.
  - `FieldMesh` (frozen dataclass), with the rotor at angle 0:
    - `nodes` (n, 2) float64, m: stator nodes, then rotor nodes;
    - `n_stator_nodes: int`;
    - `triangles` (m, 3) int64: stator part, then rotor part offset by `n_stator_nodes`, which is `mesh_at_angle`'s order without the band;
    - `region` (m,) int64, an index into `regions`;
    - `regions: tuple[RegionInfo, ...]` from the static mesh's names, kinds, parts and coils;
    - `b_last: float` (T), the smaller of the stator and rotor materials' `bn`;
    - `probes: dict[str, np.ndarray]`, element indices for `"stator_pole"`, `"stator_yoke"` and `"rotor_pole"`.
  - `FieldFrame` (frozen dataclass): `angle: float` (mechanical rad), `coil_current: float` (A at the design's turns), `band` (k, 3) int64, `b` (m + k,) float32 |B| in T in `mesh_at_angle`'s element order, `a` (n,) float32 A_z in Wb/m, `psi: float` (phase A, design turns), `torque: float` (Arkkio, N·m), `status: str` (the `SolveStatus` value), `probes: dict[str, float]` (area-weighted mean |B| per zone).
  - `field_key(design: Design, solver: str) -> str`, which is `provenance_hash(provenance(design, [], [], "A", make_solver(solver)))`.
  - `field_mesh(design: Design, *, solver: str = "ngsolve", cache_dir=None) -> FieldMesh`.
  - `field_frame(design: Design, angle: float, coil_current: float, *, solver: str = "ngsolve", cache_dir=None) -> FieldFrame`.
  - `cached_frame(design, angle, coil_current, *, solver="ngsolve", cache_dir) -> FieldFrame | None`, which reads the cache only, never solves.
  - `rotated_nodes(mesh: FieldMesh, angle: float) -> np.ndarray`, the rotor nodes rotated counter-clockwise by `angle` (the browser does the same).
  - Cache files: `<cache_dir>/fields/mesh_<key>.npz` and `<cache_dir>/fields/frame_<sha256(f"{key}|{angle!r}|{coil_current!r}")[:16]>.npz`, compressed, written to a temporary name and then `os.replace`d.

- [ ] **Step 1: Write the failing tests.** Use `DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))` and `SOLVER = "skfem_reference"` throughout. A module-scope fixture builds `field_mesh` once in a `tmp_path_factory` directory.

```python
def test_frame_matches_solve_point(cache):
    theta = math.radians(10.0)
    f = field_frame(DESIGN, theta, 5.0, solver=SOLVER, cache_dir=cache)
    p = solve_point(build_machine_mesh(DESIGN), DESIGN, theta, {"A": 5.0}, SkfemReference())
    assert f.psi == pytest.approx(p.psi[0], rel=1e-9) and f.torque == pytest.approx(p.torque_arkkio, rel=1e-9)
    assert f.status == "OK"

def test_band_and_static_triangles_are_the_mesh(cache, mesh):
    theta = math.radians(10.0)
    f = field_frame(DESIGN, theta, 5.0, solver=SOLVER, cache_dir=cache)
    mm = mesh_at_angle(build_machine_mesh(DESIGN), theta)
    assert np.array_equal(np.vstack([mesh.triangles, f.band]), mm.triangles)
    assert f.b.shape == (len(mm.triangles),) and f.a.shape == (len(mm.nodes),)

def test_rotating_the_rotor_nodes_reproduces_the_mesh_nodes(mesh):
    theta = math.radians(10.0)
    mm = mesh_at_angle(build_machine_mesh(DESIGN), theta)
    np.testing.assert_allclose(rotated_nodes(mesh, theta), mm.nodes, atol=1e-12)

def test_frames_and_mesh_come_from_the_cache_on_repeat(cache, monkeypatch):
    first = field_frame(DESIGN, 0.3, 4.0, solver=SOLVER, cache_dir=cache)
    monkeypatch.setattr("srmapp.field.solve_point", _boom)
    monkeypatch.setattr("srmapp.field.build_machine_mesh", _boom)
    again = field_frame(DESIGN, 0.3, 4.0, solver=SOLVER, cache_dir=cache)
    assert np.array_equal(first.b, again.b) and again.psi == first.psi
    assert cached_frame(DESIGN, 0.3, 4.0, solver=SOLVER, cache_dir=cache).torque == first.torque
    assert cached_frame(DESIGN, 0.31, 4.0, solver=SOLVER, cache_dir=cache) is None
    field_mesh(DESIGN, solver=SOLVER, cache_dir=cache)          # served from disk

def test_probe_zones(mesh, cache):
    m = DESIGN.machine
    zones = [set(mesh.probes[z]) for z in ("stator_pole", "stator_yoke", "rotor_pole")]
    assert all(zones) and not (zones[0] & zones[1]) and not (zones[0] & zones[2])
    aligned = field_frame(DESIGN, 0.0, 5.0, solver=SOLVER, cache_dir=cache)
    unaligned = field_frame(DESIGN, math.pi / m.n_rotor_poles, 5.0, solver=SOLVER, cache_dir=cache)
    for z in ("stator_pole", "rotor_pole"):
        assert aligned.probes[z] > 2 * unaligned.probes[z], z
```

- [ ] **Step 2: Run them and confirm they fail.** Run: `python -m pytest tests/app/test_app_field.py -v`. Expected: FAIL (no module).
- [ ] **Step 3: Implement `src/srmapp/field.py`.**
  - Keep a process-local `functools.lru_cache(maxsize=2)` on a `_static(design_json: str) -> StaticMesh`, so that a worker process meshes a design once. `field_frame` calls `solve_point(..., keep_field=True)` with `{"A": coil_current}` and `make_solver(solver, threads=1)`.
  - Probe zones use element centroids at angle 0:
    - `stator_pole`: kind `stator_iron`, `bore_radius ≤ r < stator_yoke_inner_radius`, |φ| ≤ stator_pole_arc/2 (phase A's pole is on the x axis; phase A is aligned at θ = 0).
    - `stator_yoke`: kind `stator_iron`, `r ≥ stator_yoke_inner_radius`, |φ| ≤ stator_pole_arc/2.
    - `rotor_pole`: kind `rotor_iron`, `r > rotor_yoke_outer_radius`, |φ| ≤ rotor_pole_arc/2 in the rotor frame.
  - Each probe value is Σ|B|·area / Σarea over the zone.
  - Store `b` and `a` as float32.
- [ ] **Step 4: Run the tests and the layering check.** Run: `python -m pytest tests/app/test_app_field.py tests/app/test_app_layering.py -v`. Expected: PASS. If the field tests take more than about 60 s, mark the slowest `@pytest.mark.slow` and say so in the report.
- [ ] **Step 5: Commit.** `git commit -m "feat(srmapp): field mesh, field frames, B probes and their disk cache"`

### Task 5: Quick lane, binary frames and the snapshot routes

**Files:**
- Create: `src/srmweb/quick.py`, `src/srmweb/frames.py`
- Modify: `src/srmweb/jobs.py` (`JobRunner` owns a `QuickLane`), `src/srmweb/api.py`, `src/srmweb/schemas.py`
- Test: `tests/web/test_web_quick.py`, `tests/web/test_web_frames.py`, `tests/web/test_web_field_routes.py`

**Interfaces:**
- Consumes: Task 4 `field_mesh`, `field_frame`, `FieldMesh`, `FieldFrame`; `srmapp.sizing.generator.REFERENCE_TURNS`; `srmapp.case.reference_design`.
- Produces:
  - `quick.LaneTimeout(Exception)`.
  - `quick.QuickLane(timeout_s: float = 120.0, spawn: bool = True)`, with methods:
    - `run(fn, *args, timeout: float | None = None) -> Any`: FIFO with one task at a time. It blocks the caller. It raises `LaneTimeout` once `timeout` (default `timeout_s`) has passed since the call, whether the task is still queued or already running; a timed-out queued task never runs. It re-raises the task's exception.
    - `busy() -> bool`.
    - `stop() -> None`.
  - With `spawn=True`, tasks run in a lazily created `multiprocessing.get_context("spawn").Pool(1, initializer=_init_lane)`. `_init_lane` sets `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and `MKL_NUM_THREADS` to `"1"`. A timeout of a running task calls `pool.terminate()`, and the next task makes a new pool. With `spawn=False`, tasks run in the lane thread (tests). `quick.py` imports only the stdlib at module level.
  - `frames.pack(meta: dict, arrays: dict[str, np.ndarray]) -> bytes`. Layout: a uint32 little-endian header length H, then a UTF-8 JSON header `{"meta": …, "arrays": [{"name", "dtype", "shape", "offset"}]}` padded with spaces so that 4 + H is a multiple of 8, then each array little-endian at `offset` bytes from the start of the data section. Every offset is a multiple of 8. Allowed dtypes are `"float32"`, `"uint32"` and `"uint8"`.
  - `JobRunner.__init__(store, settings, run_fn=None, quick: QuickLane | None = None)`: `self.quick` is the lane (default `QuickLane()`). `stop()` also stops it.
  - `FieldIn(angle: float = Field(ge=0, lt=2π), current_a: float = Field(gt=0))`, `extra="forbid"`.
  - `GET /api/cases/{id}/field/mesh` → `application/octet-stream`.
    - Meta: `n_stator_nodes`, `regions` (list of RegionInfo dicts), `b_last`, `n_rotor_poles`, `aligned_angle`, `unaligned_angle` (from `evaluation.key`), `winding_current` (`evaluation.winding.current`), `i_max` (`evaluation.key.i_max`).
    - Arrays: `nodes` float32 (n, 2), `triangles` uint32 (m, 3), `region` uint8 (m,), `probe.stator_pole`, `probe.stator_yoke`, `probe.rotor_pole` uint32.
  - `POST /api/cases/{id}/field` (body `FieldIn`) → `application/octet-stream`.
    - Meta: `angle`, `current_a`, `psi` (× k, chosen winding), `torque`, `status`, `probes`.
    - Arrays: `band` uint32, `b` float32, `a` float32.
  - `field_context(case_id: str) -> FieldContext` is a helper inside `create_app`, used by these routes and by Task 6. `FieldContext(design: Design, inputs: CaseInputs, k: float, i_max: float, winding_current: float)` is a frozen dataclass in `srmweb/frames.py`. The helper raises the 409 below.
  - Rules for both routes:
    - The case must be evaluated (not stale) with an `ok` evaluation that has a winding; otherwise 409 "evaluate this case first".
    - `current_a > 2 · key.i_max` gives 422 "current above twice the map's top current".
    - `LaneTimeout` gives 504 "the field solve took longer than 120 s".
    - Any other task exception gives 500 with detail `"<Type>: <message>"`.
    - The design is `reference_design(inputs)`, and the coil current is current_a · k (R7).

- [ ] **Step 1: Write the failing tests.**
  - `test_web_quick.py`:
    - `test_tasks_run_in_arrival_order` (inline: three threads submit `record` tasks; the recorded order equals the submit order).
    - `test_task_exception_reaches_the_caller`.
    - `test_queued_task_times_out_and_never_runs` (inline: the first task waits on an Event; the second, with `timeout=0.2`, raises `LaneTimeout`; after the Event is set the second task's side effect never happens).
    - `test_request_runs_between_the_tasks_of_a_loop` (inline: thread L runs 3 tasks in a loop, each gated by an Event; a run submitted after L's first task starts is recorded between L1 and L2).
    - `@pytest.mark.slow test_timeout_kills_the_worker_and_the_next_task_runs` (spawn: `run(time.sleep, 30, timeout=3)` raises `LaneTimeout` in under 10 s; then `run(math.sqrt, 4.0, timeout=60) == 2.0`).
  - `test_web_frames.py`: round trip through a test-local `unpack` (`np.frombuffer` with the header). `meta` survives. Arrays are equal with their dtypes and shapes. Every `offset % 8 == 0`, and `(4 + H) % 8 == 0`. An unsupported dtype raises `ValueError`.
  - `test_web_field_routes.py`: a TestClient with `JobRunner(store, s, run_fn=…, quick=QuickLane(spawn=False))`, and `srmapp.field.field_mesh`/`field_frame` monkeypatched to fakes that record their arguments. Cases are seeded through the store with an `ok` evaluation (winding turns 40, paths 2, current 10, key.i_max 12; REFERENCE_TURNS from the module).
    - The snapshot passes coil current = 3.0 · 40 / (2 · REFERENCE_TURNS) and returns ψ multiplied by the same k.
    - Content type `application/octet-stream`.
    - A stale case and a failed evaluation both give 409.
    - current_a = 25 gives 422; angle 7.0 gives 422.
    - A fake raising `LaneTimeout` gives 504.
    - A fake raising `RuntimeError("x")` gives 500 with "RuntimeError: x".
- [ ] **Step 2: Run them and confirm they fail.** Run: `python -m pytest tests/web/test_web_quick.py tests/web/test_web_frames.py tests/web/test_web_field_routes.py -m "not slow" -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `quick.py`, `frames.py`, the routes and `JobRunner.quick` as specified. Route handlers are sync `def`, so that waiting on the lane does not block the event loop.
- [ ] **Step 4: Run the tests and the full fast web suite.** Run: `python -m pytest tests/web tests/app/test_app_layering.py -m "not slow" -q`, then the slow lane test alone: `python -m pytest tests/web/test_web_quick.py -m slow -v`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(srmweb): quick lane, binary field frames and the snapshot routes"`

### Task 6: `animate` jobs on the quick lane

**Files:**
- Modify: `src/srmweb/jobs.py`, `src/srmweb/store.py` (`RESULT_KINDS`), `src/srmweb/schemas.py`, `src/srmweb/api.py`
- Test: `tests/web/test_web_animate.py`, `tests/web/test_web_jobs.py`

**Interfaces:**
- Consumes: Task 5 `QuickLane`, `frames.pack`, the field context helper, and the 409/422 rules; Task 4 `field_frame`, `cached_frame`.
- Produces:
  - `JobRunner` gets two lanes, each with its own deque, running slot and thread: `"main"` (search, evaluate, validate) and `"quick"` (`animate`), from `LANE_OF = {"animate": "quick"}` (other kinds are main).
    - `submit`, `cancel` and `progress` work for both.
    - `queue_max` is per lane.
    - `start()` re-queues each lane's own queued jobs.
    - `busy(lane: str = "main") -> bool`.
  - Job functions take `(req, reporter, ctx: JobContext)`, with `JobContext(settings: Settings, quick: QuickLane)` a frozen dataclass. The three existing functions change only their signature.
  - `AnimateRequest(case_id: str, inputs: CaseInputs, current_a: float > 0, coil_current: float > 0, k: float > 0, frames: int = Field(36, ge=12, le=72))`, `extra="forbid"`.
  - `run_animate_job`:
    - Angles are `np.linspace(π/N_r, 2π/N_r, frames)` (phase A unaligned to aligned).
    - Before each frame it checks `reporter.cancelled()` and returns `{"cancelled": True}` if set.
    - Each frame is `ctx.quick.run(field_frame, design, angle, coil_current, ...)` with `cache_dir` set.
    - Progress: `points_done`/`points_total` = frames, message `"frame n/N"`.
    - Result: `{case_id, current_a, angles, psi: [ψ·k], torque, status, probes: {zone: [..]}}`.
  - `RESULT_KINDS` gains `"animate"`.
  - `AnimateIn(current_a: float > 0, frames: int = 36, 12..72)`.
  - `POST /api/cases/{id}/animate` → 201 `{job_id}`, with the same 409/422 rules as `/field` and 429 when the quick queue is full.
  - `GET /api/jobs/{id}/frames`:
    - 404 unless it is an `animate` job with a stored result.
    - 410 "the frames were cleared; animate again" when any `cached_frame` is None.
    - Otherwise `application/octet-stream` with meta = the result body and arrays `band.<n>`, `b.<n>`, `a.<n>` per frame.
  - Cache size and clear:
    - `GET /settings/cache` counts `*.h5` plus `fields/*.npz` (files and bytes).
    - `DELETE /settings/cache` removes both, and returns 409 while either lane is busy.

- [ ] **Step 1: Write the failing tests.**
  - In `test_web_animate.py`, using the quick lane with `spawn=False` and a fake `field_frame` that returns a fixed small frame:
    - Animate a seeded case with `frames=12`: the job ends `done`, `progress.points_total == 12`, and the stored result has 12 angles from π/6 to π/3 on the 8/6 and ψ multiplied by k.
    - `test_frames_route_packs_every_frame`: the arrays are named `band.0` … `a.11`.
    - `test_frames_gone_after_cache_clear`: after `DELETE /settings/cache` (with the fake writing nothing, `cached_frame` is monkeypatched to return None), the route gives 410.
    - `frames=8` gives 422.
    - A stale case gives 409.
    - Cancel during the job ends it `cancelled` with no result.
    - Resume of the cancelled job runs again.
  - In `test_web_jobs.py`:
    - `test_quick_job_runs_while_a_main_job_runs`: a main job blocks on an Event, and an animate job submitted afterwards reaches `done` first.
    - `test_queue_cap_is_per_lane`.
    - `test_start_requeues_each_lane`.
- [ ] **Step 2: Run them and confirm they fail.** Run: `python -m pytest tests/web/test_web_animate.py tests/web/test_web_jobs.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** as specified. Update the `jobs.py` module docstring to say "one thread per lane".
- [ ] **Step 4: Run the tests.** Run: `python -m pytest tests/web -m "not slow" -q`, then regenerate the OpenAPI/schema and run `cd web; npx tsc -b`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(srmweb): animate jobs on the quick lane and the frames route"`

### Task 7: Field data libraries for the browser

**Files:**
- Create: `web/src/lib/fieldWire.ts`, `web/src/lib/contours.ts`, `web/src/lib/viridis.ts`, `web/src/lib/fieldView.ts`
- Test: `web/src/lib/fieldWire.test.ts`, `web/src/lib/contours.test.ts`, `web/src/lib/viridis.test.ts`, `web/src/lib/fieldView.test.ts`

**Interfaces:**
- Consumes: Task 5's wire format and the mesh/frame meta and array names; Task 6's frames names.
- Produces:
  - `decode(buf: ArrayBuffer): { meta: any; arrays: Record<string, { data: Float32Array | Uint32Array | Uint8Array; shape: number[] }> }`. It copies each array out, so alignment never throws.
  - `FieldMeshData` (`nodes`, `nStatorNodes`, `triangles`, `region`, `regions`, `bLast`, `probes`, `nRotorPoles`, `alignedAngle`, `unalignedAngle`, `windingCurrent`, `iMax`) and `FieldFrameData` (`angle`, `currentA`, `psi`, `torque`, `status`, `probes`, `band`, `b`, `a`).
  - `meshFromWire(buf)`, `frameFromWire(buf)`, `framesFromWire(buf): { meta; frames: FieldFrameData[] }`.
  - `contourLevels(values: Float32Array, n = 20): number[]`: n levels evenly spaced strictly inside (min, max); empty when min == max.
  - `contourSegments(xy: Float32Array, tris: Uint32Array, values: Float32Array, levels: number[]): Float32Array` (marching triangles on P1 values). It returns x0, y0, x1, y1 per segment. A level equal to a vertex value counts as above (`>=`), so no triangle yields a degenerate double segment.
  - `viridis(t: number): [number, number, number]` for t clamped to [0, 1], in 0..255, using matplotlib's viridis interpolated from at least 16 stops. `viridis(0)` = [68, 1, 84] and `viridis(1)` = [253, 231, 37], each ±1.
  - `positions(mesh, angle): Float32Array`: rotor nodes (index ≥ nStatorNodes) rotated counter-clockwise by `angle`.
  - `allTriangles(mesh, frame): Uint32Array`: static triangles followed by the band.
  - `pickTriangle(xy, tris, x, y): number`: −1 when none; barycentric test.
  - `regionEdges(tris, region): Uint32Array`: node pairs of edges whose two triangles differ in region, plus boundary edges.
  - `electricalDeg(angle, nRotorPoles): number`.
  - `animateEstimate(n: number): string`: `"${n} solves, about ${lo}–${hi} min"` with lo = max(1, round(n·3/60)) and hi = max(1, round(n·5/60)), or `"about ${lo} min"` when lo == hi. `animateEstimate(36)` = "36 solves, about 2–3 min".

- [ ] **Step 1: Write the failing tests.**
  - `decode` of a hand-built buffer (a header with a float32 (2, 2) array and a uint8 (3,) array at 8-aligned offsets) gives the exact values.
  - `contourSegments` on two triangles forming the unit square, with values = x and level 0.5, gives segments that all lie on x = 0.5 and join (0.5, 0) to (0.5, 1).
  - A level outside the value range gives an empty array.
  - `contourLevels([0, 1], 4)` = [0.2, 0.4, 0.6, 0.8].
  - The viridis endpoints, and `viridis(-1)` equals `viridis(0)`.
  - `positions` with angle π/2 maps rotor node (1, 0) to (0, 1) and leaves stator nodes unchanged.
  - `pickTriangle` inside, outside and on an edge.
  - `regionEdges` on two triangles of different regions includes the shared edge.
  - `electricalDeg(0, 6) = -180`.
  - `animateEstimate(36)` and `animateEstimate(12)` = "12 solves, about 1 min".
- [ ] **Step 2: Run them and confirm they fail.** Run: `cd web; npx vitest run src/lib/fieldWire.test.ts src/lib/contours.test.ts src/lib/viridis.test.ts src/lib/fieldView.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** the four modules (no DOM, no React).
- [ ] **Step 4: Run the tests and confirm they pass.** Run: `cd web; npx vitest run`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): field wire decoder, flux contours, viridis and view helpers"`

### Task 8: Field tab with snapshots (WebGL2, 2D fallback)

**Files:**
- Create: `web/src/components/field/FieldCanvas.tsx`, `web/src/components/field/ColorBar.tsx`, `web/src/components/analysis/FieldTab.tsx`, `web/src/api/field.ts`, `web/src/lib/fieldGl.ts`
- Modify: `web/src/components/analysis/AnalysisTabs.tsx`
- Test: `web/src/lib/fieldGl.test.ts`

**Interfaces:**
- Consumes: Task 7 libraries; Task 5 routes; `AnalysisTabs` `caseId`.
- Produces:
  - `useFieldMesh(caseId)`: a TanStack query on `GET /api/cases/{id}/field/mesh` (`staleTime: Infinity`, `arrayBuffer` → `meshFromWire`).
  - `useFieldSnapshot()`: a mutation on `POST /api/cases/{id}/field` → `frameFromWire`. Both send the session cookie like `api()`. Errors read the JSON `detail`.
  - `canRender(): "webgl2" | "canvas2d"`.
  - `FieldCanvas({ mesh, frame, layers, onHover })`, with `layers = { bmap, flux, mesh: wire, outlines }`.
  - `fieldGl.ts` holds the WebGL2 program and buffers:
    - triangles expanded to 3 vertices each, with a flat per-element colour from `viridis(b / bMax)`, where bMax = max(bLast, max b);
    - wireframe, region outlines and flux contours as `gl.LINES`;
    - pan and zoom as one 3×3 view matrix.
  - It exports the pure `viewMatrix(bounds, width, height, zoom, pan): Float32Array` for the test.
  - The 2D fallback fills each triangle on a `CanvasRenderingContext2D` with the same colours and strokes the lines.

- [ ] **Step 1: Write the failing test.** `viewMatrix` maps the bounds' centre to clip (0, 0) and keeps the aspect ratio: a square mesh in a 2:1 canvas spans x ∈ [−0.5, 0.5]. Zoom 2 halves the visible span.
- [ ] **Step 2: Run it and confirm it fails.** Run: `cd web; npx vitest run src/lib/fieldGl.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement the canvas.**
  - Wheel zoom about the cursor; drag pan with pointer events; two-pointer pinch zoom; a "Reset view" button.
  - Hover (throttled to one `requestAnimationFrame`) shows "|B| 1.23 T · stator iron" via `pickTriangle`.
  - The colour bar is vertical, viridis, in T from 0 to bMax, with a tick and a "last B-H point" mark at bLast.
  - Layer toggles are labelled checkboxes (min-h-11).
- [ ] **Step 4: Implement FieldTab (snapshot part).** It shows only when `caseId` is set and the evaluation is `ok`.
  - **Rotor angle slider:** 0 to the rotor pole pitch in mechanical degrees, step 0.25°. Its label shows "12.50° mech (−105.0° el)".
  - **Aligned / Unaligned buttons:** they set the angle from the mesh meta.
  - **Phase current:** an A input with `inputmode="decimal"`, defaulting to `windingCurrent`, with the error shown inline when it is above 2·iMax.
  - **Show:** calls the snapshot route.
  - **Note:** "First view about 10 s (mesh + one solve); repeats are instant from the cache."
  - Show ψ (mWb) and torque (N·m) of the frame, a warning when `status` is `NONCONVERGED`, and the 504/500 detail in a `role="alert"` box.
  - When `canRender()` is `"canvas2d"`, show "This browser has no WebGL2: snapshots only, no animation."
  - Add a "Field" tab to `AnalysisTabs`, lazy-loaded so Plotly-only pages do not pull it in.
- [ ] **Step 5: Run the tests and the build, then check in the browser.** Run: `cd web; npx vitest run; npm run build`. Then run `srmweb` on a scratch DB with an evaluated `screening` 8/6 case (the dev server from `.claude/launch.json`) and open the Field tab at 1280 and 375 px, light and dark. Show a snapshot and check that zoom, pan, hover and the layer toggles work. Expected: tests pass, the build is clean, and a frame draws.
- [ ] **Step 6: Commit.** `git commit -m "feat(web): Field tab snapshots with WebGL2 and a 2D fallback"`

### Task 9: Stroke animation and B(θ) probes

**Files:**
- Modify: `web/src/components/analysis/FieldTab.tsx`, `web/src/api/field.ts`, `web/src/pages/RunsPage.tsx` (the kind label)
- Create: `web/src/lib/playback.ts`
- Test: `web/src/lib/playback.test.ts`

**Interfaces:**
- Consumes: Task 6 `POST /cases/{id}/animate` and `GET /jobs/{id}/frames`; `useJobEvents`; Task 7 `framesFromWire`, `animateEstimate`; `LinePlot`.
- Produces:
  - `useAnimate()`: a mutation on the animate route, returning the job id.
  - `useFrames(jobId)`: loads the frames once the job is `done`. A 410 maps to the message "The frames were cleared; animate again."
  - `nextFrame(index: number, count: number): number` (wraps to 0).
  - `frameInterval(speed: number): number`: ms per frame at speeds 0.5×, 1× and 2×, with 1× = 100 ms.
  - `probeSeries(frames, nRotorPoles): Trace[]`: three traces ("stator pole", "stator yoke", "rotor pole") of probe |B| (T) against electrical degrees.

- [ ] **Step 1: Write the failing tests.**
  - `nextFrame(35, 36) === 0` and `nextFrame(3, 36) === 4`.
  - `frameInterval(2) === 50`.
  - `probeSeries` on two fake frames gives 3 traces with x = electricalDeg(angle) and y = the probe values.
- [ ] **Step 2: Run them and confirm they fail.** Run: `cd web; npx vitest run src/lib/playback.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement the animation section of FieldTab.**
  - **Frames input:** 12–72, default 36, with `animateEstimate` beside it. **Animate stroke** submits the job at the current phase current.
  - **While the job runs:** the existing progress bar with "frame n/N" and Cancel.
  - **When done:** frames load once. Show play/pause, a frame slider, a speed select (0.5×/1×/2×), and ψ (mWb) and torque of the current frame beside the plot.
  - **B(θ) plot:** "B in stator pole, yoke and rotor pole (T)" against electrical degrees at the chosen current.
  - **Reduced motion:** with `prefers-reduced-motion`, nothing autoplays and the slider still works.
  - **Reopening:** the latest `done` animate job in `data.jobs` (kind `"animate"`) is offered as "Load the last animation".
  - **No WebGL2:** the whole section is hidden.
  - **Runs page:** add the label "Animate" for kind `animate`.
- [ ] **Step 4: Run tests and the build, then check in the browser.** Run: `cd web; npx vitest run; npm run build`. Then animate 12 frames on the smoke case at 1280 and 375 px. Expected: progress streams, playback runs, and the B(θ) plot draws.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): stroke animation and B(θ) probe plot in the Field tab"`

### Task 10: Docs, versions and the slow end-to-end field test

**Files:**
- Modify: `src/srmweb/__init__.py` (`0.3.0`), `web/package.json` (`0.3.0`), `web/openapi.json` and `web/src/api/schema.ts` (regenerated), `CLAUDE.md`
- Create: `tests/web/test_web_e2e_field.py`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the slow test.** `@pytest.mark.slow`, `pytest.importorskip("ngsolve")`.
  - Use a real `JobRunner` and a spawn `QuickLane`. Seed an evaluated 8/6 `screening` reference case through the store, with no map built. Its `ok` evaluation has winding turns = REFERENCE_TURNS, paths 1 and current 10, and `key` has i_max 20, aligned_angle 0 and unaligned_angle π/6.
  - `GET /field/mesh`, then `POST /field` at the aligned angle and 10 A. Decode both with the `test_web_frames.py` `unpack` (move it to `tests/web_support.py`). ψ > 0, `status` is "OK", and the band count plus the static count equal the length of `b`.
  - Animate 12 frames to `done`. `GET /jobs/{id}/frames` has 12 frames, and |torque| at the last (aligned) frame is below 5 % of the largest |torque|.
- [ ] **Step 2: Run it.** Run: `python -m pytest tests/web/test_web_e2e_field.py -m slow -v`. Expected: PASS (a few minutes).
- [ ] **Step 3: Update versions and CLAUDE.md.**
  - Bump the versions and regenerate the schema.
  - In `CLAUDE.md`: fix the current-state line (v0b-2a merged to main; v0b-2b on branch `v0b-2b`, srmweb and `web/` 0.3.0). In "Web layer (v0b)", add `quick` (QuickLane), `frames` (wire format), the `animate` kind and its lane, the routes `/api/cases/{id}/field`, `/field/mesh`, `/animate` and `/api/jobs/{id}/frames`, the field cache under `<cache_dir>/fields/`, and `srmapp.field`. Add one line on waveforms and line current (R2) and that search results leave out waveforms (R3).
- [ ] **Step 4: Run the full suites.** Run: `python -m pytest -m "not slow" -q`, `cd web; npx vitest run; npm run build`, and check that the schema is fresh: `python -m srmweb.openapi web/openapi.json; git diff --exit-code web/openapi.json`. Expected: all pass, no diff.
- [ ] **Step 5: Commit.** `git commit -m "docs: v0b-2b web layer notes, version 0.3.0, end-to-end field test"`
