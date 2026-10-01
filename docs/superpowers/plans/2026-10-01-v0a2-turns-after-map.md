# v0a-2 Turns and Wire After the Map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Choose turns per pole, wire, parallel strands and phase current after one FEM map per geometry, in a wire mode (default when wires are given) and a density mode, and raise stage 2 to the `full` preset with a recorded accuracy check.

**Architecture:** The map is built at a fixed reference turn count over the largest ampere-turns any allowed winding can carry. `rescale_turns` turns that map into the map of any turn count exactly (current ÷ k, ψ × k). `choose_turns` scans every allowed winding through the existing drive envelope and picks one by the mode's rule. Stage 1 works in ampere-turns, so it does not depend on turns.

**Tech Stack:** Python 3.12+, numpy, scipy, pydantic v2, pytest; `srmcore` (`build_map`, `MapResult`, `key_numbers`).

**Spec:** `docs/superpowers/specs/2026-10-01-v0a2-turns-after-map-design.md` (addendum to `docs/superpowers/specs/2026-09-30-v0-walking-skeleton-design.md`).

## Global Constraints

- Python 3.12 or newer. Run everything with `.venv\Scripts\python` from the repo root `D:\y\srm-designer`.
- `srmapp` imports `srmcore` public modules; `srmcore` never imports `srmapp` (`tests/app/test_app_layering.py`).
- SI units everywhere (metres, m², A, A/m², Ω, kg). Wire sizes above 0.02 m are rejected as millimetres.
- `phase_current_a` is the inverter's peak phase current: required in wire mode, an optional cap in density mode.
- `max_slot_fill` defaults to 0.6 (outer-area basis), must be in (0, 0.9].
- Default `j_limit` (cooling limit, wire mode) is 20 A/mm² = `20e6` A/m²; default `j_peak` (density mode) stays `20e6`.
- Resistance at 100 °C, poles of a phase in series.
- Reference turns for every map: `REFERENCE_TURNS = 20`.
- Generator mesh preset `full`; stage-2 grid defaults to the preset grid (30 × 20).
- Comments describe the code as it is, never task or plan history.
- Test file basenames must be unique (`tests/` has no `__init__.py`); app tests are named `tests/app/test_app_*.py`.
- Imports in tests: `from conftest import make_8_6`, `from map_fixtures import synthetic_map` (both on the pytest path).
- Commit messages end with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## Review Focus

1. A wire too thick for even one turn in the slot → that wire contributes no windings; if no wire fits, the evaluation has status `no_winding`, not a crash (Task 3, Task 7 tests).
2. A phase current so high that even the most strands at one turn exceed `j_limit` → no windings for that wire; same `no_winding` outcome (Task 3, Task 7 tests).
3. Wire sizes typed in millimetres (`diameter=1.0`) → validation error naming millimetres (Task 1 test).
4. Wires given without `phase_current_a` → validation error (Task 2 test).
5. A winding whose current exceeds the map's ampere-turn range → `envelope` raises `ValueError` instead of extrapolating silently; `max_mmf` covers every winding the scan can produce (Task 3 and Task 4 tests).

---

## File map

- Create `src/srmapp/wire.py` — `RoundWire`, `RectangularWire`, `LitzWire`, `Wire` (discriminated union).
- Modify `src/srmapp/requirements.py` — `wires`, `phase_current_a`, `max_slot_fill`, `wire_mode`.
- Modify `src/srmapp/sizing/estimates.py` — `J_LIMIT`, `Mass.iron`, `series_resistance`, `copper_mass`.
- Create `src/srmapp/sizing/winding.py` — `Winding`, `wire_windings`, `density_windings`, `max_mmf`, `DENSITY_MAX_TURNS`.
- Modify `src/srmapp/drive/envelope.py` — `current_limit`, `n_theta`, `n_on`, `n_off` keywords.
- Create `src/srmapp/turns.py` — `rescale_turns`, `speed_grid`, `requirement_ratios` (moved), `ScanPoint`, `TurnsChoice`, `choose_turns`.
- Modify `src/srmapp/sizing/stage1.py` — ampere-turn bound, iron-only mass limit, `Stage1.mmf`, `Stage1.i_map`.
- Modify `src/srmapp/sizing/generator.py` — `REFERENCE_TURNS`, 8 sampled dimensions, `full` preset.
- Modify `src/srmapp/evaluate.py` — `choose_turns` after the map, new `Evaluation` fields, `StageTwoGrid` preset default.
- Modify `src/srmapp/pipeline.py` — `j_limit` setting, pass-through.
- Modify `examples/v0_search.py`; create `examples/v0_angle_check.py`.
- Tests: create `tests/app/test_app_wire.py`, `tests/app/test_app_winding.py`, `tests/app/test_app_turns.py`; modify `test_app_requirements.py`, `test_app_envelope.py`, `test_app_stage1.py`, `test_app_generator.py`, `test_app_evaluate.py`, `test_app_pipeline.py`.
- Docs: `CLAUDE.md`, `docs/m4-handoff.md`.

---

### Task 1: Wire models

**Files:**
- Create: `src/srmapp/wire.py`
- Test: `tests/app/test_app_wire.py`

**Interfaces:**
- Produces: `RoundWire(diameter, outer_diameter)`, `RectangularWire(width, height, insulation)`, `LitzWire(strand_diameter, strands, outer_diameter)`; each has `kind` (literal `"round"`, `"rectangular"`, `"litz"`), `copper_area: float` (m²) and `outer_area: float` (m²) properties. `Wire` = discriminated union on `kind`.

- [ ] **Step 1: Write the failing tests**

```python
import math

import pytest
from pydantic import TypeAdapter, ValidationError

from srmapp.wire import LitzWire, RectangularWire, RoundWire, Wire


def test_round_areas():
    w = RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3)
    assert w.kind == "round"
    assert w.copper_area == pytest.approx(math.pi * 1.0e-6 / 4)
    assert w.outer_area == pytest.approx(math.pi * 1.08e-3**2 / 4)


def test_round_insulation_cannot_be_thinner_than_the_copper():
    with pytest.raises(ValidationError, match="outer_diameter"):
        RoundWire(diameter=1.0e-3, outer_diameter=0.9e-3)


def test_rectangular_areas():
    w = RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3)
    assert w.copper_area == pytest.approx(2.0e-6)
    assert w.outer_area == pytest.approx(2.1e-3 * 1.1e-3)
    assert RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.0).outer_area == pytest.approx(2.0e-6)


def test_litz_areas():
    w = LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3)
    assert w.copper_area == pytest.approx(60 * math.pi * 0.1e-3**2 / 4)
    assert w.outer_area == pytest.approx(math.pi * 1.1e-3**2 / 4)


def test_litz_bundle_must_hold_its_strands():
    with pytest.raises(ValidationError, match="outer_diameter"):
        LitzWire(strand_diameter=0.1e-3, strands=100, outer_diameter=0.5e-3)


@pytest.mark.parametrize("make", [
    lambda: RoundWire(diameter=1.0, outer_diameter=1.08),
    lambda: RectangularWire(width=2.0, height=1.0, insulation=0.05),
    lambda: LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1),
])
def test_millimetre_looking_sizes_are_rejected(make):
    with pytest.raises(ValidationError, match="millimetres"):
        make()


def test_positive_sizes_and_strands():
    with pytest.raises(ValidationError):
        RoundWire(diameter=0.0, outer_diameter=1e-3)
    with pytest.raises(ValidationError):
        LitzWire(strand_diameter=0.1e-3, strands=0, outer_diameter=1.1e-3)
    with pytest.raises(ValidationError):
        RectangularWire(width=2e-3, height=1e-3, insulation=-1e-5)


def test_union_parses_by_kind():
    w = TypeAdapter(Wire).validate_python({"kind": "litz", "strand_diameter": 1e-4, "strands": 60,
                                           "outer_diameter": 1.1e-3})
    assert isinstance(w, LitzWire)
    with pytest.raises(ValidationError):
        TypeAdapter(Wire).validate_python({"kind": "hexagonal", "diameter": 1e-3})
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_wire.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'srmapp.wire'`.

- [ ] **Step 3: Implement**

