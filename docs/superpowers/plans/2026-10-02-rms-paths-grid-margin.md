# Small Cycle (RMS, Paths, Grid, Margin) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the current-density limit to the RMS current, add parallel pole paths to the turns scan, use an 80 x 80 on/off grid, and add a feasibility margin (default 1.05).

**Architecture:** All changes are in `src/srmapp/` (no `srmcore` change). The drive envelope gains an RMS-current constraint inside its stroke search; windings gain a `paths` count that maps onto the existing exact turns rescale (a paths of N turns = N/a turns in series); `choose_turns`/`evaluate_stage2`/`run_search` carry the new settings.

**Tech Stack:** Python 3.12+, numpy, pytest. Venv: `.venv\Scripts\python`.

**Spec:** `docs/superpowers/specs/2026-10-01-rms-paths-grid-margin-design.md` (addendum to `docs/superpowers/specs/2026-10-01-v0a2-turns-after-map-design.md`).

## Global Constraints

- Defaults: `SearchSettings.margin = 1.05`; `SearchSettings.j_peak_max = None` meaning 2 · `j_limit`; `N_ON = N_OFF = 80`; `J_PEAK = J_LIMIT = 20e6` A/m² unchanged.
- `srmcore` must not import `srmapp` (`tests/app/test_app_layering.py`). Do not touch `srmcore`.
- SI units internally. Keep printed output ASCII (Windows cp1252 stdout).
- Edit files only with the Edit/Write tools (UTF-8). Never rewrite source files through the shell.
- Comments describe the code as it is now, with no task or plan history.
- Tests: `tests/` has no `__init__.py`; basenames must stay unique. Run from the repo root: `.venv\Scripts\python -m pytest tests/app -q`.
- Relative tolerance for limit comparisons: 1e-9 (the existing `_EPS` pattern).
- Commit after each task with the message given, ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push or merge.

## Review Focus

1. **Map range vs scanned windings.** The map current range comes from `max_mmf` with the peak cap; if stage 1 and stage 2 resolve a different cap, a scanned winding exceeds the map and `envelope` raises "current limit ... outside the map's range". Expected: the same resolved cap everywhere (Task 4 pipeline test asserts it is passed through; Task 2 `max_mmf` tests use `coil_current`).
2. **An RMS limit so tight that no stroke is valid.** Expected: torque 0, finite values, `i_rms` 0, ratios 0, no crash or NaN (Task 1 test).
3. **Odd turns with two paths** give a non-integer rescale factor. Expected: works exactly like the equivalent series winding (Task 3 equivalence test uses even and odd turn counts through the same scan).
4. **Ties in density mode** (same turns, different paths). Expected: fewer paths wins (Task 3 test).
5. **Phase resistance of a chosen design with paths**: `est.phase_resistance(design)` is the series value; the winding's resistance is that divided by paths². Expected: tests and reports use `winding.resistance` (Task 4 test).

---

### Task 1: Envelope RMS limit, i_rms output, 80 x 80 grid

**Files:**
- Modify: `src/srmapp/drive/envelope.py`
- Modify: `tests/app/test_app_envelope.py`
- Modify: `tests/app/test_app_evaluate.py:52` (Envelope gains a field)
- Modify: `tests/app/test_app_pipeline.py:24` (Envelope gains a field)

**Interfaces:**
- Produces: `envelope(result, machine, bus_voltage, resistance, speeds_rpm, *, current_limit=None, rms_limit=None, n_theta=N_THETA, n_on=N_ON, n_off=N_OFF) -> Envelope`; `Envelope.i_rms: np.ndarray` (A per speed, last field); `N_ON = N_OFF = 80`.

- [ ] **Step 1: Write the failing tests** — append to `tests/app/test_app_envelope.py`:

```python
def _env_rms(rms_limit, r=0.0):
    return envelope(synthetic_map(n_angles=24), MACHINE, 400.0, r, SPEEDS, rms_limit=rms_limit)


def test_i_rms_matches_the_copper_loss():
    env = _env(r=0.5)
    np.testing.assert_allclose(env.copper_loss, 4 * 0.5 * env.i_rms**2, rtol=1e-12)


def test_i_rms_of_a_flat_low_speed_stroke():
    env = _env()      # at 100 rpm the current reaches the 20 A limit almost at once and stays flat
    expected = 20.0 * math.sqrt((env.theta_off[0] - env.theta_on[0]) / PERIOD)
    assert env.i_rms[0] == pytest.approx(expected, rel=0.03)


def test_rms_limit_above_the_free_rms_changes_nothing():
    free = _env()
    loose = _env_rms(1.01 * float(np.max(free.i_rms)))
    np.testing.assert_array_equal(loose.torque, free.torque)


def test_binding_rms_limit_lowers_low_speed_torque():
    free = _env()
    limit = 0.7 * float(free.i_rms[0])
    capped = _env_rms(limit)
    assert capped.torque[0] < free.torque[0]
    assert np.all(capped.i_rms <= limit * (1 + 1e-9))


def test_rms_limit_with_no_valid_stroke_gives_zero_torque():
    env = _env_rms(1e-9)
    assert np.all(env.torque == 0) and np.all(env.i_rms == 0)
    for name in ("torque", "power", "copper_loss", "theta_on", "theta_off", "i_rms"):
        assert np.all(np.isfinite(getattr(env, name))), name


@pytest.mark.parametrize("limit", [0.0, -1.0])
def test_non_positive_rms_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="rms limit"):
        _env_rms(limit)


def test_default_on_off_grid_is_80_by_80():
    from srmapp.drive import envelope as module
    assert (module.N_ON, module.N_OFF) == (80, 80)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_envelope.py -q`
Expected: the new tests FAIL (`AttributeError: ... 'i_rms'`, `TypeError: ... 'rms_limit'`, grid assert).

