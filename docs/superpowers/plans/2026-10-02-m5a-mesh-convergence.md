# M5a Mesh Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the La/Lu definition and the stale-cache hash, add a `MeshSettings.scale` knob, run a mesh-convergence and grid-error study on four designs, and set the preset defaults, grid sizes and held-out limit from the data.

**Architecture:** Three small engine changes (`maps/grids.py` + `maps/results.py`, `maps/dataset.py`, `model/design.py` + `mesh/settings.py`), one study script `examples/mesh_convergence.py` with `run`, `split` and `report` modes, then a data-driven defaults task run by the controller.

**Tech Stack:** Python 3.12, numpy, scipy (`curve_fit`), matplotlib, gmsh, NGSolve, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-m5a-mesh-convergence-design.md`

## Global Constraints

- SI units internally. Comments describe the code as it is, never task or plan history.
- Import rules in `tests/test_import_rules.py` hold (`maps` may import everything below it; examples use public modules).
- Edit files only with the Edit/Write tools; never rewrite files with scripts. Always write the task report file.
- Printed output from scripts is ASCII only (Windows cp1252 redirect).
- Fast suite (`python -m pytest -m "not slow"`) stays under 10 min. New tests are fast and small.
- `LA_CURRENT_FRACTION = 0.05`. `scale` default `1.0`, `gt=0`. Band-division base = lcm(Ns, 2·Nr); study base B = lcm(Ns, 2·Nr, 12·Nr).
- Targets (worst case over designs, vs q∞; torque as % of peak): `screening` ψ/La/Lu ≤ 2 %, torque ≤ 3 %; `full` ≤ 0.5 %, ≤ 1 %; `reference` ≤ 0.1 %, ≤ 0.2 %. Defaults meet them with a factor-2 margin.
- Venv: `.venv\Scripts\python`. Tests that import `conftest` need `tests` on the path (pytest sets it; examples need `PYTHONPATH=tests`).
- Never push. Commit on branch `m5a-mesh-convergence`.

## Review Focus

1. A map whose currents were rescaled (`srmapp.turns.rescale_turns` divides currents by k): `key_numbers` must still find i_La (relative `np.isclose`, not absolute). Test in Task 1.
2. A user-supplied `n_currents` grid where 0.05·I_max coincides with a power-law node: no duplicate current (strictly increasing grid). Test in Task 1.
3. `scale != 1` with an explicit `airgap_circumferential_divisions`: divisions stay exactly as given. Test in Task 3.
4. `scale = 1` must leave every existing mesh, provenance hash input and golden unchanged except through Task 1/2 effects. Test in Task 3.
5. Very small `scale` (finest level) must not drop band divisions below the base or produce a non-multiple of the base. Test in Task 3.

---

### Task 0 (controller, not a subagent): srmapp baseline

- [ ] Before Task 1 lands, launch `examples\v0_search.py` with its defaults detached (`python -u`, stdout to `docs/m5a-v0-search-before.txt`), using an empty fresh `cache_dir` if the search exposes one. Commit the output when it finishes. It runs alongside Tasks 1–6.

### Task 1: La and Lu at a fixed current

**Files:**
- Modify: `src/srmcore/maps/grids.py` (`current_grid`, new constant)
- Modify: `src/srmcore/maps/results.py` (`key_numbers`, `KeyNumbers` field comments)
- Modify: `tests/maps/map_fixtures.py` (`synthetic_map`)
- Modify: `examples/build_map_8_6.py:51` (print at i_La instead of `currents[1]`)
- Test: `tests/maps/test_grids.py`, `tests/maps/test_results.py`

**Interfaces:**
- Produces: `grids.LA_CURRENT_FRACTION: float = 0.05`; `current_grid(i_max: float, n: int, exponent: float = 2.0) -> np.ndarray` (n power-law points ∪ {0.05·i_max}, sorted, no duplicates); `key_numbers` La/Lu = secant at that current, `ValueError` if absent.

- [ ] **Step 1: Write the failing tests**

```python
# tests/maps/test_grids.py
def test_current_grid_contains_the_la_current_once():
    c = current_grid(20.0, 8)
    assert len(c) == 9 and np.all(np.diff(c) > 0)
    assert np.isclose(c, LA_CURRENT_FRACTION * 20.0, rtol=0, atol=1e-12).sum() == 1

def test_current_grid_no_duplicate_when_la_current_is_a_node():
    c = current_grid(20.0, 2, exponent=1.0)   # nodes 0, 20; then add 1.0
    assert list(c) == [0.0, 1.0, 20.0]
    c2 = current_grid(1.0, 21, exponent=1.0)  # 0.05 is already a node
    assert len(c2) == 21 and np.all(np.diff(c2) > 0)