```python
"""Winding wire described by its dimensions (v0a-2 spec §3.1). Sizes in metres. `copper_area` is the copper
cross-section of one conductor; `outer_area` includes the insulation and is what the slot fill counts."""
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A wire size above this looks like millimetres typed as metres.
_MAX_SIZE = 0.02   # m


class _Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def _metres(self):
        for name, value in self:
            if isinstance(value, float) and value > _MAX_SIZE:
                raise ValueError(f"{name}={value} looks like millimetres; wire sizes are in metres")
        return self


class RoundWire(_Wire):
    kind: Literal["round"] = "round"
    diameter: float = Field(gt=0)          # bare copper
    outer_diameter: float = Field(gt=0)    # over the insulation

    @model_validator(mode="after")
    def _insulated(self):
        if self.outer_diameter < self.diameter:
            raise ValueError("outer_diameter must not be below the bare diameter")
        return self

    @property
    def copper_area(self) -> float:
        return math.pi * self.diameter**2 / 4

    @property
    def outer_area(self) -> float:
        return math.pi * self.outer_diameter**2 / 4


class RectangularWire(_Wire):
    """Corner radius ignored."""
    kind: Literal["rectangular"] = "rectangular"
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    insulation: float = Field(ge=0)        # thickness on each side

    @property
    def copper_area(self) -> float:
        return self.width * self.height

    @property
    def outer_area(self) -> float:
        return (self.width + 2 * self.insulation) * (self.height + 2 * self.insulation)


class LitzWire(_Wire):
    """Litz or other multistrand conductor: `strands` round strands in a round bundle."""
    kind: Literal["litz"] = "litz"
    strand_diameter: float = Field(gt=0)
    strands: int = Field(ge=1)
    outer_diameter: float = Field(gt=0)    # bundle, over the serving or insulation

    @model_validator(mode="after")
    def _holds_strands(self):
        if self.outer_area < self.copper_area:
            raise ValueError("outer_diameter is too small to hold the strands")
        return self

    @property
    def copper_area(self) -> float:
        return self.strands * math.pi * self.strand_diameter**2 / 4

    @property
    def outer_area(self) -> float:
        return math.pi * self.outer_diameter**2 / 4


Wire = Annotated[RoundWire | RectangularWire | LitzWire, Field(discriminator="kind")]
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_wire.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/wire.py tests/app/test_app_wire.py
git commit -m "feat(app): wire models by dimensions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Requirements for wire mode

**Files:**
- Modify: `src/srmapp/requirements.py`
- Test: `tests/app/test_app_requirements.py` (append)

**Interfaces:**
- Consumes: `Wire` from Task 1.
- Produces: `Requirements.wires: tuple[Wire, ...] = ()`, `Requirements.phase_current_a: float | None = None`, `Requirements.max_slot_fill: float = 0.6`, property `Requirements.wire_mode -> bool` (True when `wires` is non-empty).

- [ ] **Step 1: Write the failing tests** (append to `tests/app/test_app_requirements.py`)

```python
from srmapp.wire import RoundWire

_WIRE = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)


def test_density_mode_by_default():
    r = _ok()
    assert r.wires == () and not r.wire_mode
    assert r.phase_current_a is None and r.max_slot_fill == 0.6


def test_wire_mode_needs_a_phase_current():
    with pytest.raises(ValidationError, match="phase_current_a"):
        _ok(wires=[_WIRE])
    r = _ok(wires=[_WIRE], phase_current_a=150.0)
    assert r.wire_mode and isinstance(r.wires[0], RoundWire)


def test_density_mode_accepts_a_current_cap():
    assert _ok(phase_current_a=200.0).phase_current_a == 200.0


@pytest.mark.parametrize("fill", [0.0, 0.95])
def test_slot_fill_range(fill):
    with pytest.raises(ValidationError):
        _ok(max_slot_fill=fill)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_requirements.py -q`
Expected: the four new tests FAIL (extra fields forbidden / no `wire_mode`).

- [ ] **Step 3: Implement**

In `src/srmapp/requirements.py` add `from .wire import Wire`, then add these fields after `max_mass_kg`:

```python
    wires: tuple[Wire, ...] = ()                                   # wire mode when non-empty
    phase_current_a: float | None = Field(default=None, gt=0)      # inverter peak phase current, A
    max_slot_fill: float = Field(default=0.6, gt=0, le=0.9)        # outer wire area / coil-side area
```

and this check at the top of `_consistent`, plus the property:

```python
        if self.wires and self.phase_current_a is None:
            raise ValueError("wire mode (wires given) needs phase_current_a")
```

```python
    @property
    def wire_mode(self) -> bool:
        return bool(self.wires)
```

Update the module docstring to: `"""Vehicle-motor requirements (v0 spec §3, v0a-2 spec §3.2). Peak-only: no continuous rating. Wire mode when wires are given, density mode otherwise."""`

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_requirements.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/requirements.py tests/app/test_app_requirements.py
git commit -m "feat(app): wire-mode requirements

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Windings a geometry can carry

**Files:**
- Modify: `src/srmapp/sizing/estimates.py`
- Create: `src/srmapp/sizing/winding.py`
- Test: `tests/app/test_app_winding.py`

**Interfaces:**
- Consumes: `Requirements` (Task 2), `coil_side_area`, `mean_turn_length`, `conductor_area` in `estimates`.
- Produces (estimates): `J_LIMIT = 20e6`; `Mass.iron` property; `series_resistance(p, turns, copper_area, temperature_c=100.0) -> float`; `copper_mass(p, turns, copper_area) -> float`. `phase_resistance` and `active_mass` keep their signatures and results.
- Produces (winding): `Winding(turns: int, strands: int, copper_area: float, current: float, resistance: float, copper_mass: float, wire: int | None)` with property `current_density`; `wire_windings(p, req, wire: int, j_limit: float) -> list[Winding]`; `density_windings(p, req, j_peak: float, max_turns: int = DENSITY_MAX_TURNS) -> list[Winding]`; `max_mmf(p, req, j_peak: float, j_limit: float) -> float`; `DENSITY_MAX_TURNS = 500`. Lists are in increasing turns.

- [ ] **Step 1: Write the failing tests**

```python
import math

import pytest
from conftest import make_8_6

from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.winding import density_windings, max_mmf, wire_windings

P = make_8_6()
A = est.coil_side_area(P)
THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)    # a few turns fit: fast scans
THIN = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def test_series_resistance_and_copper_mass_reproduce_the_reference_winding():
    assert est.series_resistance(P, P.turns_per_pole, est.conductor_area(P)) == pytest.approx(est.phase_resistance(P))
    assert est.copper_mass(P, P.turns_per_pole, est.conductor_area(P)) == pytest.approx(est.active_mass(P).copper)
    m = est.active_mass(P)
    assert m.iron == pytest.approx(m.stator_iron + m.rotor_iron)


def test_wire_windings_fill_the_slot_with_the_most_strands():
    req = _req(wires=[THIN], phase_current_a=100.0)
    room = req.max_slot_fill * A / req.wires[0].outer_area
    ws = wire_windings(P, req, 0, 20e6)
    assert ws and [w.turns for w in ws] == sorted(w.turns for w in ws)
    for w in ws:
        assert w.turns * w.strands <= room * (1 + 1e-9)
        assert w.turns * (w.strands + 1) > room
        assert w.copper_area == pytest.approx(w.strands * req.wires[0].copper_area)
        assert w.current == 100.0 and w.wire == 0
        assert w.current_density <= 20e6 * (1 + 1e-9)
        assert w.resistance == pytest.approx(est.series_resistance(P, w.turns, w.copper_area))
        assert w.copper_mass == pytest.approx(est.copper_mass(P, w.turns, w.copper_area))


def test_wire_resistance_grows_with_turns():
    ws = wire_windings(P, _req(wires=[THIN], phase_current_a=100.0), 0, 20e6)
    r = [w.resistance for w in ws]
    assert all(b > a for a, b in zip(r, r[1:]))


def test_current_density_limit_drops_turn_counts():
    req = _req(wires=[THIN], phase_current_a=100.0)
    loose, tight = wire_windings(P, req, 0, 50e6), wire_windings(P, req, 0, 5e6)
    assert len(tight) < len(loose)
    assert all(w.current_density <= 5e6 * (1 + 1e-9) for w in tight)


def test_wire_too_thick_for_one_turn_gives_nothing():
    huge = dict(kind="round", diameter=19e-3, outer_diameter=19.9e-3)
    assert wire_windings(P, _req(wires=[huge], phase_current_a=10.0), 0, 20e6) == []


def test_current_too_high_for_any_turn_count_gives_nothing():
    assert wire_windings(P, _req(wires=[THICK], phase_current_a=1e6), 0, 20e6) == []


def test_density_windings():
    ws = density_windings(P, _req(), 20e6, max_turns=50)
    assert [w.turns for w in ws] == list(range(1, 51))
    for w in ws:
        assert w.strands == 1 and w.wire is None
        assert w.copper_area == pytest.approx(P.fill_factor * A / w.turns)
        assert w.current_density == pytest.approx(20e6)


def test_density_current_cap():
    ws = density_windings(P, _req(phase_current_a=200.0), 20e6, max_turns=50)
    assert ws and all(w.current <= 200.0 * (1 + 1e-9) for w in ws)
    assert ws[0].turns == math.ceil(20e6 * P.fill_factor * A / 200.0 - 1e-9)


@pytest.mark.parametrize("wires", [[THIN], [THICK], [THIN, THICK]])
def test_max_mmf_covers_every_wire_winding(wires):
    req = _req(wires=wires, phase_current_a=60.0)
    top = max_mmf(P, req, 20e6, 20e6)
    for i in range(len(wires)):
        assert all(w.turns * w.current <= top * (1 + 1e-9) for w in wire_windings(P, req, i, 20e6))