- [ ] **Step 3: Implement** in `src/srmapp/drive/envelope.py`:

Change the grid constant:

```python
N_ON, N_OFF = 80, 80
_EPS = 1e-9
```

Add the field at the end of `Envelope` (after `work_loop`), and extend its docstring with one sentence:

```python
    """Per-speed best stroke. `torque` is the revolution average over all phases. `work_torque` is ∫T dθ and
    `work_loop` is ∮ i dψ for the chosen stroke; they agree up to discretisation. `i_rms` is the phase RMS current
    over one rotor pole pitch of the chosen stroke (0 where no stroke is valid)."""
    ...
    work_loop: np.ndarray
    i_rms: np.ndarray
```

Change `envelope`:

```python
def envelope(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float,
             speeds_rpm, *, current_limit: float | None = None, rms_limit: float | None = None,
             n_theta: int = N_THETA, n_on: int = N_ON, n_off: int = N_OFF) -> Envelope:
    """`current_limit` (A) is the hysteresis limit, at most the map's top current (the default). `rms_limit` (A)
    caps the phase RMS current over a rotor pole pitch: strokes above it are not used."""
    require_complete(result)
    if result.excited != "A":
        raise ValueError("the envelope needs the phase A map (excited='A')")
    if rms_limit is not None and not rms_limit > 0:
        raise ValueError(f"rms limit {rms_limit} A must be positive")
    ...  # unchanged down to the speed loop
    for rpm in speeds:
        omega = rpm * 2 * math.pi / 60
        w_t, w_l, i2, valid = _simulate(t, omega, bus_voltage, resistance, on, off)
        if rms_limit is not None:
            valid &= i2 / period <= rms_limit**2 * (1 + _EPS)
        best = int(np.argmax(np.where(valid, w_t, -np.inf))) if valid.any() else -1
        if best < 0 or w_t[best] <= 0:
            rows.append((0.0, 0.0, t.theta[on[0]], t.theta[off[0]], 0.0, 0.0, 0.0))
            continue
        strokes_per_rev = machine.n_phases * machine.n_rotor_poles
        rows.append((strokes_per_rev * w_t[best] / (2 * math.pi),
                     machine.n_phases * resistance * i2[best] / period,
                     t.theta[on[best]], t.theta[off[best]], w_t[best], w_l[best],
                     math.sqrt(i2[best] / period)))
    torque, copper, th_on, th_off, work_t, work_l, i_rms = (np.array(c) for c in zip(*rows))
    return Envelope(speeds, torque, torque * speeds * 2 * math.pi / 60, copper, th_on, th_off, work_t, work_l,
                    i_rms)
```

Update the two test constructions of `Envelope`:
- `tests/app/test_app_evaluate.py:52`: add a ninth argument `np.zeros(4)` after the last `np.zeros(4)`.
- `tests/app/test_app_pipeline.py:24`: `Envelope(*([np.zeros(2)] * 8))` → `Envelope(*([np.zeros(2)] * 9))`.

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/app -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/drive/envelope.py tests/app/test_app_envelope.py tests/app/test_app_evaluate.py tests/app/test_app_pipeline.py
git commit -m "feat(app): envelope RMS current limit and output, 80 x 80 on/off grid"
```

---

### Task 2: Parallel paths and the peak-density cap in the windings; stage 1

**Files:**
- Modify: `src/srmapp/sizing/winding.py`
- Modify: `src/srmapp/sizing/stage1.py`
- Modify: `tests/app/test_app_winding.py`
- Modify: `tests/app/test_app_stage1.py`

**Interfaces:**
- Produces:
  - `Winding(turns, strands, copper_area, current, resistance, copper_mass, wire, paths=1)`; `Winding.coil_current` (= current / paths); `Winding.current_density` (peak conductor density = coil_current / copper_area). `resistance` is the phase value with its paths in parallel.
  - `path_counts(p: RadialSRMParams) -> list[int]` (divisors of `n_stator_poles // n_phases`, increasing).
  - `wire_windings(p, req, wire, j_peak_max) -> list[Winding]`, ordered by paths, then increasing turns.
  - `density_windings(p, req, j_peak, max_turns=DENSITY_MAX_TURNS) -> list[Winding]`, ordered by paths, then increasing turns.
  - `max_mmf(p, req, j_peak, j_peak_max) -> float` (largest `turns * coil_current`).
  - `stage1(req, p, margin=1.0, j_peak=J_PEAK, j_peak_max=2 * J_LIMIT) -> Stage1`.

- [ ] **Step 1: Write / update the tests** in `tests/app/test_app_winding.py`.

Add `make_12_8` to the conftest import: `from conftest import make_12_8, make_8_6`. Add `path_counts` to the winding import.

Replace `test_wire_windings_fill_the_slot_with_the_most_strands`, `test_wire_resistance_grows_with_turns`, `test_density_windings`, `test_max_mmf_covers_every_wire_winding` and `test_max_mmf_is_the_largest_ampere_turns_of_the_allowed_windings` with:

```python
def test_wire_windings_fill_the_slot_with_the_most_strands():
    req = _req(wires=[THIN], phase_current_a=100.0)
    room = req.max_slot_fill * A / req.wires[0].outer_area
    ws = wire_windings(P, req, 0, 20e6)
    assert ws and {w.paths for w in ws} == {1, 2}
    for paths in (1, 2):
        turns = [w.turns for w in ws if w.paths == paths]
        assert turns == sorted(turns)
    for w in ws:
        assert w.turns * w.strands <= room * (1 + 1e-9)
        assert w.turns * (w.strands + 1) > room
        assert w.copper_area == pytest.approx(w.strands * req.wires[0].copper_area)
        assert w.current == 100.0 and w.coil_current == 100.0 / w.paths and w.wire == 0
        assert w.current_density <= 20e6 * (1 + 1e-9)
        assert w.resistance == pytest.approx(est.series_resistance(P, w.turns, w.copper_area) / w.paths**2)
        assert w.copper_mass == pytest.approx(est.copper_mass(P, w.turns, w.copper_area))


def test_wire_resistance_grows_with_turns():
    ws = wire_windings(P, _req(wires=[THIN], phase_current_a=100.0), 0, 20e6)
    for paths in (1, 2):
        r = [w.resistance for w in ws if w.paths == paths]
        assert len(r) > 1 and all(b > a for a, b in zip(r, r[1:]))


def test_peak_cap_keeps_densities_above_the_cooling_limit():
    req = _req(wires=[THICK], phase_current_a=800.0)       # one THICK strand at 800 A is about 28 A/mm²
    loose, tight = wire_windings(P, req, 0, 40e6), wire_windings(P, req, 0, 20e6)
    assert any(20e6 < w.current_density <= 40e6 * (1 + 1e-9) for w in loose)
    assert all(w.current_density <= 20e6 * (1 + 1e-9) for w in tight) and len(tight) < len(loose)


def test_path_counts_are_the_divisors_of_the_poles_per_phase():
    assert path_counts(P) == [1, 2]                  # 8/6: 2 poles per phase
    assert path_counts(make_12_8()) == [1, 2, 4]     # 12/8: 4 poles per phase


def test_parallel_paths_equal_the_series_winding_of_fewer_turns():
    ws = {(w.turns, w.paths): w for w in density_windings(P, _req(), 20e6, max_turns=40)}
    for n in (1, 7, 20):
        two, one = ws[(2 * n, 2)], ws[(n, 1)]
        assert two.resistance == pytest.approx(one.resistance)
        assert two.current == pytest.approx(one.current)
        assert two.copper_mass == pytest.approx(one.copper_mass)


def test_density_windings():
    ws = density_windings(P, _req(), 20e6, max_turns=50)
    assert len(ws) == 100
    assert [w.turns for w in ws if w.paths == 1] == list(range(1, 51))
    assert [w.turns for w in ws if w.paths == 2] == list(range(1, 51))
    for w in ws:
        assert w.strands == 1 and w.wire is None
        assert w.copper_area == pytest.approx(P.fill_factor * A / w.turns)
        assert w.current_density == pytest.approx(20e6)
        assert w.current == pytest.approx(20e6 * w.copper_area * w.paths)


@pytest.mark.parametrize("wires", [[THIN], [THICK], [THIN, THICK]])
def test_max_mmf_covers_every_wire_winding(wires):
    req = _req(wires=wires, phase_current_a=60.0)
    top = max_mmf(P, req, 20e6, 20e6)
    for i in range(len(wires)):
        assert all(w.turns * w.coil_current <= top * (1 + 1e-9) for w in wire_windings(P, req, i, 20e6))


def test_max_mmf_is_the_largest_ampere_turns_of_the_allowed_windings():
    req = _req(wires=[THIN, THICK], phase_current_a=60.0)
    top = max(w.turns * w.coil_current for i in range(2) for w in wire_windings(P, req, i, 20e6))
    assert max_mmf(P, req, 20e6, 20e6) == top
    thin = _req(wires=[THIN], phase_current_a=60.0)
    old_bound = 20e6 * thin.max_slot_fill * A * max(w.copper_area / w.outer_area for w in thin.wires)
    assert max_mmf(P, thin, 20e6, 20e6) < old_bound
```

In `test_max_mmf_density_mode`, replace `w.turns * w.current` with `w.turns * w.coil_current`.

In `tests/app/test_app_stage1.py`, replace `test_wire_mode_range_follows_the_cooling_limit` with:

```python
def test_wire_mode_range_follows_the_peak_cap():
    req = _req(wires=[dict(kind="round", diameter=1e-3, outer_diameter=1.08e-3)], phase_current_a=100.0)
    p = make_8_6()
    lo, hi = stage1(req, p, j_peak_max=10e6), stage1(req, p, j_peak_max=20e6)
    assert hi.mmf >= lo.mmf
    for s, j in ((lo, 10e6), (hi, 20e6)):
        assert s.mmf == max(w.turns * w.coil_current for w in wire_windings(p, req, 0, j))


def test_stage1_default_cap_is_twice_the_cooling_limit():
    req = _req(wires=[dict(kind="round", diameter=1e-3, outer_diameter=1.08e-3)], phase_current_a=100.0)
    assert stage1(req, make_8_6()).mmf == stage1(req, make_8_6(), j_peak_max=40e6).mmf
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_winding.py tests/app/test_app_stage1.py -q`
Expected: FAIL (`ImportError: cannot import name 'path_counts'`, `AttributeError: ... 'paths'`, `TypeError: ... 'j_peak_max'`).

- [ ] **Step 3: Implement** `src/srmapp/sizing/winding.py`:

Module docstring:

```python
"""Windings a geometry can carry (v0a-2 spec §3, small-cycle spec §3). Wire mode fixes the wire and the phase
current and fits as many parallel strands as the slot holds; density mode fixes the current density. The poles of a
phase are connected in `paths` equal parallel paths, each carrying the phase current / paths."""
```

`Winding`:

```python
@dataclass(frozen=True)
class Winding:
    turns: int             # per pole
    strands: int           # parallel conductors per turn
    copper_area: float     # m², one turn, all strands
    current: float         # A, peak phase current
    resistance: float      # Ω, one phase at 100 °C, its paths in parallel
    copper_mass: float     # kg, all coils
    wire: int | None       # index into Requirements.wires; None in density mode
    paths: int = 1         # parallel paths per phase

    @property
    def coil_current(self) -> float:
        """A, peak current in one coil."""
        return self.current / self.paths

    @property
    def current_density(self) -> float:
        """A/m², peak conductor current density."""
        return self.coil_current / self.copper_area


def path_counts(p: RadialSRMParams) -> list[int]:
    """Parallel path counts a phase allows: the divisors of its pole count."""
    poles = p.n_stator_poles // p.n_phases
    return [a for a in range(1, poles + 1) if poles % a == 0]


def _winding(p: RadialSRMParams, turns: int, strands: int, copper_area: float, current: float,
             wire: int | None, paths: int) -> Winding:
    return Winding(turns, strands, copper_area, current, series_resistance(p, turns, copper_area) / paths**2,
                   copper_mass(p, turns, copper_area), wire, paths)


def wire_windings(p: RadialSRMParams, req: Requirements, wire: int, j_peak_max: float) -> list[Winding]:
    """Every (paths, turns) `req.wires[wire]` can wind at `req.phase_current_a`, each with as many parallel strands
    as fit in `req.max_slot_fill` of the coil side, keeping the peak conductor current density within `j_peak_max`.
    Ordered by paths, then increasing turns."""
    w = req.wires[wire]
    room = req.max_slot_fill * coil_side_area(p) / w.outer_area     # conductors that fit in one coil side
    out = []
    for paths in path_counts(p):
        for turns in range(1, math.floor(room + _EPS) + 1):
            strands = math.floor(room / turns + _EPS)
            area = strands * w.copper_area
            if req.phase_current_a / paths / area <= j_peak_max * (1 + _EPS):
                out.append(_winding(p, turns, strands, area, req.phase_current_a, wire, paths))
    return out


def density_windings(p: RadialSRMParams, req: Requirements, j_peak: float,
                     max_turns: int = DENSITY_MAX_TURNS) -> list[Winding]:
    """Turn counts 1..max_turns for every path count, at current density `j_peak` in `p.fill_factor` of the coil
    side; windings whose peak phase current exceeds `req.phase_current_a` (when set) are left out. Ordered by
    paths, then increasing turns."""
    copper = p.fill_factor * coil_side_area(p)
    out = []
    for paths in path_counts(p):
        for turns in range(1, max_turns + 1):
            area = copper / turns
            current = j_peak * area * paths
            if req.phase_current_a is None or current <= req.phase_current_a * (1 + _EPS):
                out.append(_winding(p, turns, 1, area, current, None, paths))
    return out


def max_mmf(p: RadialSRMParams, req: Requirements, j_peak: float, j_peak_max: float) -> float:
    """Largest peak ampere-turns per pole any allowed winding carries (v0a-2 spec §3.3); the map must cover it.
    0 when wire mode allows no winding."""
    if req.wire_mode:
        return max((w.turns * w.coil_current for i in range(len(req.wires))
                    for w in wire_windings(p, req, i, j_peak_max)), default=0.0)
    return j_peak * p.fill_factor * coil_side_area(p)
```

`src/srmapp/sizing/stage1.py`: change the signature and the call; nothing else:

```python
def stage1(req: Requirements, p: RadialSRMParams, margin: float = 1.0, j_peak: float = J_PEAK,
           j_peak_max: float = 2 * J_LIMIT) -> Stage1:
    mass = active_mass(p)
    mmf = max_mmf(p, req, j_peak, j_peak_max)
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_winding.py tests/app/test_app_stage1.py -q`
Expected: PASS. (`tests/app/test_app_turns.py` and `test_app_evaluate.py` may fail until Tasks 3–4; that is expected.)

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/sizing/winding.py src/srmapp/sizing/stage1.py tests/app/test_app_winding.py tests/app/test_app_stage1.py
git commit -m "feat(app): parallel pole paths and a peak current-density cap in the windings"
```

---

### Task 3: Turns scan with paths, RMS limit, margin and cap flag

**Files:**
- Modify: `src/srmapp/turns.py`
- Modify: `tests/app/test_app_turns.py`

**Interfaces:**
- Consumes: Task 1 `envelope(..., rms_limit=...)`, `Envelope.i_rms`; Task 2 `Winding.paths`, `Winding.coil_current`, `wire_windings(p, req, wire, j_peak_max)`, `density_windings`, `max_mmf(p, req, j_peak, j_peak_max)`.
- Produces:
  - `ScanPoint(winding, torque_ratio, power_ratio, i_rms, feasible)`; properties `worst`, `j_rms` (A/m², = i_rms / (paths · copper_area)).
  - `TurnsChoice(point, feasible, envelope, scan, capped)`; `capped: bool`.
  - `turns_scale(machine, w) -> float` (= w.turns / (w.paths · machine.turns_per_pole)).
  - `choose_turns(result, machine, req, *, j_peak=J_PEAK, j_limit=J_LIMIT, j_peak_max=None, margin=1.0, max_turns=DENSITY_MAX_TURNS) -> TurnsChoice`. `j_peak_max=None` means `2 * j_limit`.

- [ ] **Step 1: Write / update the tests** in `tests/app/test_app_turns.py`.

Change `_map_for` to use the default cap:

```python
def _map_for(req, j_peak=20e6, j_peak_max=40e6):
    top = max_mmf(MACHINE, req, j_peak, j_peak_max) / MACHINE.turns_per_pole
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, top, 9))
```

In `test_wire_mode_picks_the_lowest_resistance_feasible_winding`, replace the `same_wire` lines with:

```python
    same = [s.winding.turns for s in feasible
            if (s.winding.wire, s.winding.paths) == (c.point.winding.wire, c.point.winding.paths)]
    assert c.point.winding.turns == min(same)