# tests/maps/test_results.py
def test_key_numbers_read_la_at_five_percent_of_i_max():
    r = synthetic_map(psi_sat=0.05, currents=current_grid(20.0, 8))
    k = key_numbers(r, make_8_6())
    i = 0.05 * 20.0
    assert k.la == pytest.approx(0.05 * np.tanh((L0 + L1) * i / 0.05) / i, rel=1e-9)

def test_key_numbers_after_turns_rescale():           # Review Focus 1
    r = synthetic_map(currents=current_grid(20.0, 8))
    r = dataclasses.replace(r, currents=r.currents / 3.0, psi=r.psi * 3.0)
    key_numbers(r, make_8_6())                         # must not raise

def test_key_numbers_without_la_current_raises():
    with pytest.raises(ValueError, match="0.05"):
        key_numbers(synthetic_map(currents=np.linspace(0, 20, 9), la_node=False), make_8_6())
```

Replace `test_key_numbers_use_lowest_current_when_saturating` with the five-percent test above.

- [ ] **Step 2: Run** `python -m pytest tests/maps/test_grids.py tests/maps/test_results.py -v` — expected FAIL (no `LA_CURRENT_FRACTION`, no `la_node`).

- [ ] **Step 3: Implement**
  - `current_grid`: `np.union1d` of the power-law nodes and `[LA_CURRENT_FRACTION * i_max]`, after snapping the added value to an existing node when `np.isclose` (so no near-duplicate). Docstring states the definition.
  - `key_numbers`: `i_la = LA_CURRENT_FRACTION * i_max`; index via `np.isclose(result.currents, i_la, rtol=1e-9, atol=0)`; none → `ValueError(f"map has no current at {LA_CURRENT_FRACTION} x I_max = {i_la:.6g} A")`. La/Lu = ψ/i_la at aligned/unaligned from the angle spline at that column. Update the `KeyNumbers` comments.
  - `synthetic_map(..., la_node=True)`: when true, `cur = np.union1d(cur, [0.05 * cur[-1]])`.

- [ ] **Step 4: Run** `python -m pytest tests/maps tests/app -m "not slow" -q`. Fix fallout: tests that pinned a current count or a `currents[1]` value get the new expected numbers (do not loosen tolerances); `tests/maps/test_fem_checks.py:55` keeps its meaning (sample currents above the lowest non-zero current). Expected: all pass.

- [ ] **Step 5: Commit** `fix(maps): La and Lu at a fixed 5 % of I_max`

### Task 2: Provenance hashes the resolved mesh settings

**Files:**
- Modify: `src/srmcore/maps/dataset.py` (`provenance`)
- Test: `tests/maps/test_dataset.py`

**Interfaces:**
- Produces: `provenance(...)` dict gains key `"mesh_resolved"` = `dataclasses.asdict(resolve_mesh_settings(design.machine, design.mesh))` made JSON-safe (tuples → lists).

- [ ] **Step 1: Write the failing test**

```python
def test_provenance_changes_when_preset_numbers_change(monkeypatch):
    before = provenance_hash(_prov())
    monkeypatch.setitem(settings.PRESETS, DESIGN.mesh.preset,
                        dataclasses.replace(settings.PRESETS[DESIGN.mesh.preset], iron_factor=0.5))
    assert provenance_hash(_prov()) != before

def test_provenance_holds_resolved_mesh_settings():
    p = _prov()
    assert p["mesh_resolved"]["band_divisions"] == resolve_mesh_settings(DESIGN.machine, DESIGN.mesh).band_divisions
    json.dumps(p)   # serialisable
```

- [ ] **Step 2: Run** `python -m pytest tests/maps/test_dataset.py -v` — FAIL.
- [ ] **Step 3: Implement** in `provenance`; docstring names the resolved settings as covering preset numbers and sizing code.
- [ ] **Step 4: Run** `python -m pytest tests/maps -m "not slow" -q` — PASS.
- [ ] **Step 5: Commit** `fix(maps): hash resolved mesh settings into map provenance`

### Task 3: `MeshSettings.scale`

**Files:**
- Modify: `src/srmcore/model/design.py` (`MeshSettings`)
- Modify: `src/srmcore/mesh/settings.py` (`resolve_mesh_settings`)
- Test: `tests/mesh/test_settings.py` (create if absent; basename must be unique in `tests/`)

**Interfaces:**
- Produces: `MeshSettings.scale: float = Field(1.0, gt=0)`. `resolve_mesh_settings` applies, after all preset and user values: sizes, gap size, refinement sizes × scale; growth g → 1 + (g − 1)·scale; if `scale != 1` and `airgap_circumferential_divisions is None`: `divisions = base * max(1, round(divisions / scale / base))`, base = lcm(Ns, 2·Nr). Explicit divisions are never changed.

- [ ] **Step 1: Write the failing tests**

```python
def test_scale_one_is_identity():                       # Review Focus 4
    for preset in ("screening", "full", "reference"):
        a = resolve_mesh_settings(M, MeshSettings(preset=preset))
        assert resolve_mesh_settings(M, MeshSettings(preset=preset, scale=1.0)) == a