def test_max_mmf_density_mode():
    assert max_mmf(P, _req(), 20e6, 99e6) == pytest.approx(20e6 * P.fill_factor * A)
    assert all(w.turns * w.current <= max_mmf(P, _req(), 20e6, 20e6) * (1 + 1e-9)
               for w in density_windings(P, _req(), 20e6, max_turns=50))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_winding.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'srmapp.sizing.winding'`.

- [ ] **Step 3: Implement estimates helpers**

In `src/srmapp/sizing/estimates.py`, below `J_PEAK`:

```python
# Default cooling limit on the conductor current density in wire mode, A/m². Provisional: a thermal model replaces it.
J_LIMIT = 20e6
```

Add to `Mass`:

```python
    @property
    def iron(self) -> float:
        return self.stator_iron + self.rotor_iron
```

Add these functions and route the existing ones through them:

```python
def series_resistance(p: RadialSRMParams, turns: int, copper_area: float, temperature_c: float = 100.0) -> float:
    """One phase at `temperature_c`, its poles in series, `turns` per pole, each turn of `copper_area` (m²)."""
    copper = load_material(p.materials.coil)
    rho = copper.resistivity * (1 + copper.temperature_coefficient * (temperature_c - copper.reference_temperature_c))
    return rho * turns * p.n_stator_poles / p.n_phases * mean_turn_length(p) / copper_area


def copper_mass(p: RadialSRMParams, turns: int, copper_area: float) -> float:
    """Copper of all coils, `turns` per pole, each turn of `copper_area` (m²)."""
    return load_material(p.materials.coil).density * p.n_stator_poles * turns * copper_area * mean_turn_length(p)
```

Replace the body of `phase_resistance` with `return series_resistance(p, p.turns_per_pole, conductor_area(p), temperature_c)`, and in `active_mass` replace the copper lines with `copper=copper_mass(p, p.turns_per_pole, conductor_area(p))` (drop the now-unused `copper = load_material(...)` and `copper_volume` lines).

- [ ] **Step 4: Implement `src/srmapp/sizing/winding.py`**

```python
"""Windings a geometry can carry (v0a-2 spec §3). Wire mode fixes the wire and the phase current and fits as
many parallel strands as the slot holds; density mode fixes the current density. Poles of a phase are in series."""
import math
from dataclasses import dataclass

from srmcore.model.design import RadialSRMParams

from ..requirements import Requirements
from .estimates import coil_side_area, copper_mass, series_resistance

DENSITY_MAX_TURNS = 500     # upper end of the density-mode turn scan
_EPS = 1e-9


@dataclass(frozen=True)
class Winding:
    turns: int             # per pole
    strands: int           # parallel conductors per turn
    copper_area: float     # m², one turn, all strands
    current: float         # A, peak phase current
    resistance: float      # Ω, one phase at 100 °C
    copper_mass: float     # kg, all coils
    wire: int | None       # index into Requirements.wires; None in density mode

    @property
    def current_density(self) -> float:
        return self.current / self.copper_area


def _winding(p: RadialSRMParams, turns: int, strands: int, copper_area: float, current: float,
             wire: int | None) -> Winding:
    return Winding(turns, strands, copper_area, current, series_resistance(p, turns, copper_area),
                   copper_mass(p, turns, copper_area), wire)


def wire_windings(p: RadialSRMParams, req: Requirements, wire: int, j_limit: float) -> list[Winding]:
    """Every turn count `req.wires[wire]` can wind at `req.phase_current_a`, each with as many parallel strands as
    fit in `req.max_slot_fill` of the coil side, keeping the current density within `j_limit`. Increasing turns."""
    w = req.wires[wire]
    room = req.max_slot_fill * coil_side_area(p) / w.outer_area     # conductors that fit in one coil side
    out = []
    for turns in range(1, math.floor(room + _EPS) + 1):
        strands = math.floor(room / turns + _EPS)
        area = strands * w.copper_area
        if req.phase_current_a / area <= j_limit * (1 + _EPS):
            out.append(_winding(p, turns, strands, area, req.phase_current_a, wire))
    return out


def density_windings(p: RadialSRMParams, req: Requirements, j_peak: float,
                     max_turns: int = DENSITY_MAX_TURNS) -> list[Winding]:
    """Turn counts 1..max_turns at current density `j_peak` in `p.fill_factor` of the coil side; turn counts whose
    peak current exceeds `req.phase_current_a` (when set) are left out. Increasing turns."""
    copper = p.fill_factor * coil_side_area(p)
    out = []
    for turns in range(1, max_turns + 1):
        area = copper / turns
        current = j_peak * area
        if req.phase_current_a is None or current <= req.phase_current_a * (1 + _EPS):
            out.append(_winding(p, turns, 1, area, current, None))
    return out


def max_mmf(p: RadialSRMParams, req: Requirements, j_peak: float, j_limit: float) -> float:
    """Largest peak ampere-turns per pole any allowed winding carries (spec §3.3); the map must cover it."""
    a = coil_side_area(p)
    if req.wire_mode:
        return j_limit * req.max_slot_fill * a * max(w.copper_area / w.outer_area for w in req.wires)
    return j_peak * p.fill_factor * a
```

- [ ] **Step 5: Run the new and the existing estimate tests**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_winding.py tests/app/test_app_estimates.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/srmapp/sizing/estimates.py src/srmapp/sizing/winding.py tests/app/test_app_winding.py
git commit -m "feat(app): wire-mode and density-mode windings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Exact turns rescale and envelope current limit

**Files:**
- Modify: `src/srmapp/drive/envelope.py`
- Create: `src/srmapp/turns.py` (only `rescale_turns` in this task)
- Test: `tests/app/test_app_envelope.py` (append), `tests/app/test_app_turns.py` (create)

**Interfaces:**
- Produces: `envelope(result, machine, bus_voltage, resistance, speeds_rpm, *, current_limit: float | None = None, n_theta: int = N_THETA, n_on: int = N_ON, n_off: int = N_OFF) -> Envelope`. `current_limit=None` means the map's top current. A limit outside (0, top·(1+1e-6)] raises `ValueError` containing `"current limit"`.
- Produces: `rescale_turns(result: MapResult, k: float) -> MapResult` (k = new turns / map turns).

- [ ] **Step 1: Write the failing envelope tests** (append to `tests/app/test_app_envelope.py`)

```python
def test_current_limit_scales_the_low_speed_torque_with_the_square_of_the_current():
    full, half = _env(), _env_limited(10.0)
    assert half.torque[0] == pytest.approx(0.25 * full.torque[0], rel=0.03)


def _env_limited(limit, volts=400.0, r=0.0):
    return envelope(synthetic_map(n_angles=24), MACHINE, volts, r, SPEEDS, current_limit=limit)


@pytest.mark.parametrize("limit", [0.0, -1.0, 20.5])
def test_current_limit_outside_the_map_is_rejected(limit):
    with pytest.raises(ValueError, match="current limit"):
        _env_limited(limit)


def test_finer_drive_discretisation_agrees_at_low_speed():
    coarse = _env()
    fine = envelope(synthetic_map(n_angles=24), MACHINE, 400.0, 0.0, SPEEDS, n_theta=361, n_on=80, n_off=80)
    assert fine.torque[0] == pytest.approx(coarse.torque[0], rel=0.02)
```

- [ ] **Step 2: Write the failing rescale tests** (`tests/app/test_app_turns.py`)

```python
import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive.envelope import envelope
from srmapp.turns import rescale_turns

MACHINE = make_8_6()
SPEEDS = np.array([100.0, 1500.0, 6000.0, 12000.0])


def test_rescale_moves_current_and_flux_and_keeps_torque_and_energy():
    r = synthetic_map(n_angles=16)
    s = rescale_turns(r, 2.0)
    np.testing.assert_allclose(s.currents, r.currents / 2)
    np.testing.assert_allclose(s.psi, 2 * r.psi)
    np.testing.assert_allclose(s.l_inc, 4 * r.l_inc)
    for name in ("torque_arkkio", "torque_virtual_work", "energy", "coenergy", "pole_force", "b_peak"):
        np.testing.assert_array_equal(getattr(s, name), getattr(r, name))
    assert s.angles is r.angles and s.complete == r.complete