```

Replace `test_density_mode_picks_the_most_turns` with:

```python
def test_density_mode_picks_the_most_turns_then_the_fewest_paths():
    req = _req()
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40)
    assert c.feasible and len(c.scan) == 80          # 40 turn counts x paths 1 and 2
    feasible = [s for s in c.scan if s.feasible]
    assert c.point.winding.turns == max(s.winding.turns for s in feasible)
    assert c.point.winding.paths == min(s.winding.paths for s in feasible if s.winding.turns == c.point.winding.turns)
```

Append:

```python
def test_two_paths_scan_like_the_series_winding_of_half_the_turns():
    req = _req()
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40)
    by = {(s.winding.turns, s.winding.paths): s for s in c.scan}
    for n in (1, 7, 20):          # 2n turns on 2 paths act as n turns in series
        two, one = by[(2 * n, 2)], by[(n, 1)]
        assert (two.torque_ratio, two.power_ratio) == pytest.approx((one.torque_ratio, one.power_ratio), rel=1e-9)
        assert two.i_rms == pytest.approx(one.i_rms, rel=1e-9)
        assert two.j_rms == pytest.approx(one.j_rms, rel=1e-9)


def test_margin_sets_feasibility():
    req = _req()
    base = choose_turns(_map_for(req), MACHINE, req, max_turns=20, margin=1.0)
    assert all(s.feasible == (s.worst >= 1.0) for s in base.scan)
    bar = base.point.worst * 1.001
    strict = choose_turns(_map_for(req), MACHINE, req, max_turns=20, margin=bar)
    assert all(s.feasible == (s.worst >= bar) for s in strict.scan)
    assert not any(s.feasible for s in strict.scan if s.winding == base.point.winding)


def test_rms_limit_binds_the_scan():
    req = _req(wires=[THICK], phase_current_a=100.0)
    m = _map_for(req, j_peak_max=40e6)
    loose = choose_turns(m, MACHINE, req, j_limit=1e9, j_peak_max=40e6)
    limit = 0.5 * float(np.median([s.j_rms for s in loose.scan]))
    tight = choose_turns(m, MACHINE, req, j_limit=limit, j_peak_max=40e6)
    assert [s.winding for s in tight.scan] == [s.winding for s in loose.scan]
    assert all(s.j_rms <= limit * (1 + 1e-9) for s in tight.scan)
    assert any(t.torque_ratio < l.torque_ratio for t, l in zip(tight.scan, loose.scan))


def test_capped_flag_reports_windings_left_out_by_the_peak_cap():
    req = _req(wires=[THICK], phase_current_a=800.0)       # one THICK strand at 800 A is about 28 A/mm²
    assert choose_turns(_map_for(req, j_peak_max=20e6), MACHINE, req, j_peak_max=20e6).capped
    assert not choose_turns(_map_for(req, j_peak_max=1e12), MACHINE, req, j_peak_max=1e12).capped
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_turns.py -q`
Expected: FAIL (`AttributeError: 'ScanPoint' ... 'i_rms'`, `TypeError: ... 'margin'`, `... 'capped'`).

- [ ] **Step 3: Implement** in `src/srmapp/turns.py`:

Add `import math` at the top. Replace `ScanPoint`, `TurnsChoice`, `_envelope` and `choose_turns` with:

```python
@dataclass(frozen=True)
class ScanPoint:
    winding: Winding
    torque_ratio: float     # achieved / required, at base speed
    power_ratio: float      # achieved / required, worst over base..max speed
    i_rms: float            # A, phase RMS current, worst over base..max speed
    feasible: bool          # worst ratio at least the margin

    @property
    def worst(self) -> float:
        return min(self.torque_ratio, self.power_ratio)

    @property
    def j_rms(self) -> float:
        """A/m², conductor RMS current density."""
        return self.i_rms / (self.winding.paths * self.winding.copper_area)


@dataclass(frozen=True)
class TurnsChoice:
    point: ScanPoint | None        # None when no winding meets the wire, current and current-density limits
    feasible: bool
    envelope: Envelope | None      # chosen winding over the full speed grid
    scan: tuple[ScanPoint, ...]    # every winding tried, in scan order
    capped: bool                   # wire mode: the peak current-density cap left out windings that fit the slot


def turns_scale(machine: RadialSRMParams, w: Winding) -> float:
    """Rescale factor from the map at `machine.turns_per_pole` to winding `w`: `paths` parallel paths of N turns
    act as N / paths turns in series."""
    return w.turns / (w.paths * machine.turns_per_pole)


def _envelope(result: MapResult, machine: RadialSRMParams, req: Requirements, w: Winding, speeds,
              j_limit: float) -> Envelope:
    return envelope(rescale_turns(result, turns_scale(machine, w)), machine, req.bus_voltage_v, w.resistance,
                    speeds, current_limit=w.current, rms_limit=j_limit * w.paths * w.copper_area)