def test_scale_half_halves_lengths_and_doubles_divisions():
    a = resolve_mesh_settings(M, MeshSettings(preset="screening"))
    b = resolve_mesh_settings(M, MeshSettings(preset="screening", scale=0.5))
    assert b.gap_size == pytest.approx(a.gap_size / 2)
    assert all(b.region_sizes[k] == pytest.approx(v / 2) for k, v in a.region_sizes.items())
    for tag, (size, g) in a.refinement.items():
        assert b.refinement[tag] == pytest.approx((size / 2, 1 + (g - 1) / 2))
    assert b.band_divisions == 2 * a.band_divisions

@pytest.mark.parametrize("scale", [2 ** -0.5, 0.3, 0.05, 3.0])
def test_scaled_divisions_stay_multiples_of_the_base(scale):   # Review Focus 5
    base = math.lcm(M.n_stator_poles, 2 * M.n_rotor_poles)
    d = resolve_mesh_settings(M, MeshSettings(preset="screening", scale=scale)).band_divisions
    assert d % base == 0 and d >= base

def test_explicit_divisions_are_not_scaled():           # Review Focus 3
    s = MeshSettings(preset="screening", scale=0.5, airgap_circumferential_divisions=1000)
    assert resolve_mesh_settings(M, s).band_divisions == 1000

def test_scale_must_be_positive():
    with pytest.raises(ValidationError):
        MeshSettings(scale=0)