def test_rescaled_drive_equals_the_original_at_scaled_voltage():
    # k times the turns: ψ' = kψ, i' = i/k, R' = k²R, so dψ/dt = V/k − R·i on the original map
    r, k, res = synthetic_map(n_angles=24), 3.0, 0.2
    scaled = envelope(rescale_turns(r, k), MACHINE, 300.0, k * k * res, SPEEDS, current_limit=20.0 / k)
    original = envelope(r, MACHINE, 300.0 / k, res, SPEEDS, current_limit=20.0)
    np.testing.assert_allclose(scaled.torque, original.torque, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(scaled.copper_loss, original.copper_loss, rtol=1e-9, atol=1e-12)


@pytest.mark.slow
def test_fem_map_at_double_turns_matches_the_rescale():
    pytest.importorskip("ngsolve")
    from srmcore.maps import build_map
    from srmcore.model.design import Design, MeshSettings

    def run(turns, i_max):
        design = Design(machine=make_8_6(turns_per_pole=turns), mesh=MeshSettings(preset="screening"))
        return build_map(design, i_max, n_angles=6, n_currents=4, workers=2)
    base, double = run(40, 20.0), run(80, 10.0)
    predicted = rescale_turns(base, 2.0)
    np.testing.assert_allclose(double.currents, predicted.currents, rtol=1e-12)
    psi_scale = np.max(np.abs(double.psi))
    np.testing.assert_allclose(double.psi, predicted.psi, rtol=1e-6, atol=1e-7 * psi_scale)
    t_scale = np.max(np.abs(double.torque_arkkio))
    np.testing.assert_allclose(double.torque_arkkio, predicted.torque_arkkio, rtol=1e-6, atol=1e-7 * t_scale)
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_envelope.py tests/app/test_app_turns.py -q -m "not slow"`
Expected: new tests FAIL (`unexpected keyword argument 'current_limit'`, `No module named 'srmapp.turns'`).

- [ ] **Step 4: Implement the envelope keywords**

In `src/srmapp/drive/envelope.py`:

Change `_tables` to take the top current and angle count:

```python
def _tables(result: MapResult, period: float, i_top: float, n_theta: int) -> _Tables:
    e = result.circuits.index(result.excited)
    current = np.linspace(0.0, i_top, N_CURRENT)
    psi = PchipInterpolator(result.currents, result.psi[..., e], axis=1)(current)
    torque = PchipInterpolator(result.currents, result.torque_arkkio, axis=1)(current)
    theta = np.linspace(0.0, period, n_theta)
    psi_f = angle_spline(result.angles, psi, period)(theta)
    torque_f = angle_spline(result.angles, torque, period)(theta)
    return _Tables(theta, current, np.maximum.accumulate(np.maximum(psi_f, 0.0), axis=1), torque_f)
```

Update the `_Tables` field comments from `(N_THETA,)` / `(N_THETA, N_CURRENT)` to `(n_theta,)` / `(n_theta, N_CURRENT)` and `0..I_max` to `0..current limit`.

Change `envelope`:

```python
def envelope(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float,
             speeds_rpm, *, current_limit: float | None = None, n_theta: int = N_THETA, n_on: int = N_ON,
             n_off: int = N_OFF) -> Envelope:
    """`current_limit` (A) is the hysteresis limit, at most the map's top current (the default)."""
    require_complete(result)
    if result.excited != "A":
        raise ValueError("the envelope needs the phase A map (excited='A')")
    top_current = float(result.currents[-1])
    i_top = top_current if current_limit is None else float(current_limit)
    if not 0 < i_top <= top_current * (1 + 1e-6):
        raise ValueError(f"current limit {i_top} A is outside the map's range (0, {top_current}] A")
    period = 2 * math.pi / machine.n_rotor_poles
    t = _tables(result, period, i_top, n_theta)
    top = n_theta - 1
    on_axis = np.unique(np.round(np.linspace(*ON_RANGE, n_on) * top).astype(int))
    off_axis = np.unique(np.round(np.linspace(*OFF_RANGE, n_off) * top).astype(int))
```

(the rest of the function is unchanged). Update the module docstring's first sentence to say the current limit defaults to the map's I_max: `Single-pulse voltage control with a hysteresis current limit (the map's I_max unless given), ...`.

- [ ] **Step 5: Implement `src/srmapp/turns.py`**

```python
"""Turns, wire and current chosen after the map (v0a-2 spec §2-3)."""
import dataclasses

from srmcore.maps import MapResult


def rescale_turns(result: MapResult, k: float) -> MapResult:
    """The map of the same geometry with k times the turns per pole. The 2D field depends only on the ampere-turns,
    so the current axis divides by k and flux linkage multiplies by k; torque, energy, forces and flux density at
    a given ampere-turns are unchanged, and L_inc scales by k²."""
    return dataclasses.replace(result, currents=result.currents / k, psi=result.psi * k,
                               l_inc=result.l_inc * (k * k))
```

- [ ] **Step 6: Run the fast tests**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_envelope.py tests/app/test_app_turns.py -q -m "not slow"`
Expected: all pass.

- [ ] **Step 7: Run the slow exactness test**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_turns.py -q -m slow`
Expected: PASS (a few minutes). If it fails, report the largest relative ψ and torque differences; do not loosen the tolerances.

- [ ] **Step 8: Commit**

```bash
git add src/srmapp/drive/envelope.py src/srmapp/turns.py tests/app/test_app_envelope.py tests/app/test_app_turns.py
git commit -m "feat(app): exact turns rescale and envelope current limit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Turns scan

**Files:**
- Modify: `src/srmapp/turns.py`, `src/srmapp/evaluate.py` (move `speed_grid`, `requirement_ratios` out; import them back)
- Test: `tests/app/test_app_turns.py` (append)

**Interfaces:**
- Consumes: `rescale_turns`, `envelope(..., current_limit=...)` (Task 4); `Winding`, `wire_windings`, `density_windings`, `max_mmf`, `DENSITY_MAX_TURNS` (Task 3); `J_PEAK`, `J_LIMIT`.
- Produces in `srmapp.turns`: `speed_grid(req, n=12)`, `requirement_ratios(env, req)` (moved unchanged; `srmapp.evaluate` re-imports them so existing imports keep working); `ScanPoint(winding: Winding, torque_ratio: float, power_ratio: float)` with properties `worst` and `feasible`; `TurnsChoice(point: ScanPoint | None, feasible: bool, envelope: Envelope | None, scan: tuple[ScanPoint, ...])`; `choose_turns(result, machine, req, *, j_peak=J_PEAK, j_limit=J_LIMIT, max_turns=DENSITY_MAX_TURNS) -> TurnsChoice`. `machine.turns_per_pole` is the map's reference turns.

- [ ] **Step 1: Write the failing tests** (append to `tests/app/test_app_turns.py`)

```python
from srmapp.requirements import Requirements
from srmapp.sizing.winding import max_mmf
from srmapp.turns import choose_turns, speed_grid

THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)
THICKER = dict(kind="rectangular", width=7.0e-3, height=4.0e-3, insulation=0.1e-3)


def _req(**kw):
    values = dict(peak_power_w=10.47, peak_torque_nm=0.1, base_speed_rpm=1000.0, max_speed_rpm=2000.0)
    values.update(kw)
    return Requirements(**values)


def _map_for(req, j_peak=20e6, j_limit=20e6):
    top = max_mmf(MACHINE, req, j_peak, j_limit) / MACHINE.turns_per_pole
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, top, 9))


def test_wire_mode_picks_the_lowest_resistance_feasible_winding():
    req = _req(wires=[THICK, THICKER], phase_current_a=100.0)
    c = choose_turns(_map_for(req), MACHINE, req)
    assert c.point is not None and c.feasible and c.point.feasible
    feasible = [s for s in c.scan if s.feasible]
    assert c.point.winding.resistance == min(s.winding.resistance for s in feasible)
    same_wire = [s.winding.turns for s in feasible if s.winding.wire == c.point.winding.wire]
    assert c.point.winding.turns == min(same_wire)
    assert {s.winding.wire for s in c.scan} == {0, 1}


def test_density_mode_picks_the_most_turns():
    req = _req()
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40)
    assert c.feasible
    assert c.point.winding.turns == max(s.winding.turns for s in c.scan if s.feasible)
    assert len(c.scan) == 40


def test_density_current_cap_limits_the_scan():
    req = _req(phase_current_a=200.0)
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40)
    assert c.scan and all(s.winding.current <= 200.0 * (1 + 1e-9) for s in c.scan)


def test_infeasible_requirement_reports_the_closest_winding():
    req = _req(peak_torque_nm=1e4, peak_power_w=1.047e6)
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=20)
    assert not c.feasible and c.point is not None and not c.point.feasible
    assert c.point.worst == max(s.worst for s in c.scan)


def test_no_winding_when_nothing_fits():
    req = _req(wires=[THICK], phase_current_a=1e6)
    c = choose_turns(synthetic_map(n_angles=24), MACHINE, req)
    assert c.point is None and not c.feasible and c.envelope is None and c.scan == ()


def test_chosen_envelope_covers_the_full_speed_grid_and_matches_the_scan_ratios():
    req = _req(wires=[THICK], phase_current_a=100.0)
    c = choose_turns(_map_for(req), MACHINE, req)
    np.testing.assert_array_equal(c.envelope.speeds_rpm, speed_grid(req))
    from srmapp.turns import requirement_ratios
    assert requirement_ratios(c.envelope, req) == pytest.approx((c.point.torque_ratio, c.point.power_ratio))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_turns.py -q -m "not slow"`
Expected: new tests FAIL (`cannot import name 'choose_turns'`).

- [ ] **Step 3: Move `speed_grid` and `requirement_ratios`**

Cut both functions (unchanged bodies and docstrings) from `src/srmapp/evaluate.py` into `src/srmapp/turns.py`. In `evaluate.py` add `from .turns import requirement_ratios, speed_grid` so `from srmapp.evaluate import requirement_ratios, speed_grid` keeps working.

- [ ] **Step 4: Implement the scan in `src/srmapp/turns.py`**

Full module after this step:

```python
"""Turns, wire and current chosen after the map (v0a-2 spec §2-3)."""
import dataclasses
from dataclasses import dataclass