def choose_turns(result: MapResult, machine: RadialSRMParams, req: Requirements, *, j_peak: float = J_PEAK,
                 j_limit: float = J_LIMIT, j_peak_max: float | None = None, margin: float = 1.0,
                 max_turns: int = DENSITY_MAX_TURNS) -> TurnsChoice:
    """Scan every allowed winding on the map of `machine` (built at `machine.turns_per_pole`). `j_limit` caps the
    conductor RMS current density, `j_peak_max` (default 2 · `j_limit`) the peak density in wire mode. A winding is
    feasible when its worst ratio is at least `margin`. Wire mode keeps the feasible winding with the lowest
    resistance; density mode keeps the feasible winding with the most turns, then the fewest paths. With no
    feasible winding, the one with the largest worst ratio is reported."""
    cap = 2 * j_limit if j_peak_max is None else j_peak_max
    capped = False
    if req.wire_mode:
        windings = [w for i in range(len(req.wires)) for w in wire_windings(machine, req, i, cap)]
        capped = len(windings) < sum(len(wire_windings(machine, req, i, math.inf)) for i in range(len(req.wires)))
    else:
        windings = density_windings(machine, req, j_peak, max_turns)
    grid = speed_grid(req)
    band = grid[grid >= req.base_speed_rpm]

    def scan_point(w: Winding) -> ScanPoint:
        env = _envelope(result, machine, req, w, band, j_limit)
        torque_ratio, power_ratio = requirement_ratios(env, req)
        return ScanPoint(w, torque_ratio, power_ratio, float(np.max(env.i_rms)),
                         min(torque_ratio, power_ratio) >= margin)

    scan = tuple(scan_point(w) for w in windings)
    if not scan:
        return TurnsChoice(None, False, None, (), capped)
    feasible = [s for s in scan if s.feasible]
    if not feasible:
        point = max(scan, key=lambda s: (s.worst, -s.winding.resistance))
    elif req.wire_mode:
        point = min(feasible, key=lambda s: (s.winding.resistance, s.winding.turns, s.winding.paths))
    else:
        point = max(feasible, key=lambda s: (s.winding.turns, -s.winding.paths))
    return TurnsChoice(point, bool(feasible), _envelope(result, machine, req, point.winding, grid, j_limit), scan,
                       capped)
```

Delete the old comment `# for one wire, resistance grows with turns ...` (no longer true across path counts).

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_turns.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/turns.py tests/app/test_app_turns.py
git commit -m "feat(app): turns scan over parallel paths with the RMS limit, margin and peak-cap flag"
```

---

### Task 4: Evaluation and search settings

**Files:**
- Modify: `src/srmapp/evaluate.py`
- Modify: `src/srmapp/pipeline.py`
- Modify: `tests/app/test_app_evaluate.py`
- Modify: `tests/app/test_app_pipeline.py`

**Interfaces:**
- Consumes: Task 3 `choose_turns(..., j_peak_max=, margin=)`, `TurnsChoice.capped`, `turns_scale`; Task 2 `stage1(req, p, margin, j_peak, j_peak_max)`.
- Produces:
  - `evaluate_stage2(candidate, req, stage, *, grid, j_peak, j_limit, j_peak_max=None, margin=1.0, max_turns, solver, workers, cache_dir, progress, cancel)`.
  - `Evaluation` gains trailing fields `i_rms_a: float = nan` (A, worst phase RMS over the full speed grid) and `j_rms: float = nan` (A/m²).
  - `SearchSettings.margin = 1.05`, `SearchSettings.j_peak_max: float | None = None`.

- [ ] **Step 1: Write / update the tests.**

`tests/app/test_app_evaluate.py`:

In `test_density_mode_evaluation_fills_the_metrics` change two lines:

```python
    assert est.phase_resistance(m) == pytest.approx(e.winding.resistance * e.winding.paths**2)
    assert len(e.scan) == 60          # 30 turn counts x paths 1 and 2
```

Replace the body assertions of `test_wire_mode_evaluation_uses_the_inverter_current` with:

```python
    req = _req(wires=[THICK], phase_current_a=100.0)
    e, _ = _evaluate(req)
    assert e.status == "ok" and e.winding.wire == 0
    assert e.winding.current == 100.0 and e.winding.strands >= 1
    assert e.winding.current_density <= 40e6 * (1 + 1e-9)
    assert 0 < e.i_rms_a and e.j_rms <= 20e6 * (1 + 1e-9)
    assert e.j_rms == pytest.approx(e.i_rms_a / (e.winding.paths * e.winding.copper_area))
    assert est.phase_resistance(e.design.machine) == pytest.approx(e.winding.resistance * e.winding.paths**2)
```

In `test_no_winding_is_reported_not_raised` change `j_limit=1.0` to `j_peak_max=1.0` and the comment to `# stricter than the stage-1 range`.

In `test_failed_map_becomes_an_evaluation_and_does_not_raise` add `assert math.isnan(e.i_rms_a) and math.isnan(e.j_rms)`.

Append:

```python
def test_margin_reaches_the_turns_choice():
    e, _ = _evaluate(_req(), margin=1e6)
    assert e.status == "ok" and not e.feasible


def test_capped_infeasible_result_carries_a_note():
    req = _req(wires=[THICK], phase_current_a=800.0, peak_torque_nm=1e3, peak_power_w=314_159.0)
    e, _ = _evaluate(req, j_limit=10e6)          # cap 20 A/mm² leaves out the one-strand windings
    assert e.status == "ok" and not e.feasible
    assert "j_peak_max" in e.error
```

`tests/app/test_app_pipeline.py`:

Replace `test_j_peak_reaches_stage_one` with:

```python
def test_settings_reach_stage_one():
    seen = []
    real = __import__("srmapp.pipeline", fromlist=["stage1"]).stage1

    def spy(req, p, margin, j_peak, j_peak_max):
        seen.append((margin, j_peak, j_peak_max))
        return real(req, p, margin, j_peak, j_peak_max)
    with mock.patch("srmapp.pipeline.stage1", side_effect=spy), mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak=25e6, j_limit=30e6))
    assert seen and set(seen) == {(1.05, 25e6, 60e6)}
```

Replace `test_current_density_settings_reach_stage_two` with:

```python
def test_settings_reach_stage_two():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak=25e6, j_limit=30e6))
    kw = ev.call_args.kwargs
    assert (kw["j_peak"], kw["j_limit"], kw["j_peak_max"], kw["margin"]) == (25e6, 30e6, 60e6, 1.05)


def test_explicit_peak_cap_is_used():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak_max=33e6))
    assert ev.call_args.kwargs["j_peak_max"] == 33e6
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_evaluate.py tests/app/test_app_pipeline.py -q`
Expected: FAIL (`TypeError: ... 'margin'` / `'j_peak_max'`, `AttributeError: ... 'i_rms_a'`, settings asserts).