```

- [ ] **Step 2: Run** `python -m pytest tests/mesh/test_settings.py -v` — FAIL.
- [ ] **Step 3: Implement** as in Interfaces; comment on `scale` explains its use (uniform refinement study; a fixed `scale` defines finer presets).
- [ ] **Step 4: Run** `python -m pytest tests/mesh tests/model tests/maps -m "not slow" -q` — PASS. Also build one scaled mesh to check the quality gate: `python -c "..."` building `make_8_6()` at `scale=0.5` via `build_machine_mesh` (expect no `MeshRejected`).
- [ ] **Step 5: Commit** `feat(mesh): MeshSettings.scale for uniform refinement`

### Task 4: Study script, `run` mode

**Files:**
- Create: `examples/mesh_convergence.py`

**Interfaces:**
- Consumes: Task 1 `LA_CURRENT_FRACTION`; Task 3 `MeshSettings.scale`.
- Produces: CLI `python examples\mesh_convergence.py run <design> <k...>` and `run-presets <design>`; designs `8_6`, `8_6_sharp` (`make_8_6(stator_fillet_radius=0, rotor_fillet_radius=0)`), `12_8`, `24_16` from `conftest`. Appends JSON lines to `docs/m5a-data/convergence.jsonl` with keys `design, level (k or preset name), scale, nodes, elements, mesh_s, peak_gb, i_max, rows`; each row `state, angle, i, psi, t_ark, t_vw, wc, status, it, s`.

- [ ] **Step 1: Implement**
  - Level k: `MeshSettings(preset="screening", scale=2**(-k/2), airgap_circumferential_divisions=B*max(1, round(D/B)))` where D = scale-k default divisions from `resolve_mesh_settings` and B = lcm(Ns, 2·Nr, 12·Nr). Preset rows: stock `MeshSettings(preset=p)`.
  - I_max: 20 A for `8_6*`; others found once by doubling from 5 A on stock `screening` at aligned until `saturation_report(...)["stator_poles"].peak >= 2.0`; cached in `docs/m5a-data/i_max.json`.
  - States: angles 0, τ/12, τ/6, τ/2; currents `LA_CURRENT_FRACTION*I_max` and `I_max` (unaligned: i_La only). One `make_solver("ngsolve")` per process; peak memory from `K32GetProcessMemoryInfo` (ctypes, Windows) or `resource.getrusage` elsewhere.
  - ASCII progress lines, `flush=True`.
- [ ] **Step 2: Smoke run** `set PYTHONPATH=tests && .venv\Scripts\python examples\mesh_convergence.py run 8_6 0` — one JSON line, 7 rows, all `OK`. Delete that smoke line from the jsonl afterwards.
- [ ] **Step 3: Commit** `feat(examples): mesh convergence study runner`

### Task 5: Study script, `split` mode (grid-error split)

**Files:**
- Modify: `examples/mesh_convergence.py`

**Interfaces:**
- Produces: `python examples\mesh_convergence.py split <design>` → one JSON line in `docs/m5a-data/split.jsonl`: `design, i_max, peak_torque, psi_max, angle_only: [{angle, i, err_psi, err_t}], current_only: [...], band: {pitch, angles, torque, rms_residual}`.

- [ ] **Step 1: Implement**
  - Build the stock `full` map with `build_map(design, i_max, workers=None)`.
  - Interpolant exactly as in `maps/fem_checks.py` (`angle_spline` over angles, `PchipInterpolator` over currents).
  - angle-only: 8 angle mid-points (evenly chosen, wrap interval included) × the grid currents i_La, mid-range, I_max; current-only: 8 grid angles × 3 current mid-points. Errors: ψ relative to ψ_max, torque relative to peak torque (from `key_numbers`).
  - band noise: at I_max, angles over 4 band pitches starting at the grid angle nearest τ/6, 8 points per pitch; residual of off-pitch points against a cubic `np.polyfit` of the on-pitch points; RMS relative to peak torque.
- [ ] **Step 2: Smoke run** `split 8_6` with a temporary small `n_angles`/`n_currents` via an env var `M5A_SMOKE=1` (8 × 4 grid), check the JSON line; remove the smoke line.
- [ ] **Step 3: Commit** `feat(examples): grid-error split in the convergence study`

### Task 6: Study script, `report` mode

**Files:**
- Modify: `examples/mesh_convergence.py`

**Interfaces:**
- Produces: `python examples\mesh_convergence.py report` → writes `docs/m5a-convergence.md` and `docs/m5a-data/*.png`.

- [ ] **Step 1: Implement**
  - Per design and quantity (ψ at each state × current; torque at τ/12 and τ/6 × I_max, Arkkio and virtual work; W′ aligned I_max): `scipy.optimize.curve_fit(q∞ + C·h^p)` over the k-levels (h = scale). Flag p ∉ [0.5, 3] or non-monotone series; flagged error bound = 3 × |q_finest − q_second|.
  - Errors relative to q∞ (torque relative to the design's peak torque at I_max from the finest level's τ/12 and τ/6 values, maximum magnitude) for every level and stock preset.
  - Tables: per design (p, q∞, fit RMS, flag, error per level and preset); summary: worst-case error per preset and per level over all designs, against the targets; split summary (worst angle-only, current-only, band RMS per design). One PNG per design: |error| vs nodes, log-log; one PNG of |T_ark − T_vw|/peak vs nodes.
- [ ] **Step 2: Check** `report` on the smoke data (or on a hand-made two-level jsonl in a temp dir via env var `M5A_DATA`) produces the markdown without errors.
- [ ] **Step 3: Commit** `feat(examples): convergence report`

### Task 7 (controller): run the study

- [ ] Launch detached, sequentially per design: `run <d> 0 1 2 3 4 5` (stop at the last level that does not page; on paging, kill and record the cap), `run-presets <d>`, `split <d>`. Watch with a Monitor that also watches the PID; re-arm every 30 min.
- [ ] `report`; commit `docs/m5a-convergence.md` and `docs/m5a-data/`.

### Task 8 (controller, owner sign-off): defaults from the data

- [ ] Apply spec §5 rules to the report: new `PRESETS` numbers (or `reference` = `full` at a fixed `scale`), `GRID_SIZES`, `fem_checks.TORQUE_TOLERANCE`, `fidelity.MAX_REL_ERROR["la"]`. Show the owner the proposed values and the evidence before editing; edit only after a yes.
- [ ] Regenerate `tests/maps/goldens_8_6.json` (command in `tests/maps/test_goldens.py` docstring); bump `version` in `pyproject.toml` (0.1.0 → 0.2.0) and reinstall `pip install -e ".[dev,ngsolve]"` so `importlib.metadata` sees it.
- [ ] Run `examples\v0_search.py` again (output `docs/m5a-v0-search-after.txt`); add a before/after section to `docs/m5a-convergence.md` (rank changes, feasibility flips).
- [ ] Full suites: `python -m pytest -m "not slow"` (time it; < 10 min) and `python -m pytest -m slow`.
- [ ] Docs: spec §4.5 preset defaults, §10/§11 entries, `docs/m4-handoff.md` La caveat, `CLAUDE.md` current state. Commit.