import numpy as np

from srmcore.maps import MapResult
from srmcore.model.design import RadialSRMParams

from .drive.envelope import Envelope, envelope
from .requirements import Requirements
from .sizing.estimates import J_LIMIT, J_PEAK
from .sizing.winding import DENSITY_MAX_TURNS, Winding, density_windings, wire_windings


def rescale_turns(result: MapResult, k: float) -> MapResult:
    """The map of the same geometry with k times the turns per pole. The 2D field depends only on the ampere-turns,
    so the current axis divides by k and flux linkage multiplies by k; torque, energy, forces and flux density at
    a given ampere-turns are unchanged, and L_inc scales by k²."""
    return dataclasses.replace(result, currents=result.currents / k, psi=result.psi * k,
                               l_inc=result.l_inc * (k * k))


def speed_grid(req: Requirements, n: int = 12) -> np.ndarray:
    """Speeds in rpm from 10 % of base to the maximum; base and maximum speed are members exactly."""
    base, top = req.base_speed_rpm, req.max_speed_rpm
    return np.unique(np.concatenate([base * np.array([0.1, 0.25, 0.5]), np.linspace(base, top, n)]))


def requirement_ratios(env: Envelope, req: Requirements) -> tuple[float, float]:
    """(torque at base speed / required torque, lowest power between base and maximum speed / required power)."""
    torque_at_base = float(np.interp(req.base_speed_rpm, env.speeds_rpm, env.torque))
    band = (env.speeds_rpm >= req.base_speed_rpm) & (env.speeds_rpm <= req.max_speed_rpm)
    return torque_at_base / req.peak_torque_nm, float(np.min(env.power[band])) / req.peak_power_w


@dataclass(frozen=True)
class ScanPoint:
    winding: Winding
    torque_ratio: float     # achieved / required, at base speed
    power_ratio: float      # achieved / required, worst over base..max speed

    @property
    def worst(self) -> float:
        return min(self.torque_ratio, self.power_ratio)

    @property
    def feasible(self) -> bool:
        return self.worst >= 1.0


@dataclass(frozen=True)
class TurnsChoice:
    point: ScanPoint | None        # None when no winding meets the wire, current and current-density limits
    feasible: bool
    envelope: Envelope | None      # chosen winding over the full speed grid
    scan: tuple[ScanPoint, ...]    # every winding tried, in scan order


def _envelope(result: MapResult, machine: RadialSRMParams, req: Requirements, w: Winding, speeds) -> Envelope:
    return envelope(rescale_turns(result, w.turns / machine.turns_per_pole), machine, req.bus_voltage_v,
                    w.resistance, speeds, current_limit=w.current)


def choose_turns(result: MapResult, machine: RadialSRMParams, req: Requirements, *, j_peak: float = J_PEAK,
                 j_limit: float = J_LIMIT, max_turns: int = DENSITY_MAX_TURNS) -> TurnsChoice:
    """Scan every allowed winding on the map of `machine` (built at `machine.turns_per_pole`). Wire mode keeps the
    feasible winding with the lowest resistance; density mode keeps the feasible winding with the most turns. With
    no feasible winding, the one with the largest worst ratio is reported."""
    if req.wire_mode:
        windings = [w for i in range(len(req.wires)) for w in wire_windings(machine, req, i, j_limit)]
    else:
        windings = density_windings(machine, req, j_peak, max_turns)
    grid = speed_grid(req)
    band = grid[grid >= req.base_speed_rpm]
    scan = tuple(ScanPoint(w, *requirement_ratios(_envelope(result, machine, req, w, band), req)) for w in windings)
    if not scan:
        return TurnsChoice(None, False, None, ())
    feasible = [s for s in scan if s.feasible]
    if not feasible:
        point = max(scan, key=lambda s: (s.worst, -s.winding.resistance))
    elif req.wire_mode:
        # for one wire, resistance grows with turns (fewer strands fit), so this is also that wire's smallest N
        point = min(feasible, key=lambda s: (s.winding.resistance, s.winding.turns))
    else:
        point = max(feasible, key=lambda s: s.winding.turns)
    return TurnsChoice(point, bool(feasible), _envelope(result, machine, req, point.winding, grid), scan)
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_turns.py tests/app/test_app_evaluate.py -q -m "not slow"`
Expected: the turns tests pass; evaluate tests pass (they still use the old `evaluate_stage2`, which Task 7 replaces).

- [ ] **Step 6: Commit**

```bash
git add src/srmapp/turns.py src/srmapp/evaluate.py tests/app/test_app_turns.py
git commit -m "feat(app): turns scan over wire-mode and density-mode windings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Stage 1 in ampere-turns; generator at reference turns and `full`

**Files:**
- Modify: `src/srmapp/sizing/stage1.py`, `src/srmapp/sizing/generator.py`
- Test: `tests/app/test_app_stage1.py`, `tests/app/test_app_generator.py`

**Interfaces:**
- Consumes: `max_mmf` (Task 3), `J_LIMIT`, `Mass.iron`.
- Produces: `torque_upper_bound(p, mmf: float) -> float` (mmf = peak ampere-turns per pole); `Stage1(mass: Mass, mmf: float, i_map: float, torque_upper: float, passes: bool, reason: str)` where `i_map = mmf / p.turns_per_pole`; `stage1(req, p, margin=1.0, j_peak=J_PEAK, j_limit=J_LIMIT)`. Mass limit compares `mass.iron`. Generator: `REFERENCE_TURNS = 20`, `_DIMS = 8`, `MeshSettings(preset="full")`.

- [ ] **Step 1: Update the stage-1 tests**

Replace the bodies in `tests/app/test_app_stage1.py` as follows (keep `_req`, `test_small_motor_fails_a_large_torque_requirement`, `test_margin_tightens_the_filter`, `test_mass_precedence_over_torque`):

```python
def test_bound_sits_above_the_fem_static_peak_of_the_example_machine():
    # Sanity check only: the FEM static peak of this 8/6 at 20 A is 12.42 N·m (tests/maps/goldens_8_6.json).
    # A static peak is not a revolution average, so this only shows the bound is not absurdly low.
    p = make_8_6()
    assert torque_upper_bound(p, 20.0 * p.turns_per_pole) >= 12.42


def test_bound_scales_linearly_with_ampere_turns_and_stack():
    p = make_8_6()
    assert torque_upper_bound(p, 2400.0) == pytest.approx(2 * torque_upper_bound(p, 1200.0))
    q = make_8_6(stack_length=0.2)
    assert torque_upper_bound(q, 1200.0) == pytest.approx(2 * torque_upper_bound(p, 1200.0))


def test_stage1_does_not_depend_on_turns():
    a, b = stage1(_req(), make_8_6(turns_per_pole=40)), stage1(_req(), make_8_6(turns_per_pole=80))
    assert a.torque_upper == pytest.approx(b.torque_upper) and a.mmf == pytest.approx(b.mmf)
    assert a.i_map == pytest.approx(2 * b.i_map)


def test_easy_requirement_passes():
    s = stage1(_req(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0), make_8_6())
    assert s.passes and s.reason == ""
    assert s.mass.total > 0 and s.i_map > 0
    assert s.i_map == pytest.approx(s.mmf / make_8_6().turns_per_pole)


def test_mass_limit_uses_iron_only():
    p = make_8_6()
    m = est.active_mass(p)
    between = (m.iron + m.total) / 2          # above the iron, below iron plus reference copper
    assert stage1(_req(peak_power_w=1000.0, peak_torque_nm=3.2, max_mass_kg=between), p).passes
    s = stage1(_req(peak_power_w=1000.0, peak_torque_nm=3.2, max_mass_kg=0.5), p)
    assert not s.passes and "mass" in s.reason


def test_current_density_raises_the_bound_and_the_map_current():
    lo, hi = stage1(_req(), make_8_6(), j_peak=10e6), stage1(_req(), make_8_6(), j_peak=30e6)
    assert hi.i_map == pytest.approx(3 * lo.i_map)
    assert hi.torque_upper == pytest.approx(3 * lo.torque_upper)


def test_wire_mode_range_follows_the_cooling_limit():
    req = _req(wires=[dict(kind="round", diameter=1e-3, outer_diameter=1.08e-3)], phase_current_a=100.0)
    lo, hi = stage1(req, make_8_6(), j_limit=10e6), stage1(req, make_8_6(), j_limit=20e6)
    assert hi.mmf == pytest.approx(2 * lo.mmf)


def test_narrow_rotor_pole_does_not_lower_the_bound():
    p = make_8_6()
    narrow = p.model_copy(update={"rotor_pole_arc": p.rotor_pole_arc / 2})
    assert torque_upper_bound(narrow, 1200.0) == pytest.approx(torque_upper_bound(p, 1200.0))
```