- [ ] **Step 3: Implement.**

`src/srmapp/evaluate.py`:
- Import line: `from .turns import ScanPoint, choose_turns, requirement_ratios, rescale_turns, speed_grid, turns_scale  # noqa: F401`.
- Add to `Evaluation` after `scan`:

```python
    scan: tuple[ScanPoint, ...] = ()
    i_rms_a: float = _NAN       # A, worst phase RMS current over the speed grid, chosen winding
    j_rms: float = _NAN         # A/m², conductor RMS current density at i_rms_a
```

- `evaluate_stage2` signature: add `j_peak_max: float | None = None, margin: float = 1.0,` after `j_limit: float = J_LIMIT,`.
- Body changes:

```python
    choice = choose_turns(result, machine, req, j_peak=j_peak, j_limit=j_limit, j_peak_max=j_peak_max,
                          margin=margin, max_turns=max_turns)
    ...
    key = key_numbers(rescale_turns(result, turns_scale(machine, w)), chosen)
    i_rms = float(np.max(env.i_rms))
    notes = []
    if not req.wire_mode and w.turns == max_turns:
        notes.append(f"turn scan reached its limit of {max_turns}; more turns may also be feasible")
    if not choice.feasible and choice.capped:
        notes.append("no winding is feasible and j_peak_max left out windings that fit the slot; "
                     "a higher cap might allow one")
    over_mass = ...  # unchanged
    return Evaluation(candidate.id, design.model_copy(update={"machine": chosen}), "ok", "; ".join(notes), mass, w,
                      choice.point.torque_ratio, choice.point.power_ratio, peak_power, peak_power / 1000 / mass,
                      float(env.efficiency[at_base]), choice.feasible and not over_mass, env, key, choice.scan,
                      i_rms, i_rms / (w.paths * w.copper_area))
```

- Module docstring: append "Parallel paths and the RMS current-density limit: small-cycle spec." to the first sentence block (one short sentence).

`src/srmapp/pipeline.py`:

```python
@dataclass(frozen=True)
class SearchSettings:
    n_candidates: int = 200
    seed: int = 0
    shortlist: int = 40
    grid: StageTwoGrid = field(default_factory=StageTwoGrid)
    margin: float = 1.05            # feasible when the worst of torque and power ratio is at least this
    j_peak: float = J_PEAK          # A/m², peak current density that sets each design's I_max (density mode)
    j_limit: float = J_LIMIT        # A/m², cooling limit on the conductor RMS current density
    j_peak_max: float | None = None  # A/m², peak conductor current density cap in wire mode; None is 2 x j_limit

    @property
    def peak_cap(self) -> float:
        return 2 * self.j_limit if self.j_peak_max is None else self.j_peak_max
```

In `run_search`:

```python
    scored = [(c, stage1(req, c.design.machine, settings.margin, settings.j_peak, settings.peak_cap))
              for c in candidates]
    ...
        evaluation = evaluate_stage2(candidate, req, stage, grid=settings.grid, j_peak=settings.j_peak,
                                     j_limit=settings.j_limit, j_peak_max=settings.peak_cap,
                                     margin=settings.margin, solver=solver, workers=workers,
                                     cache_dir=cache_dir, cancel=cancel)
```

- [ ] **Step 4: Run the whole app suite**

Run: `.venv\Scripts\python -m pytest tests/app -q -m "not slow"`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/evaluate.py src/srmapp/pipeline.py tests/app/test_app_evaluate.py tests/app/test_app_pipeline.py
git commit -m "feat(app): RMS outputs, margin and peak cap through evaluation and search settings"
```

---

### Task 5: Accuracy-check script and docs

**Files:**
- Modify: `examples/v0_angle_check.py`
- Modify: `CLAUDE.md` (the `src/srmapp/` paragraph)
- Modify: `docs/superpowers/specs/2026-10-01-v0a2-turns-after-map-design.md` §10 items 1–2 (one line pointing to the small-cycle spec)

**Interfaces:**
- Consumes: `SearchSettings` (`margin`, `j_peak`, `j_limit`, `peak_cap`), `stage1`, `choose_turns`, `turns_scale`, `envelope(..., rms_limit=)`.

- [ ] **Step 1: Rewrite `examples/v0_angle_check.py`** (full file):

```python
"""Stage-2 accuracy check (v0a-2 spec §5, small-cycle spec §8) on one candidate per pole set, all with the winding
chosen on the 30-angle map at the search defaults (margin, RMS current-density limit, peak cap, paths): envelope
from 30 angles against 60 angles on the `full` mesh, 20 map currents against twice as many, and the drive
discretisation (N_THETA 181 against 361; the 80 x 80 on/off grid against 160 x 160 at N_THETA 361).

    python examples/v0_angle_check.py [n_candidates] [n_currents]

Prints, per design, the torque ratio at base speed and the worst power ratio over base..max speed for each
variant, and their change against the default (30 angles, 1x currents, 181, 80 x 80). The on/off grid effect is
the "361, on/off 160" row against the "n_theta 361" row. Maps are cached in out/v0_angle_check. Hours on a laptop."""
import sys
import time

from srmapp.drive.envelope import envelope
from srmapp.pipeline import SearchSettings
from srmapp.requirements import Requirements
from srmapp.sizing.generator import sample_candidates
from srmapp.sizing.stage1 import stage1
from srmapp.turns import choose_turns, requirement_ratios, rescale_turns, speed_grid, turns_scale
from srmapp.wire import LitzWire, RectangularWire, RoundWire
from srmcore.maps import build_map

REQ = Requirements(peak_power_w=10_000.0, peak_torque_nm=32.0, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                   wires=(RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3),
                          RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3),
                          LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3)),
                   phase_current_a=150.0)