Delete the old `test_bound_scales_linearly_with_current_and_stack`, `test_bound_does_not_depend_on_turns_at_fixed_current_density`, `test_mass_limit` and `test_current_density_raises_the_bound_and_the_current`.

- [ ] **Step 2: Update the generator tests** (`tests/app/test_app_generator.py`)

Replace `test_screening_preset_and_speed_are_set` with:

```python
def test_full_preset_reference_turns_and_speed_are_set():
    cands, _ = sample_candidates(_req(), 8, seed=0)
    assert all(c.design.mesh.preset == "full" for c in cands)
    assert all(c.design.machine.turns_per_pole == REFERENCE_TURNS for c in cands)
    assert cands[0].design.machine.max_speed_rpm == 9000.0
```

and change the import to `from srmapp.sizing.generator import POLE_SETS, REFERENCE_TURNS, sample_candidates`.

- [ ] **Step 3: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_stage1.py tests/app/test_app_generator.py -q`
Expected: FAIL (`Stage1` has no `mmf`; no `REFERENCE_TURNS`).

- [ ] **Step 4: Implement stage 1**

Replace `src/srmapp/sizing/stage1.py` from the imports down with:

```python
import math
from dataclasses import dataclass

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams

from ..requirements import Requirements
from .estimates import J_LIMIT, J_PEAK, Mass, active_mass, pole_chord
from .winding import max_mmf

# Allowance on the saturation flux for mu0*H beyond Js and fringing.
FLUX_ALLOWANCE = 1.1


def torque_upper_bound(p: RadialSRMParams, mmf: float) -> float:
    """Upper bound on the revolution-average torque (N·m) if every stroke converted the full rectangle
    ψ_sat·i_peak at `mmf` peak ampere-turns per pole. The flux through a pole is bounded by the stator pole body
    saturating at the stator material's saturation polarisation, taken at the bore chord (pole taper is ignored;
    the generator uses zero taper), and a phase has Ns/m poles in series, so ψ_sat·i_peak = (Ns/m)·Φ_sat·mmf, which
    does not depend on the turns. Each of the m·Nr strokes per revolution converts one rectangle."""
    stator = load_material(p.materials.stator)
    pole_area = pole_chord(p.bore_radius, p.stator_pole_arc) * p.stack_length * stator.stacking_factor
    flux_sat = FLUX_ALLOWANCE * stator.saturation_polarisation * pole_area
    return p.n_phases * p.n_rotor_poles * (p.n_stator_poles / p.n_phases) * flux_sat * mmf / (2 * math.pi)


@dataclass(frozen=True)
class Stage1:
    mass: Mass             # at the reference winding; the limit compares the iron only (the winding is chosen later)
    mmf: float             # peak ampere-turns per pole the map must cover
    i_map: float           # A, map I_max at the reference turns
    torque_upper: float    # N·m
    passes: bool
    reason: str            # empty when the design passes


def stage1(req: Requirements, p: RadialSRMParams, margin: float = 1.0, j_peak: float = J_PEAK,
           j_limit: float = J_LIMIT) -> Stage1:
    mass = active_mass(p)
    mmf = max_mmf(p, req, j_peak, j_limit)
    upper = torque_upper_bound(p, mmf)
    reason = ""
    if req.max_mass_kg is not None and mass.iron > req.max_mass_kg:
        reason = f"iron mass {mass.iron:.2f} kg above the {req.max_mass_kg:.2f} kg limit"
    elif upper < margin * req.peak_torque_nm:
        reason = f"torque upper bound {upper:.1f} N·m below the required {margin * req.peak_torque_nm:.1f} N·m"
    return Stage1(mass, mmf, mmf / p.turns_per_pole, upper, reason == "", reason)
```

Keep the module docstring; append to it: ` The mass limit compares the iron only, so it never drops a design whose winding is not yet chosen.`

- [ ] **Step 5: Implement the generator changes**

In `src/srmapp/sizing/generator.py`:
- Replace `_DIMS = 9` with `_DIMS = 8` and `_TURNS = (6, 120)` with `REFERENCE_TURNS = 20      # every map is built at these turns; stage 2 chooses the winding`.
- In `_machine`, delete the `turns = ...` line and pass `turns_per_pole=REFERENCE_TURNS`.
- In `sample_candidates`, use `MeshSettings(preset="full")`.
- Update the module docstring to: `"""Candidate generator: Latin-hypercube samples of radial SRM geometries inside a bounded box (v0 spec §4.1). Turns are not sampled: every candidate carries REFERENCE_TURNS and stage 2 chooses the winding (v0a-2 spec §4)."""`

- [ ] **Step 6: Update the pipeline call sites so the suite stays green**

In `src/srmapp/pipeline.py`:
- `from .sizing.estimates import J_LIMIT, J_PEAK`
- add `j_limit: float = J_LIMIT        # A/m², cooling limit on the conductor current density (wire mode)` to `SearchSettings` after `j_peak`.
- `scored = [(c, stage1(req, c.design.machine, settings.margin, settings.j_peak, settings.j_limit)) for c in candidates]`
- sort key: `cs[1].torque_upper / cs[1].mass.iron`.

In `src/srmapp/evaluate.py` replace `stage.i_peak` with `stage.i_map` everywhere (the `build_map` call, `_failed` and the final `Evaluation`). Task 7 rewrites this module; this keeps it running in between.

In `tests/app/test_app_pipeline.py` change the spy to:

```python
    def spy(req, p, margin, j_peak, j_limit):
        seen.append(j_peak)
        return real(req, p, margin, j_peak, j_limit)
```

and in `_fake` replace `stage.i_peak` with `stage.i_map` (both places).

- [ ] **Step 7: Run the app tests**

Run: `.venv\Scripts\python -m pytest tests/app -q -m "not slow"`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/srmapp tests/app
git commit -m "feat(app): stage 1 in ampere-turns, generator at reference turns and full preset

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Stage 2 chooses the winding

**Files:**
- Modify: `src/srmapp/evaluate.py`, `src/srmapp/pipeline.py`, `examples/v0_search.py`
- Test: `tests/app/test_app_evaluate.py`, `tests/app/test_app_pipeline.py`