# name: (map angles, current multiplier, n_theta, on/off grid size)
VARIANTS = {"default": (30, 1, 181, 80), "60 angles": (60, 1, 181, 80), "2x currents": (30, 2, 181, 80),
            "n_theta 361": (30, 1, 361, 80), "361, on/off 160": (30, 1, 361, 160)}
CACHE = "out/v0_angle_check"
S = SearchSettings()

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n_currents = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    candidates, _ = sample_candidates(REQ, n, seed=0)
    for c in candidates:
        m = c.design.machine
        t0 = time.perf_counter()
        stage = stage1(REQ, m, S.margin, S.j_peak, S.peak_cap)
        label = f"{c.id} {m.n_stator_poles}/{m.n_rotor_poles} OD {m.stator_outer_diameter * 1e3:.0f} mm"
        if stage.mmf == 0.0:
            print(f"\n{label}\n  no winding meets the limits; skipped")
            continue
        maps = {(a, k * n_currents): build_map(c.design, stage.i_map, n_angles=a, n_currents=k * n_currents,
                                               cache_dir=CACHE)
                for a, k in sorted({v[:2] for v in VARIANTS.values()})}
        choice = choose_turns(maps[(30, n_currents)], m, REQ, j_peak=S.j_peak, j_limit=S.j_limit,
                              j_peak_max=S.peak_cap, margin=S.margin)
        print(f"\n{label} ({time.perf_counter() - t0:.0f} s)")
        if choice.point is None:
            print("  no winding meets the limits; skipped")
            continue
        w = choice.point.winding
        print(f"  wire {REQ.wires[w.wire].kind}, N {w.turns}, paths {w.paths}, strands {w.strands}, "
              f"R {w.resistance * 1e3:.1f} mOhm, J_rms {choice.point.j_rms / 1e6:.1f} A/mm2, "
              f"feasible {choice.feasible}")
        rows = {}
        for name, (n_a, k, n_theta, n_sw) in VARIANTS.items():
            env = envelope(rescale_turns(maps[(n_a, k * n_currents)], turns_scale(m, w)), m, REQ.bus_voltage_v,
                           w.resistance, speed_grid(REQ), current_limit=w.current,
                           rms_limit=S.j_limit * w.paths * w.copper_area, n_theta=n_theta, n_on=n_sw, n_off=n_sw)
            rows[name] = requirement_ratios(env, REQ)
        ref = rows["default"]
        print(f"  {'variant':16}{'T ratio':>9}{'P ratio':>9}{'dT':>9}{'dP':>9}")
        for name, (t, p) in rows.items():
            dt = (t - ref[0]) / ref[0] if ref[0] else float("nan")
            dp = (p - ref[1]) / ref[1] if ref[1] else float("nan")
            print(f"  {name:16}{t:9.3f}{p:9.3f}{dt:9.2%}{dp:9.2%}")
```

- [ ] **Step 2: Smoke-check that the script imports and parses**

Run: `.venv\Scripts\python -c "import ast,sys; ast.parse(open('examples/v0_angle_check.py', encoding='utf-8').read()); import runpy; runpy.run_path('examples/v0_angle_check.py', run_name='not_main')"`
Expected: no output, exit 0.

- [ ] **Step 3: Update `CLAUDE.md`**. In the `src/srmapp/` paragraph, after the sentence ending "in density mode the feasible winding with the most turns.", insert:

```
Windings may use parallel pole paths (a paths of N turns act as N/a turns on the map); `j_limit` caps the conductor RMS current density inside the drive's stroke search, `j_peak_max` (default 2 x `j_limit`) caps the peak density and thus the map range, and a design is feasible when its worst ratio is at least `SearchSettings.margin` (default 1.05). The on/off grid is 80 x 80. See `docs/superpowers/specs/2026-10-01-rms-paths-grid-margin-design.md`.
```

Also in the Commands block change the `v0_angle_check.py` comment to `# stage-2 angle, current and drive-discretisation check at the search defaults (hours)`.

- [ ] **Step 4: Update the v0a-2 spec §10.** After the line starting `2. **Parallel pole paths.**`, add a new line:

```
Items 1 and 2 and decisions (a) and (b) are implemented as specified in `2026-10-01-rms-paths-grid-margin-design.md`.
```

- [ ] **Step 5: Run the fast suite**

Run: `.venv\Scripts\python -m pytest -m "not slow" -q --durations=15` (about 8 minutes)
Expected: all PASS, total under the 10-minute CI budget. The density scans doubled (two path counts) and the on/off grid is 4x larger; if the total exceeds 10 minutes, lower `max_turns` in the slowest `tests/app` tests (keeping every assertion meaningful) and report it.

- [ ] **Step 6: Commit**

```bash
git add examples/v0_angle_check.py CLAUDE.md docs/superpowers/specs/2026-10-01-v0a2-turns-after-map-design.md
git commit -m "docs, examples: small-cycle defaults in the accuracy check and the docs"
```

---

### Task 6 (controller, not a subagent): accuracy re-run and record

- [ ] **Step 1:** Launch detached (hours): `Start-Process -FilePath .venv\Scripts\python.exe -ArgumentList '-u','examples\v0_angle_check.py' -RedirectStandardOutput out\angle_check_small_cycle.log -RedirectStandardError out\angle_check_small_cycle.err -NoNewWindow`; watch the log with a Monitor that re-arms every 30 minutes.
- [ ] **Step 2:** Record the table in `docs/m4-handoff.md` under a new heading "Small-cycle accuracy check" next to the v0a-2 results: per design the winding (wire, N, paths, strands, J_rms), feasibility at margin 1.05, and the variant deltas; state whether 80 x 80 is within 2 % of 160 x 160 at N_THETA 361 for each design.
- [ ] **Step 3:** Commit: `docs: small-cycle accuracy check results`.