**Interfaces:**
- Consumes: `choose_turns`, `rescale_turns`, `ScanPoint` (Tasks 4–5); `Stage1.i_map`, `Stage1.mass.iron` (Task 6); `Winding`, `DENSITY_MAX_TURNS`; `coil_side_area`.
- Produces: `StageTwoGrid(n_angles: int | None = None, n_currents: int | None = None)` (None = the design's preset grid). `Evaluation(id, design, status, error, mass_kg, winding: Winding | None, torque_ratio, power_ratio, peak_power_w, power_density_kw_per_kg, efficiency_base, feasible, envelope, key, scan: tuple[ScanPoint, ...] = ())`. `evaluate_stage2(candidate, req, stage, *, grid=StageTwoGrid(), j_peak=J_PEAK, j_limit=J_LIMIT, max_turns=DENSITY_MAX_TURNS, solver="ngsolve", workers=None, cache_dir=None, progress=None, cancel=None)`. On success `design.machine` carries the chosen `turns_per_pole` and `fill_factor = turns·copper_area / coil_side_area`. Status `"no_winding"` when no winding meets the limits.

- [ ] **Step 1: Rewrite the evaluate tests** (`tests/app/test_app_evaluate.py`)

Replace the whole file with:

```python
import math
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation, StageTwoGrid, evaluate_stage2, requirement_ratios, speed_grid
from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.generator import Candidate
from srmapp.sizing.stage1 import stage1
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError, MapFailed, MeshRejected, WorkerCrashed

THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _cand():
    return Candidate("c0", Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _map(stage):
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, stage.i_map, 9))


def _evaluate(req, **kw):
    stage = stage1(req, make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)), \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        return evaluate_stage2(_cand(), req, stage, max_turns=30, **kw), stage


def test_speed_grid_contains_base_and_max_exactly():
    g = speed_grid(_req())
    assert 3000.0 in g and 6000.0 in g
    assert np.all(np.diff(g) > 0) and g[0] < 3000.0


def test_requirement_ratios():
    speeds = np.array([300.0, 3000.0, 4500.0, 6000.0])
    torque = np.array([10.0, 4.0, 2.0, 1.0])
    power = torque * speeds * 2 * math.pi / 60
    env = Envelope(speeds, torque, power, np.zeros(4), np.zeros(4), np.ones(4), np.zeros(4), np.zeros(4))
    t_ratio, p_ratio = requirement_ratios(env, _req())
    assert t_ratio == pytest.approx(4.0 / 3.2)
    assert p_ratio == pytest.approx(min(power[1:]) / 1000.0)


def test_stage_two_grid_defaults_to_the_preset():
    assert StageTwoGrid() == StageTwoGrid(None, None)


def test_failed_map_becomes_an_evaluation_and_does_not_raise():
    with mock.patch("srmapp.evaluate.build_map", side_effect=MapFailed(["3 of 50 points failed"], 3)):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert isinstance(e, Evaluation)
    assert e.status == "MapFailed" and "3 of 50" in e.error
    assert not e.feasible and math.isnan(e.torque_ratio) and e.envelope is None and e.winding is None


def test_cancelled_map_is_reported():
    partial = synthetic_map(complete=False)
    with mock.patch("srmapp.evaluate.build_map", return_value=partial):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert e.status == "cancelled" and not e.feasible


def test_map_is_built_over_the_stage_one_range():
    stage = stage1(_req(), make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)) as bm, \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        evaluate_stage2(_cand(), _req(), stage, max_turns=5)
    assert bm.call_args.args[1] == stage.i_map


def test_density_mode_evaluation_fills_the_metrics():
    e, stage = _evaluate(_req())
    assert e.status == "ok" and e.winding is not None and e.winding.wire is None
    m = e.design.machine
    assert m.turns_per_pole == e.winding.turns
    assert est.phase_resistance(m) == pytest.approx(e.winding.resistance)
    assert e.mass_kg == pytest.approx(stage.mass.iron + e.winding.copper_mass)
    assert len(e.scan) == 30
    assert e.peak_power_w > 0
    assert e.power_density_kw_per_kg == pytest.approx(e.peak_power_w / 1000 / e.mass_kg)
    assert 0 < e.efficiency_base <= 1
    assert e.feasible == (e.torque_ratio >= 1 and e.power_ratio >= 1)


def test_wire_mode_evaluation_uses_the_inverter_current():
    req = _req(wires=[THICK], phase_current_a=100.0)
    e, _ = _evaluate(req)
    assert e.status == "ok" and e.winding.wire == 0
    assert e.winding.current == 100.0 and e.winding.strands >= 1
    assert e.winding.current_density <= 20e6 * (1 + 1e-9)
    assert est.phase_resistance(e.design.machine) == pytest.approx(e.winding.resistance)


def test_no_winding_is_reported_not_raised():
    e, _ = _evaluate(_req(wires=[THICK], phase_current_a=1e6))
    assert e.status == "no_winding" and not e.feasible and e.winding is None and e.envelope is None


@pytest.mark.slow
def test_real_8_6_evaluation():
    pytest.importorskip("ngsolve")
    req = _req(peak_power_w=2000.0, peak_torque_nm=6.4, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    stage = stage1(req, make_8_6())
    e = evaluate_stage2(_cand(), req, stage, grid=StageTwoGrid(8, 4), workers=4, max_turns=120)
    assert e.status == "ok", e.error
    assert 1.0 < e.envelope.torque[0] < stage.torque_upper
    assert e.key is not None and e.key.peak_torque > 0


@pytest.mark.parametrize("exc", [MeshRejected(["min angle"], None), InputError([]), WorkerCrashed([3]),
                                 RuntimeError("boom"), ValueError("bad current")])
def test_any_exception_from_build_map_becomes_a_failed_evaluation(exc):
    with mock.patch("srmapp.evaluate.build_map", side_effect=exc):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert e.status == type(exc).__name__ and not e.feasible
    assert math.isnan(e.torque_ratio) and e.envelope is None


def test_keyboard_interrupt_is_not_swallowed():
    with mock.patch("srmapp.evaluate.build_map", side_effect=KeyboardInterrupt), pytest.raises(KeyboardInterrupt):
        evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
```

- [ ] **Step 2: Update the pipeline test fake** (`tests/app/test_app_pipeline.py`)

Replace `_fake` and the `ev` helper inside `test_pareto_uses_feasible_designs_only` so they build `Evaluation` with keywords:

```python
def _fake(candidate, req, stage, **kw):
    nan = float("nan")
    if kw["cancel"] is not None and kw["cancel"]():
        return Evaluation(candidate.id, candidate.design, "cancelled", "map cancelled", stage.mass.iron, None,
                          nan, nan, nan, nan, nan, False, None, None)
    return Evaluation(candidate.id, candidate.design, "ok", "", stage.mass.total, None, 1.2, 1.1,
                      5500.0, 5.5 / stage.mass.total, 0.9, True, Envelope(*([np.zeros(2)] * 8)), None)
```

```python
    def ev(i, feasible, mass, density, eff):
        c = cands[i]
        return Evaluation(c.id, c.design, "ok", "", mass, None, 1.1, 1.1, 1000.0, density, eff, feasible, None, None)
```

Add a test that the settings reach stage 2:

```python
def test_current_density_settings_reach_stage_two():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak=25e6, j_limit=30e6))
    assert ev.call_args.kwargs["j_peak"] == 25e6 and ev.call_args.kwargs["j_limit"] == 30e6
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_evaluate.py tests/app/test_app_pipeline.py -q -m "not slow"`
Expected: FAIL (old `Evaluation` field order, no `max_turns`, no `no_winding`).

- [ ] **Step 4: Implement `src/srmapp/evaluate.py`**

Replace the module with:

```python
"""Stage 2: FEM map of one candidate at its reference turns, then the winding chosen on the rescaled map and its
drive envelope and scores (v0 spec §4.4-4.6, v0a-2 spec §3). Peak-only and unvalidated: no losses beyond copper,
no thermal limit."""
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from srmcore.maps import build_map
from srmcore.maps.results import KeyNumbers, key_numbers
from srmcore.model.design import Design

from .drive.envelope import Envelope
from .requirements import Requirements
from .sizing.estimates import J_LIMIT, J_PEAK, coil_side_area
from .sizing.generator import Candidate
from .sizing.stage1 import Stage1
from .sizing.winding import DENSITY_MAX_TURNS, Winding
from .turns import ScanPoint, choose_turns, requirement_ratios, rescale_turns, speed_grid  # noqa: F401

_NAN = float("nan")


@dataclass(frozen=True)
class StageTwoGrid:
    """Map grid; None takes the design's preset grid (30 x 20 for `full`)."""
    n_angles: int | None = None
    n_currents: int | None = None


@dataclass(frozen=True)
class Evaluation:
    id: str
    design: Design              # with the chosen turns per pole and copper fill once a winding is chosen
    status: str                 # "ok", "cancelled", "no_winding", or the name of the exception that stopped it
    error: str
    mass_kg: float              # iron plus the chosen winding's copper; iron only without a winding
    winding: Winding | None
    torque_ratio: float         # achieved / required, at base speed
    power_ratio: float          # achieved / required, worst over base..max speed
    peak_power_w: float
    power_density_kw_per_kg: float
    efficiency_base: float      # copper-only, at base speed
    feasible: bool
    envelope: Envelope | None
    key: KeyNumbers | None      # of the map at the chosen turns
    scan: tuple[ScanPoint, ...] = ()


def _failed(candidate: Candidate, stage: Stage1, status: str, error: str) -> Evaluation:
    return Evaluation(candidate.id, candidate.design, status, error, stage.mass.iron, None,
                      _NAN, _NAN, _NAN, _NAN, _NAN, False, None, None)


def evaluate_stage2(candidate: Candidate, req: Requirements, stage: Stage1, *, grid: StageTwoGrid = StageTwoGrid(),
                    j_peak: float = J_PEAK, j_limit: float = J_LIMIT, max_turns: int = DENSITY_MAX_TURNS,
                    solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                    progress: Callable[[int, int], None] | None = None,
                    cancel: Callable[[], bool] | None = None) -> Evaluation:
    design = candidate.design
    machine = design.machine
    try:
        result = build_map(design, stage.i_map, solver=solver, workers=workers, n_angles=grid.n_angles,
                           n_currents=grid.n_currents, cache_dir=cache_dir, progress=progress, cancel=cancel)
    except Exception as exc:  # batch boundary: one bad design must not lose the search (not BaseException)
        return _failed(candidate, stage, type(exc).__name__, str(exc))
    if not result.complete:
        return _failed(candidate, stage, "cancelled", "map cancelled")
    choice = choose_turns(result, machine, req, j_peak=j_peak, j_limit=j_limit, max_turns=max_turns)
    if choice.point is None:
        return _failed(candidate, stage, "no_winding",
                       "no turn count meets the wire, phase current and current-density limits")
    w, env = choice.point.winding, choice.envelope
    chosen = machine.model_copy(update={"turns_per_pole": w.turns,
                                        "fill_factor": w.turns * w.copper_area / coil_side_area(machine)})
    mass = stage.mass.iron + w.copper_mass
    peak_power = float(np.max(env.power))
    at_base = int(np.argmin(np.abs(env.speeds_rpm - req.base_speed_rpm)))
    key = key_numbers(rescale_turns(result, w.turns / machine.turns_per_pole), chosen)
    note = (f"turn scan reached its limit of {max_turns}; more turns may also be feasible"
            if not req.wire_mode and w.turns == max_turns else "")
    return Evaluation(candidate.id, design.model_copy(update={"machine": chosen}), "ok", note, mass, w,
                      choice.point.torque_ratio, choice.point.power_ratio, peak_power, peak_power / 1000 / mass,
                      float(env.efficiency[at_base]), choice.feasible, env, key, choice.scan)
```

- [ ] **Step 5: Pass the settings through in `src/srmapp/pipeline.py`**

```python
        evaluation = evaluate_stage2(candidate, req, stage, grid=settings.grid, j_peak=settings.j_peak,
                                     j_limit=settings.j_limit, solver=solver, workers=workers,
                                     cache_dir=cache_dir, cancel=cancel)
```

- [ ] **Step 6: Update `examples/v0_search.py`**

Replace the requirements and the table with:

```python
from srmapp.wire import LitzWire, RectangularWire, RoundWire

# Example wires: Ø1.0 mm grade-2 round, 2.0 x 1.0 mm rectangular, 60 x Ø0.1 mm litz. Sizes in metres.
WIRES = (RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3),
         RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3),
         LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3))
```

```python
    req = Requirements(peak_power_w=10_000.0, peak_torque_nm=32.0, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                       wires=WIRES, phase_current_a=150.0)
```

```python
    print(f"{'id':14}{'poles':>7}{'OD mm':>7}{'wire':>12}{'N':>5}{'par':>5}{'R mΩ':>8}{'J A/mm²':>9}{'mass kg':>9}"
          f"{'T ratio':>9}{'P ratio':>9}{'kW/kg':>7}{'eff':>6}  status")
    for e in res.evaluations:
        m, w = e.design.machine, e.winding
        wire = "-" if w is None else req.wires[w.wire].kind
        wind = (f"{'-':>5}{'-':>5}{'-':>8}{'-':>9}" if w is None else
                f"{w.turns:5d}{w.strands:5d}{w.resistance * 1e3:8.1f}{w.current_density / 1e6:9.1f}")
        print(f"{e.id:14}{m.n_stator_poles:>4}/{m.n_rotor_poles:<2}{m.stator_outer_diameter * 1e3:7.0f}{wire:>12}{wind}"
              f"{e.mass_kg:9.2f}{e.torque_ratio:9.2f}{e.power_ratio:9.2f}{e.power_density_kw_per_kg:7.2f}"
              f"{e.efficiency_base:6.2f}  {e.status}{' *' if e.id in front else ''}")
```

Update its docstring line `Peak-only and unvalidated. Stage 2 takes about 200 s per design.` to `Peak-only and unvalidated. Stage 2 builds a full-preset map (about 13 min) and scans the windings per design.`

- [ ] **Step 7: Run the app suite**

Run: `.venv\Scripts\python -m pytest tests/app -q -m "not slow"`
Expected: all pass.

- [ ] **Step 8: Run the slow evaluate test**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_evaluate.py -q -m slow`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/srmapp examples/v0_search.py tests/app
git commit -m "feat(app): stage 2 chooses turns, wire and strands on the rescaled map

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Stage-2 accuracy check script

**Files:**
- Create: `examples/v0_angle_check.py`

**Interfaces:**
- Consumes: `sample_candidates`, `stage1`, `choose_turns`, `rescale_turns`, `requirement_ratios`, `speed_grid`, `envelope(..., n_theta, n_on, n_off, current_limit)`, `build_map`.

- [ ] **Step 1: Write the script**

```python
"""Stage-2 accuracy check (v0a-2 spec §5) on one candidate per pole set, all with the winding chosen on the
30-angle map: envelope from 30 angles against 60 angles on the `full` mesh, and the drive discretisation
(N_THETA 181 against 361, a 40 x 40 against an 80 x 80 on/off grid) on the 30-angle map.

    python examples/v0_angle_check.py [n_candidates] [n_currents]

Prints, per design, the torque ratio at base speed and the worst power ratio over base..max speed for each
variant, and their change against the default (30 angles, 181, 40 x 40). Maps are cached in out/v0_angle_check.
Hours on a laptop."""
import sys
import time

from srmapp.drive.envelope import envelope
from srmapp.requirements import Requirements
from srmapp.sizing.generator import sample_candidates
from srmapp.sizing.stage1 import stage1
from srmapp.turns import choose_turns, requirement_ratios, rescale_turns, speed_grid
from srmapp.wire import LitzWire, RectangularWire, RoundWire
from srmcore.maps import build_map

REQ = Requirements(peak_power_w=10_000.0, peak_torque_nm=32.0, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                   wires=(RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3),
                          RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3),
                          LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3)),
                   phase_current_a=150.0)
# name: (map angles, n_theta, on/off grid size)
VARIANTS = {"default": (30, 181, 40), "60 angles": (60, 181, 40), "n_theta 361": (30, 361, 40),
            "on/off 80": (30, 181, 80)}
CACHE = "out/v0_angle_check"

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n_currents = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    candidates, _ = sample_candidates(REQ, n, seed=0)
    for c in candidates:
        m = c.design.machine
        t0 = time.perf_counter()
        i_map = stage1(REQ, m).i_map
        maps = {a: build_map(c.design, i_map, n_angles=a, n_currents=n_currents, cache_dir=CACHE)
                for a in sorted({v[0] for v in VARIANTS.values()})}
        choice = choose_turns(maps[30], m, REQ)
        print(f"\n{c.id} {m.n_stator_poles}/{m.n_rotor_poles} OD {m.stator_outer_diameter * 1e3:.0f} mm "
              f"({time.perf_counter() - t0:.0f} s)")
        if choice.point is None:
            print("  no winding meets the limits; skipped")
            continue
        w = choice.point.winding
        print(f"  wire {REQ.wires[w.wire].kind}, N {w.turns}, strands {w.strands}, R {w.resistance * 1e3:.1f} mΩ")
        rows = {}
        for name, (n_a, n_theta, n_sw) in VARIANTS.items():
            env = envelope(rescale_turns(maps[n_a], w.turns / m.turns_per_pole), m, REQ.bus_voltage_v,
                           w.resistance, speed_grid(REQ), current_limit=w.current, n_theta=n_theta, n_on=n_sw,
                           n_off=n_sw)
            rows[name] = requirement_ratios(env, REQ)
        ref = rows["default"]
        print(f"  {'variant':14}{'T ratio':>9}{'P ratio':>9}{'dT':>9}{'dP':>9}")
        for name, (t, p) in rows.items():
            print(f"  {name:14}{t:9.3f}{p:9.3f}{(t - ref[0]) / ref[0]:9.2%}{(p - ref[1]) / ref[1]:9.2%}")
```

- [ ] **Step 2: Smoke-run on a tiny budget**

Run: `.venv\Scripts\python examples\v0_angle_check.py 1 4`
Expected: one design printed with four variant rows and no exception (about 45 min: the `full` maps dominate). If the first candidate has no winding, it prints the skip line; that is also a pass for this step.

- [ ] **Step 3: Commit**

```bash
git add examples/v0_angle_check.py
git commit -m "feat(examples): stage-2 angle and drive-discretisation check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Run the check and record it (controller)

**Files:**
- Modify: `docs/m4-handoff.md`

- [ ] **Step 1: Run the full check in the background**

Run: `.venv\Scripts\python examples\v0_angle_check.py 4 20 > out\v0_angle_check.txt`
Expected: four designs (one per pole set), several hours.

- [ ] **Step 2: Record**

Add a section `## v0a-2 stage-2 accuracy check (2026-10-01)` to `docs/m4-handoff.md` with the command, the printed table, the wall time, and one line per finding. Any |dT| or |dP| above 2 % is listed as an owner decision, with no default changed.

- [ ] **Step 3: Commit**

```bash
git add docs/m4-handoff.md
git commit -m "docs: v0a-2 stage-2 accuracy check results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

Replace the `src/srmapp/` paragraph with:

```markdown
`src/srmapp/` holds the requirements-driven search (requirements, wires, candidate generator, stage-1 filter, windings, drive envelope, turns scan, stage-2 evaluation, Pareto set); it imports `srmcore` public modules and `srmcore` never imports it (`tests/app/test_app_layering.py`). Every candidate is mapped once at `REFERENCE_TURNS` over the largest ampere-turns any allowed winding carries; `turns.rescale_turns` gives the exact map at any turn count and `turns.choose_turns` picks the winding: in wire mode (`Requirements.wires` and `phase_current_a` given) the feasible winding with the lowest resistance, in density mode the feasible winding with the most turns. See `docs/superpowers/specs/2026-10-01-v0a2-turns-after-map-design.md`.
```

Add to the Commands block, after the `v0_grid_study.py` line:

```
python examples\v0_angle_check.py [n_candidates] [n_currents]   # stage-2 angle and drive-discretisation check (hours)
```

- [ ] **Step 2: Run the fast suite**

Run: `.venv\Scripts\python -m pytest -m "not slow" -q`
Expected: all pass (6–8 minutes).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: srmapp turns and wire after the map

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
