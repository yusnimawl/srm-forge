# v0a Search Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From vehicle requirements (power, torque, speed range, bus voltage, limits), generate candidate radial SRM designs, evaluate them with `srmcore` in two stages, and return scored candidates plus a Pareto set. No web layer (that is plan v0b).

**Architecture:** A new package `srmapp` sits above `srmcore` and only imports its public modules. `srmcore` never imports `srmapp`. Stage 1 is a closed-form filter (mass, torque upper bound). Stage 2 builds a reduced `srmcore` map per shortlisted design and runs a minimal drive model on it (single-pulse voltage control with current limit, ideal commutation) to get a torque-speed envelope. Results are peak-only and unvalidated.

**Tech Stack:** Python 3.12+, numpy, scipy (`qmc.LatinHypercube`, `PchipInterpolator`), pydantic v2, pytest; `srmcore` (NGSolve solver for stage 2).

**Spec:** `docs/superpowers/specs/2026-09-30-v0-walking-skeleton-design.md` (this plan implements its §3 and §4; the web layer (§5) is plan v0b and optimisation (§6) a later plan). Parent spec: `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md`.

## Global Constraints

- SI units everywhere (metres, radians, amperes, watts, kg); rpm only in `Requirements` field names and the `Envelope.speeds_rpm` axis.
- `srmcore` must not import `srmapp` (test in Task 1). `srmapp` imports only `srmcore` public modules and numpy/scipy/pydantic.
- Frozen pydantic models or frozen dataclasses for anything that crosses a module boundary.
- Comments describe the code as it is now; no task or plan history.
- Fast suite stays under 10 minutes. Tests that build a map are marked `@pytest.mark.slow` and use `pytest.importorskip("ngsolve")`.
- Test file basenames must be unique across `tests/` (no `__init__.py`); all new tests are named `test_app_*.py`.
- Every result carries the label "unvalidated, peak-only" in its docstring or field; nothing in this plan awards "EM-validated".
- `J_PEAK = 15e6` A/m² is a provisional peak current density (sub-project #3 replaces it with a thermal limit).
- DC-bus voltage default is 400 V (assumed; parent spec §10 open item).

## Review Focus

- A millimetre-looking outer-diameter limit (e.g. `160` for 160 mm) must be rejected by `Requirements`, not silently produce an empty search. Pinned in Task 1.
- A very restrictive `max_outer_diameter_m` or an infeasible pole set makes the generator return fewer designs than asked, never raise and never loop forever. Pinned in Task 3.
- At high speed the flux may not decay before alignment; those (turn-on, turn-off) pairs must be excluded and the envelope must never contain NaN or negative-infinity torque. Pinned in Task 5.
- A candidate whose map raises `MapFailed`, `MeshRejected` or `WorkerCrashed` must become an `Evaluation` with a status and error text; the search continues. Pinned in Task 6.
- Cancelling mid-search returns the evaluations finished so far with `cancelled=True`, not an exception. Pinned in Task 7.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/srmapp/__init__.py` | package marker, version |
| `src/srmapp/requirements.py` | `Requirements` model and its checks |
| `src/srmapp/sizing/__init__.py` | empty |
| `src/srmapp/sizing/estimates.py` | closed-form mass, winding resistance, peak current |
| `src/srmapp/sizing/generator.py` | `Candidate`, `sample_candidates` |
| `src/srmapp/sizing/stage1.py` | `Stage1`, `torque_upper_bound`, `stage1` |
| `src/srmapp/drive/__init__.py` | empty |
| `src/srmapp/drive/envelope.py` | `Envelope`, `envelope` (minimal drive model) |
| `src/srmapp/evaluate.py` | `Evaluation`, `StageTwoGrid`, `speed_grid`, `evaluate_stage2` |
| `src/srmapp/pareto.py` | `pareto_mask` |
| `src/srmapp/pipeline.py` | `SearchSettings`, `SearchResult`, `run_search` |
| `examples/v0_search.py` | run a small search and print a table |
| `examples/v0_grid_study.py` | measure reduced map grids against the `screening` map |
| `tests/app/test_app_*.py` | tests, one file per module |

`pyproject.toml` gains `src/srmapp` in the wheel packages.

---

### Task 1: Package scaffold and `Requirements`

**Files:**
- Create: `src/srmapp/__init__.py`, `src/srmapp/requirements.py`, `src/srmapp/sizing/__init__.py`, `src/srmapp/drive/__init__.py`
- Modify: `pyproject.toml` (wheel packages)
- Test: `tests/app/test_app_requirements.py`, `tests/app/test_app_layering.py`

**Interfaces:**
- Produces: `srmapp.requirements.Requirements` (frozen pydantic model) with fields `peak_power_w`, `peak_torque_nm`, `base_speed_rpm`, `max_speed_rpm`, `bus_voltage_v=400.0`, `max_outer_diameter_m=None`, `max_mass_kg=None`.

- [ ] **Step 1: Write the failing tests**

`tests/app/test_app_requirements.py`:

```python
import math

import pytest
from pydantic import ValidationError

from srmapp.requirements import Requirements


def _ok(**kw):
    # 30 kW at 3000 rpm base: torque = 30000 / (3000 * 2π/60) = 95.49 N·m
    values = dict(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    values.update(kw)
    return Requirements(**values)


def test_defaults():
    r = _ok()
    assert r.bus_voltage_v == 400.0
    assert r.max_outer_diameter_m is None and r.max_mass_kg is None


def test_frozen():
    with pytest.raises(ValidationError):
        _ok().bus_voltage_v = 48.0


@pytest.mark.parametrize("field", ["peak_power_w", "peak_torque_nm", "base_speed_rpm", "max_speed_rpm",
                                   "bus_voltage_v"])
def test_positive_fields(field):
    with pytest.raises(ValidationError):
        _ok(**{field: 0.0})


def test_max_speed_not_below_base():
    with pytest.raises(ValidationError, match="max_speed_rpm"):
        _ok(max_speed_rpm=2000.0)


def test_power_torque_speed_must_agree():
    # 30 kW needs 95.5 N·m at 3000 rpm; 50 N·m is off by far more than 10 %
    with pytest.raises(ValidationError, match="power"):
        _ok(peak_torque_nm=50.0)


def test_millimetre_looking_outer_diameter_is_rejected():
    with pytest.raises(ValidationError, match="metres"):
        _ok(max_outer_diameter_m=160.0)
    assert _ok(max_outer_diameter_m=0.16).max_outer_diameter_m == 0.16


def test_no_extra_fields():
    with pytest.raises(ValidationError):
        _ok(colour="red")
```

`tests/app/test_app_layering.py`:

```python
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_srmcore_never_imports_srmapp():
    for py in (SRC / "srmcore").rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            assert not any(n == "srmapp" or n.startswith("srmapp.") for n in names), py
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'srmapp'`).

- [ ] **Step 3: Implement**

`pyproject.toml`: change `packages = ["src/srmcore"]` to `packages = ["src/srmcore", "src/srmapp"]`, then run `.venv\Scripts\python -m pip install -e ".[dev,ngsolve]"` once so `srmapp` is importable.

`src/srmapp/__init__.py`:

```python
"""srmapp: requirements-driven search over radial SRM designs, built on srmcore. Results are peak-only and unvalidated."""

__version__ = "0.1.0"
```

`src/srmapp/sizing/__init__.py` and `src/srmapp/drive/__init__.py`: empty files.

`src/srmapp/requirements.py`:

```python
"""Vehicle-motor requirements (v0 spec §3). Peak-only: no continuous rating."""
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Same plausibility window as the srmcore validator's stator_outer_diameter unit rule.
_OD_RANGE = (0.01, 2.0)
_POWER_TOLERANCE = 0.10


class Requirements(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    peak_power_w: float = Field(gt=0)
    peak_torque_nm: float = Field(gt=0)
    base_speed_rpm: float = Field(gt=0)
    max_speed_rpm: float = Field(gt=0)
    bus_voltage_v: float = Field(default=400.0, gt=0)
    max_outer_diameter_m: float | None = Field(default=None, gt=0)
    max_mass_kg: float | None = Field(default=None, gt=0)

    @field_validator("max_outer_diameter_m")
    @classmethod
    def _metres(cls, value):
        if value is not None and not _OD_RANGE[0] <= value <= _OD_RANGE[1]:
            raise ValueError(f"{value} is outside {_OD_RANGE} metres; lengths are in metres")
        return value

    @model_validator(mode="after")
    def _consistent(self):
        if self.max_speed_rpm < self.base_speed_rpm:
            raise ValueError("max_speed_rpm must not be below base_speed_rpm")
        power_at_base = self.peak_torque_nm * self.base_speed_rpm * 2 * math.pi / 60
        if abs(power_at_base - self.peak_power_w) > _POWER_TOLERANCE * self.peak_power_w:
            raise ValueError(f"power {self.peak_power_w:.0f} W disagrees with torque x base speed "
                             f"= {power_at_base:.0f} W by more than {_POWER_TOLERANCE:.0%}")
        return self
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/srmapp tests/app
git commit -m "feat(app): srmapp package and Requirements"
```

---

### Task 2: Closed-form estimates (mass, resistance, peak current)

**Files:**
- Create: `src/srmapp/sizing/estimates.py`
- Test: `tests/app/test_app_estimates.py`

**Interfaces:**
- Consumes: `srmcore.model.design.RadialSRMParams`, `srmcore.materials.load_material` (soft magnetic: `.density`, `.stacking_factor`; conductor: `.density`, `.resistivity`, `.reference_temperature_c`, `.temperature_coefficient`).
- Produces:
  - `J_PEAK: float = 15e6`
  - `@dataclass(frozen=True) Mass(stator_iron: float, rotor_iron: float, copper: float)` with property `total`
  - `pole_chord(radius: float, arc: float) -> float`
  - `coil_side_area(p) -> float` (m², one coil side)
  - `mean_turn_length(p) -> float` (m)
  - `conductor_area(p) -> float` (m²)
  - `peak_current(p, j_peak=J_PEAK) -> float` (A)
  - `active_mass(p) -> Mass`
  - `phase_resistance(p, temperature_c=100.0) -> float` (Ω)

- [ ] **Step 1: Write the failing tests**

```python
import math

import pytest
from conftest import make_8_6, make_24_16

from srmapp.sizing import estimates as est


def test_pole_chord():
    assert est.pole_chord(0.05, math.pi) == pytest.approx(0.1)


def test_mass_parts_positive_and_total():
    m = est.active_mass(make_8_6())
    assert m.stator_iron > 0 and m.rotor_iron > 0 and m.copper > 0
    assert m.total == pytest.approx(m.stator_iron + m.rotor_iron + m.copper)


def test_iron_mass_scales_with_stack_length():
    a = est.active_mass(make_8_6(stack_length=0.1))
    b = est.active_mass(make_8_6(stack_length=0.2))
    assert b.stator_iron == pytest.approx(2 * a.stator_iron)
    assert b.rotor_iron == pytest.approx(2 * a.rotor_iron)


def test_8_6_mass_is_plausible():
    # 160 mm OD, 100 mm stack: a few kg of iron, under a kilogram-ish of copper
    m = est.active_mass(make_8_6())
    assert 3.0 < m.stator_iron + m.rotor_iron < 12.0
    assert 0.2 < m.copper < 3.0


def test_current_and_resistance_relations():
    p = make_8_6()
    a = est.conductor_area(p)
    assert est.peak_current(p) == pytest.approx(est.J_PEAK * a)
    # doubling the turns halves the conductor area and doubles the current-carrying length
    q = make_8_6(turns_per_pole=120)
    assert est.conductor_area(q) == pytest.approx(a / 2)
    assert est.phase_resistance(q) == pytest.approx(4 * est.phase_resistance(p))


def test_resistance_rises_with_temperature():
    p = make_8_6()
    assert est.phase_resistance(p, 100.0) > est.phase_resistance(p, 20.0)
    assert est.phase_resistance(p, 20.0) > 0


def test_copper_mass_equals_volume_from_resistance_geometry():
    # copper volume = phases × (turns per phase × turn length × conductor area)
    p = make_24_16()
    turns_phase = p.turns_per_pole * p.n_stator_poles / p.n_phases
    volume = p.n_phases * turns_phase * est.mean_turn_length(p) * est.conductor_area(p)
    assert est.active_mass(p).copper == pytest.approx(8890.0 * volume, rel=1e-6)


@pytest.mark.slow
def test_areas_agree_with_the_mesh():
    pytest.importorskip("gmsh")
    import numpy as np

    from srmcore.mesh import build_machine_mesh
    from srmcore.model.design import Design, MeshSettings
    from srmcore.physics.fem import triangle_areas

    p = make_8_6()
    mesh = build_machine_mesh(Design(machine=p, mesh=MeshSettings(preset="screening")))

    def area(part, kind):
        a = triangle_areas(part.nodes, part.triangles)
        ids = [i for i, n in enumerate(mesh.region_names) if mesh.region_kind[n] == kind]
        return float(a[np.isin(part.region_ids, ids)].sum())

    stator_area = area(mesh.stator, "stator_iron")
    rotor_area = area(mesh.rotor, "rotor_iron")
    coil_area = area(mesh.stator, "coil")
    m = est.active_mass(p)
    rho = 7650.0   # M19 provisional density
    from srmcore.materials import load_material
    k = load_material("M19").stacking_factor
    assert m.stator_iron == pytest.approx(rho * k * stator_area * p.stack_length, rel=0.08)
    assert m.rotor_iron == pytest.approx(rho * k * rotor_area * p.stack_length, rel=0.08)
    assert 2 * p.n_stator_poles * est.coil_side_area(p) == pytest.approx(coil_area, rel=0.15)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_estimates.py -m "not slow" -q`
Expected: FAIL (`ModuleNotFoundError: srmapp.sizing.estimates`).

- [ ] **Step 3: Implement**

`src/srmapp/sizing/estimates.py`:

```python
"""Closed-form estimates of active mass, winding resistance and peak current (v0 spec §4).

Poles are treated as parallel-sided bars of the chord width at the pole face, so iron areas are estimates
(fillets, tapers and the slot corners are ignored). The end winding is a racetrack approximation."""
import math
from dataclasses import dataclass

from srmcore.materials import load_material
from srmcore.model.design import RadialSRMParams

# Peak current density in the conductor, A/m². Provisional: a thermal model replaces it.
J_PEAK = 15e6


@dataclass(frozen=True)
class Mass:
    stator_iron: float   # kg
    rotor_iron: float
    copper: float

    @property
    def total(self) -> float:
        return self.stator_iron + self.rotor_iron + self.copper


def pole_chord(radius: float, arc: float) -> float:
    return 2 * radius * math.sin(arc / 2)


def _slot_width(p: RadialSRMParams) -> float:
    """Mean circumferential slot width between two stator poles."""
    r_mid = (p.bore_radius + p.stator_yoke_inner_radius) / 2
    return 2 * math.pi * r_mid / p.n_stator_poles - pole_chord(p.bore_radius, p.stator_pole_arc)


def coil_side_area(p: RadialSRMParams) -> float:
    """Copper-bearing area of one coil side: half of the slot, less liner and inner clearance."""
    height = p.stator_yoke_inner_radius - p.bore_radius
    width = _slot_width(p) - 2 * p.slot_liner_thickness
    depth = height - p.slot_liner_thickness - p.coil_inner_clearance
    return max(width, 0.0) * max(depth, 0.0) / 2


def mean_turn_length(p: RadialSRMParams) -> float:
    """Two straight runs plus two semicircular ends around a pole and half a slot either side."""
    return 2 * p.stack_length + math.pi * (pole_chord(p.bore_radius, p.stator_pole_arc) + _slot_width(p) / 2)


def conductor_area(p: RadialSRMParams) -> float:
    """Cross-section of one conductor: the filled coil side shared among the turns of a pole."""
    return p.fill_factor * coil_side_area(p) / p.turns_per_pole


def peak_current(p: RadialSRMParams, j_peak: float = J_PEAK) -> float:
    return j_peak * conductor_area(p)


def _iron_areas(p: RadialSRMParams) -> tuple[float, float]:
    """Cross-section areas (m²) of stator and rotor iron, without the stacking factor."""
    rb, ryi = p.bore_radius, p.stator_yoke_inner_radius
    stator = (math.pi * (p.stator_outer_radius**2 - ryi**2)
              + p.n_stator_poles * pole_chord(rb, p.stator_pole_arc) * (ryi - rb))
    ro, rj = p.rotor_outer_radius, p.rotor_yoke_outer_radius
    rotor = (math.pi * (rj**2 - p.shaft_radius**2)
             + p.n_rotor_poles * pole_chord(ro, p.rotor_pole_arc) * (ro - rj))
    return stator, rotor


def active_mass(p: RadialSRMParams) -> Mass:
    stator_area, rotor_area = _iron_areas(p)
    stator_mat, rotor_mat = load_material(p.materials.stator), load_material(p.materials.rotor)
    copper = load_material(p.materials.coil)
    copper_volume = (p.n_stator_poles * p.turns_per_pole * conductor_area(p) * mean_turn_length(p))
    return Mass(stator_iron=stator_mat.density * stator_mat.stacking_factor * stator_area * p.stack_length,
                rotor_iron=rotor_mat.density * rotor_mat.stacking_factor * rotor_area * p.stack_length,
                copper=copper.density * copper_volume)


def phase_resistance(p: RadialSRMParams, temperature_c: float = 100.0) -> float:
    """Series resistance of one phase at `temperature_c`."""
    copper = load_material(p.materials.coil)
    rho = copper.resistivity * (1 + copper.temperature_coefficient * (temperature_c - copper.reference_temperature_c))
    turns_phase = p.turns_per_pole * p.n_stator_poles / p.n_phases
    return rho * turns_phase * mean_turn_length(p) / conductor_area(p)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_estimates.py -m "not slow" -q`
Expected: pass. Then `.venv\Scripts\python -m pytest tests/app/test_app_estimates.py -m slow -q`. If the mesh comparison fails, change the formulas in `estimates.py` (not the tolerances) until iron agrees within 8 % and coil area within 15 %; if the coil area cannot get within 15 %, report the measured ratio and stop.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/sizing/estimates.py tests/app/test_app_estimates.py
git commit -m "feat(app): closed-form mass, resistance and peak-current estimates"
```

---

### Task 3: Candidate generator

**Files:**
- Create: `src/srmapp/sizing/generator.py`
- Test: `tests/app/test_app_generator.py`

**Interfaces:**
- Consumes: `Requirements`; `srmcore.model.design.{Design, MeshSettings, RadialSRMParams}`; `srmcore.model.validator.require_valid`; `srmcore.model.errors.InputError`; `srmcore.topology.radial.build_outline`.
- Produces:
  - `POLE_SETS: tuple[tuple[int, int, int], ...] = ((6, 4, 3), (8, 6, 4), (12, 8, 3), (24, 16, 3))` as `(n_stator, n_rotor, n_phases)`
  - `@dataclass(frozen=True) Candidate(id: str, design: Design)`
  - `sample_candidates(req, n, *, seed=0, pole_sets=POLE_SETS) -> tuple[list[Candidate], dict[str, int]]`; the dict counts drops as `{"validator": int, "fit": int}`. Designs use `MeshSettings(preset="screening")`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from srmapp.requirements import Requirements
from srmapp.sizing.generator import POLE_SETS, sample_candidates
from srmcore.model.validator import require_valid
from srmcore.topology.radial import build_outline


def _req(**kw):
    values = dict(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    values.update(kw)
    return Requirements(**values)


def test_deterministic_for_a_seed():
    a, _ = sample_candidates(_req(), 8, seed=3)
    b, _ = sample_candidates(_req(), 8, seed=3)
    assert [c.id for c in a] == [c.id for c in b]
    c, _ = sample_candidates(_req(), 8, seed=4)
    assert [x.id for x in a] != [x.id for x in c]


def test_every_candidate_is_valid_and_fits():
    cands, dropped = sample_candidates(_req(), 12, seed=1)
    assert len(cands) > 0
    assert set(dropped) == {"validator", "fit"}
    for c in cands:
        require_valid(c.design)
        build_outline(c.design.machine)


def test_all_pole_sets_are_represented():
    cands, _ = sample_candidates(_req(), 16, seed=0)
    seen = {(c.design.machine.n_stator_poles, c.design.machine.n_rotor_poles) for c in cands}
    assert seen == {(s, r) for s, r, _ in POLE_SETS}


def test_outer_diameter_limit_is_respected():
    cands, _ = sample_candidates(_req(max_outer_diameter_m=0.15), 8, seed=0)
    assert all(c.design.machine.stator_outer_diameter <= 0.15 for c in cands)


def test_screening_preset_and_speed_are_set():
    c = sample_candidates(_req(), 4, seed=0)[0][0]
    assert c.design.mesh.preset == "screening"
    assert c.design.machine.max_speed_rpm == 9000.0


def test_ids_are_unique():
    cands, _ = sample_candidates(_req(), 16, seed=0)
    assert len({c.id for c in cands}) == len(cands)


def test_very_restrictive_limit_returns_fewer_without_raising():
    cands, dropped = sample_candidates(_req(max_outer_diameter_m=0.02), 8, seed=0)
    assert len(cands) <= 8
    assert sum(dropped.values()) >= 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_generator.py -q`
Expected: FAIL (`ModuleNotFoundError: srmapp.sizing.generator`).

- [ ] **Step 3: Implement**

`src/srmapp/sizing/generator.py`:

```python
"""Candidate generator: Latin-hypercube samples of radial SRM designs inside a bounded box (v0 spec §4.1)."""
import hashlib
import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import qmc

from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.errors import InputError
from srmcore.model.validator import require_valid
from srmcore.topology.radial import build_outline

from ..requirements import Requirements

POLE_SETS = ((6, 4, 3), (8, 6, 4), (12, 8, 3), (24, 16, 3))   # (stator poles, rotor poles, phases)
DEFAULT_MAX_OD = 0.35      # m
MIN_OD = 0.08              # m
_DIMS = 9
_TRIES_PER_DESIGN = 20     # sample budget per requested design before giving up on a pole set
_TURNS = (6, 120)


@dataclass(frozen=True)
class Candidate:
    id: str
    design: Design


def _machine(u: np.ndarray, ns: int, nr: int, m: int, d_lo: float, d_hi: float, max_speed_rpm: float) -> RadialSRMParams:
    d_o = d_lo + u[0] * (d_hi - d_lo)
    stack = d_o * (0.25 + 0.95 * u[1])
    d_r = d_o * (0.50 + 0.15 * u[2])
    gap = min(max(d_o / 400, 3e-4), 8e-4)
    limit = 2 * math.pi / (m * nr)              # Lawrenson self-starting limit on the pole arcs
    beta_s, beta_r = limit * (1.0 + 0.6 * u[3]), limit * (1.0 + 0.7 * u[4])
    w_s = 2 * (d_r / 2 + gap) * math.sin(beta_s / 2)
    w_r = d_r * math.sin(beta_r / 2)
    turns = int(round(math.exp(math.log(_TURNS[0]) + u[8] * (math.log(_TURNS[1]) - math.log(_TURNS[0])))))
    return RadialSRMParams(
        n_stator_poles=ns, n_rotor_poles=nr, n_phases=m,
        stator_outer_diameter=d_o, rotor_outer_diameter=d_r, air_gap=gap, stack_length=stack,
        shaft_diameter=d_r * (0.25 + 0.20 * u[7]),
        stator_pole_arc=beta_s, rotor_pole_arc=beta_r,
        stator_yoke_thickness=w_s * (0.5 + 0.4 * u[5]), rotor_yoke_thickness=w_r * (0.5 + 0.5 * u[6]),
        turns_per_pole=turns, fill_factor=0.5, slot_liner_thickness=4e-4, coil_inner_clearance=1e-3,
        lamination_thickness=0.35e-3, max_speed_rpm=max_speed_rpm)


def sample_candidates(req: Requirements, n: int, *, seed: int = 0,
                      pole_sets=POLE_SETS) -> tuple[list[Candidate], dict[str, int]]:
    """About `n` valid designs, split evenly over `pole_sets`. Designs the validator or the topology fit
    check rejects are dropped and counted; a pole set that cannot yield its share simply contributes fewer,
    so the result may hold fewer than `n` designs."""
    d_hi = req.max_outer_diameter_m or DEFAULT_MAX_OD
    d_lo = min(MIN_OD, d_hi / 2)
    per_set = math.ceil(n / len(pole_sets))
    dropped = {"validator": 0, "fit": 0}
    kept: list[Candidate] = []
    for index, (ns, nr, m) in enumerate(pole_sets):
        samples = qmc.LatinHypercube(d=_DIMS, seed=seed + index).random(per_set * _TRIES_PER_DESIGN)
        taken = 0
        for u in samples:
            if taken == per_set:
                break
            try:
                machine = _machine(u, ns, nr, m, d_lo, d_hi, req.max_speed_rpm)
                design = Design(machine=machine, mesh=MeshSettings(preset="screening"))
                require_valid(design)
            except InputError:
                dropped["validator"] += 1
                continue
            try:
                build_outline(machine)
            except InputError:
                dropped["fit"] += 1
                continue
            kept.append(Candidate(hashlib.sha256(design.to_json().encode()).hexdigest()[:12], design))
            taken += 1
    return kept[:n] if len(kept) > n else kept, dropped
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_generator.py -q`
Expected: pass. If `test_all_pole_sets_are_represented` fails because a pole set never yields a valid design, print `dropped` and the rejecting rule, widen the sampling ranges in `_machine` for that set (for example the arc factors), and rerun; do not remove the test.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/sizing/generator.py tests/app/test_app_generator.py
git commit -m "feat(app): Latin-hypercube candidate generator"
```

---

### Task 4: Stage 1 filter

**Files:**
- Create: `src/srmapp/sizing/stage1.py`
- Test: `tests/app/test_app_stage1.py`

**Interfaces:**
- Consumes: `estimates.{active_mass, peak_current, pole_chord}`, `Requirements`, `srmcore.materials.load_material`.
- Produces:
  - `torque_upper_bound(p, i_peak) -> float`: N·m; a deliberately optimistic bound (energy-conversion rectangle ψ_sat·I per stroke, m·Nr strokes per revolution).
  - `@dataclass(frozen=True) Stage1(mass: Mass, i_peak: float, torque_upper: float, passes: bool, reason: str)`
  - `stage1(req, p, margin=1.0) -> Stage1`: fails when the mass exceeds `req.max_mass_kg` or `torque_upper < margin * req.peak_torque_nm`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from conftest import make_8_6

from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.stage1 import stage1, torque_upper_bound


def _req(**kw):
    values = dict(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    values.update(kw)
    return Requirements(**values)


def test_bound_is_above_the_engine_result():
    # The FEM peak torque of this 8/6 at 20 A is 12.42 N·m (tests/maps/goldens_8_6.json).
    assert torque_upper_bound(make_8_6(), 20.0) >= 12.42


def test_bound_scales_linearly_with_current_and_stack():
    p = make_8_6()
    assert torque_upper_bound(p, 40.0) == pytest.approx(2 * torque_upper_bound(p, 20.0))
    q = make_8_6(stack_length=0.2)
    assert torque_upper_bound(q, 20.0) == pytest.approx(2 * torque_upper_bound(p, 20.0))


def test_bound_does_not_depend_on_turns_at_fixed_current_density():
    # ψ_sat ∝ turns and i_peak ∝ 1/turns, so the product is turn-independent
    a = make_8_6(turns_per_pole=40)
    b = make_8_6(turns_per_pole=80)
    ta = torque_upper_bound(a, est.peak_current(a))
    tb = torque_upper_bound(b, est.peak_current(b))
    assert ta == pytest.approx(tb)


def test_small_motor_fails_a_large_torque_requirement():
    s = stage1(_req(), make_8_6())
    assert not s.passes and "torque" in s.reason


def test_easy_requirement_passes():
    s = stage1(_req(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0), make_8_6())
    assert s.passes and s.reason == ""
    assert s.mass.total > 0 and s.i_peak > 0


def test_mass_limit():
    s = stage1(_req(peak_power_w=1000.0, peak_torque_nm=3.2, max_mass_kg=0.5), make_8_6())
    assert not s.passes and "mass" in s.reason


def test_margin_tightens_the_filter():
    req = _req(peak_power_w=1000.0, peak_torque_nm=3.2)
    assert stage1(req, make_8_6(), margin=1.0).passes
    assert not stage1(req, make_8_6(), margin=1e6).passes
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_stage1.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`src/srmapp/sizing/stage1.py`:

```python
"""Stage 1: closed-form filter that drops designs that cannot meet the requirements even under optimistic
assumptions (v0 spec §4.3). The torque bound is an upper bound on purpose, so the filter never drops a design
the FEM stage would keep."""
import math
from dataclasses import dataclass

from srmcore.materials import load_material
from srmcore.model.design import RadialSRMParams

from ..requirements import Requirements
from .estimates import Mass, active_mass, peak_current, pole_chord


def torque_upper_bound(p: RadialSRMParams, i_peak: float) -> float:
    """Average torque (N·m) if every stroke converted the full rectangle ψ_sat·i_peak: the pole flux saturates at
    the material's saturation polarisation in the narrower of the stator and rotor poles, and the phase carries
    turns_per_pole × poles-per-phase series turns. Each of the m·Nr strokes per revolution converts one rectangle."""
    stator, rotor = load_material(p.materials.stator), load_material(p.materials.rotor)
    b_sat = min(stator.saturation_polarisation, rotor.saturation_polarisation)
    pole_width = min(pole_chord(p.bore_radius, p.stator_pole_arc), pole_chord(p.rotor_outer_radius, p.rotor_pole_arc))
    pole_area = pole_width * p.stack_length * min(stator.stacking_factor, rotor.stacking_factor)
    series_turns = p.turns_per_pole * p.n_stator_poles / p.n_phases
    psi_sat = series_turns * b_sat * pole_area
    return p.n_phases * p.n_rotor_poles * psi_sat * i_peak / (2 * math.pi)


@dataclass(frozen=True)
class Stage1:
    mass: Mass
    i_peak: float          # A
    torque_upper: float    # N·m
    passes: bool
    reason: str            # empty when the design passes


def stage1(req: Requirements, p: RadialSRMParams, margin: float = 1.0) -> Stage1:
    mass = active_mass(p)
    i_peak = peak_current(p)
    upper = torque_upper_bound(p, i_peak)
    reason = ""
    if req.max_mass_kg is not None and mass.total > req.max_mass_kg:
        reason = f"mass {mass.total:.2f} kg above the {req.max_mass_kg:.2f} kg limit"
    elif upper < margin * req.peak_torque_nm:
        reason = f"torque upper bound {upper:.1f} N·m below the required {margin * req.peak_torque_nm:.1f} N·m"
    return Stage1(mass, i_peak, upper, reason == "", reason)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_stage1.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/sizing/stage1.py tests/app/test_app_stage1.py
git commit -m "feat(app): stage-1 closed-form filter"
```

---

### Task 5: Minimal drive model (torque-speed envelope)

**Files:**
- Create: `src/srmapp/drive/envelope.py`
- Test: `tests/app/test_app_envelope.py`

**Interfaces:**
- Consumes: `srmcore.maps.MapResult` (complete, `excited == "A"`), `srmcore.maps.tables.angle_spline`, `srmcore.model.design.RadialSRMParams`; test fixture `tests/maps/map_fixtures.synthetic_map` (Nr = 6, L0 = 2 mH, L1 = 1 mH, phase A aligned at θ = 0, currents 0 to 20 A).
- Produces:
  - `@dataclass(frozen=True) Envelope` with arrays over `speeds_rpm`: `torque` (N·m, revolution average, all phases), `power` (W), `copper_loss` (W, all phases), `theta_on`, `theta_off` (rad), `work_torque`, `work_loop` (J per stroke) and property `efficiency` (`power / (power + copper_loss)`, copper-only).
  - `envelope(result, machine, bus_voltage, resistance, speeds_rpm) -> Envelope`

Method: phase A's ψ(θ, i) and T(θ, i) are tabulated on a fine angle × current grid (angle by periodic spline, current by PCHIP). For each speed ω, every (turn-on, turn-off) angle pair on a grid is simulated at once: +V from turn-on, hysteresis limit at the map's I_max (ψ capped at ψ(θ, I_max)), −V after turn-off until the flux is zero, dψ = (V − R·i) dθ / ω. Pairs whose flux has not decayed by alignment (θ = τ) are invalid. Stroke work is ∫T dθ; the average torque is m·Nr·W/2π. ∮ i dψ is accumulated as a cross-check.

- [ ] **Step 1: Write the failing tests**

```python
import math

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import NR, PERIOD, synthetic_map

from srmapp.drive.envelope import envelope

MACHINE = make_8_6()          # Nr = 6, m = 4, matches the synthetic map
SPEEDS = np.array([100.0, 500.0, 1500.0, 3000.0, 6000.0, 12000.0])


def _env(volts=400.0, r=0.0, **kw):
    return envelope(synthetic_map(n_angles=24, **kw), MACHINE, volts, r, SPEEDS)


def test_low_speed_torque_matches_the_ideal_current_limited_stroke():
    env = _env()
    # ideal stroke at 20 A: ½ I² ΔL over the rising-inductance half pitch, ΔL ≈ 2 mH → 0.4 J
    ideal = 4 * NR * 0.4 / (2 * math.pi)
    assert 0.9 * ideal < env.torque[0] <= 1.02 * ideal


def test_power_is_torque_times_speed():
    env = _env()
    np.testing.assert_allclose(env.power, env.torque * env.speeds_rpm * 2 * math.pi / 60)


def test_torque_falls_at_high_speed():
    env = _env()
    assert env.torque[-1] < 0.5 * env.torque[0]


def test_more_bus_voltage_helps_at_high_speed():
    assert _env(volts=800.0).torque[-1] > _env(volts=400.0).torque[-1]


def test_resistance_costs_torque_and_gives_copper_loss():
    lossless, lossy = _env(r=0.0), _env(r=0.5)
    assert np.all(lossy.torque <= lossless.torque + 1e-9)
    assert np.all(lossy.copper_loss > 0)
    assert np.all(lossy.efficiency < 1.0)


def test_loop_energy_matches_torque_work():
    env = _env()
    ok = env.work_torque > 0
    np.testing.assert_allclose(env.work_loop[ok], env.work_torque[ok], rtol=0.05)


def test_no_nan_or_infinite_values_even_when_flux_cannot_decay():
    env = _env(volts=5.0)      # a tiny bus voltage cannot demagnetise before alignment at speed
    for name in ("torque", "power", "copper_loss", "theta_on", "theta_off"):
        assert np.all(np.isfinite(getattr(env, name))), name
    assert np.all(env.torque >= 0)


def test_turn_off_comes_after_turn_on():
    env = _env()
    assert np.all(env.theta_off > env.theta_on)
    assert np.all((env.theta_on >= 0) & (env.theta_off <= PERIOD))


def test_only_phase_a_maps_are_accepted():
    with pytest.raises(ValueError, match="phase A"):
        envelope(synthetic_map(excited="B"), MACHINE, 400.0, 0.0, SPEEDS)


def test_incomplete_map_is_rejected():
    with pytest.raises(ValueError):
        envelope(synthetic_map(complete=False), MACHINE, 400.0, 0.0, SPEEDS)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_envelope.py -q`
Expected: FAIL (`ModuleNotFoundError: srmapp.drive.envelope`).

- [ ] **Step 3: Implement**

`src/srmapp/drive/envelope.py`:

```python
"""Minimal drive model: torque-speed envelope of a machine from the ψ/T map of phase A (v0 spec §4.5).

Single-pulse voltage control with a hysteresis current limit at the map's I_max, ideal commutation, no
mutual coupling (the other phases are open in the map) and no iron loss. Peak-only and unvalidated."""
import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from srmcore.maps import MapResult
from srmcore.maps.run import require_complete
from srmcore.maps.tables import angle_spline
from srmcore.model.design import RadialSRMParams

N_THETA = 181                 # angle points over one rotor pole pitch
N_CURRENT = 121               # current points over 0..I_max
ON_RANGE = (0.25, 0.80)       # turn-on search range, fraction of the pitch
OFF_RANGE = (0.45, 0.95)      # turn-off search range
N_ON, N_OFF = 12, 10


@dataclass(frozen=True)
class Envelope:
    """Per-speed best stroke. `torque` is the revolution average over all phases. `work_torque` is ∫T dθ and
    `work_loop` is ∮ i dψ for the chosen stroke; they agree up to discretisation."""
    speeds_rpm: np.ndarray
    torque: np.ndarray
    power: np.ndarray
    copper_loss: np.ndarray
    theta_on: np.ndarray
    theta_off: np.ndarray
    work_torque: np.ndarray
    work_loop: np.ndarray

    @property
    def efficiency(self) -> np.ndarray:
        """Copper-only efficiency P / (P + P_cu)."""
        return self.power / np.maximum(self.power + self.copper_loss, 1e-12)


@dataclass(frozen=True)
class _Tables:
    theta: np.ndarray       # (N_THETA,), 0..period inclusive
    current: np.ndarray     # (N_CURRENT,), 0..I_max
    psi: np.ndarray         # (N_THETA, N_CURRENT), non-decreasing in current
    torque: np.ndarray      # (N_THETA, N_CURRENT)


def _tables(result: MapResult, period: float) -> _Tables:
    e = result.circuits.index(result.excited)
    current = np.linspace(0.0, result.currents[-1], N_CURRENT)
    psi = PchipInterpolator(result.currents, result.psi[..., e], axis=1)(current)
    torque = PchipInterpolator(result.currents, result.torque_arkkio, axis=1)(current)
    theta = np.linspace(0.0, period, N_THETA)
    psi_f = angle_spline(result.angles, psi, period)(theta)
    torque_f = angle_spline(result.angles, torque, period)(theta)
    return _Tables(theta, current, np.maximum.accumulate(np.maximum(psi_f, 0.0), axis=1), torque_f)


def _simulate(t: _Tables, omega: float, volts: float, r: float, on: np.ndarray, off: np.ndarray):
    """One stroke for every (on, off) index pair. Returns (work_torque, work_loop, ∫i² dθ, valid)."""
    n = on.size
    psi, i = np.zeros(n), np.zeros(n)
    w_t, w_l, i2, peak = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    dth = t.theta[1] - t.theta[0]
    for k in range(t.theta.size - 1):
        pulse = k < off
        started = k >= on
        v = np.where(pulse, volts, -volts)
        new = np.where(started, psi + (v - r * i) / omega * dth, 0.0)
        new = np.where(pulse, np.minimum(new, t.psi[k + 1, -1]), new)     # current limit while the pulse is on
        new = np.maximum(new, 0.0)
        i_new = np.interp(new, t.psi[k + 1], t.current)
        tq_old = np.interp(i, t.current, t.torque[k])
        tq_new = np.interp(i_new, t.current, t.torque[k + 1])
        w_t += 0.5 * (tq_old + tq_new) * dth * started
        w_l += 0.5 * (i + i_new) * (new - psi)
        i2 += 0.5 * (i**2 + i_new**2) * dth
        psi, i = new, i_new
        peak = np.maximum(peak, psi)
    valid = psi <= 0.01 * np.maximum(peak, 1e-12)       # flux must be gone by alignment
    return w_t, w_l, i2, valid


def envelope(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float,
             speeds_rpm) -> Envelope:
    require_complete(result)
    if result.excited != "A":
        raise ValueError("the envelope needs the phase A map (excited='A')")
    period = 2 * math.pi / machine.n_rotor_poles
    t = _tables(result, period)
    top = N_THETA - 1
    on_axis = np.unique(np.round(np.linspace(*ON_RANGE, N_ON) * top).astype(int))
    off_axis = np.unique(np.round(np.linspace(*OFF_RANGE, N_OFF) * top).astype(int))
    on, off = (a.ravel() for a in np.meshgrid(on_axis, off_axis, indexing="ij"))
    keep = off > on
    on, off = on[keep], off[keep]
    speeds = np.asarray(speeds_rpm, float)
    rows = []
    for rpm in speeds:
        omega = rpm * 2 * math.pi / 60
        w_t, w_l, i2, valid = _simulate(t, omega, bus_voltage, resistance, on, off)
        best = int(np.argmax(np.where(valid, w_t, -np.inf))) if valid.any() else -1
        if best < 0 or w_t[best] <= 0:
            rows.append((0.0, 0.0, t.theta[on[0]], t.theta[off[0]], 0.0, 0.0))
            continue
        strokes_per_rev = machine.n_phases * machine.n_rotor_poles
        rows.append((strokes_per_rev * w_t[best] / (2 * math.pi),
                     machine.n_phases * resistance * i2[best] / period,
                     t.theta[on[best]], t.theta[off[best]], w_t[best], w_l[best]))
    torque, copper, th_on, th_off, work_t, work_l = (np.array(c) for c in zip(*rows))
    return Envelope(speeds, torque, torque * speeds * 2 * math.pi / 60, copper, th_on, th_off, work_t, work_l)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_envelope.py -q`
Expected: pass. If `test_low_speed_torque_matches_the_ideal_current_limited_stroke` misses by a small margin, check that the turn-on grid contains an index at or just after 0.5 of the pitch and that `theta_off` can reach 0.95 of the pitch; widen `ON_RANGE`/`OFF_RANGE` resolution (`N_ON`, `N_OFF`) rather than the test bounds. If `test_loop_energy_matches_torque_work` fails by more than 5 %, raise `N_THETA` before touching the tolerance.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/drive/envelope.py tests/app/test_app_envelope.py
git commit -m "feat(app): minimal drive model with torque-speed envelope"
```

---

### Task 6: Stage-2 evaluation and Pareto set

**Files:**
- Create: `src/srmapp/evaluate.py`, `src/srmapp/pareto.py`
- Test: `tests/app/test_app_evaluate.py`, `tests/app/test_app_pareto.py`

**Interfaces:**
- Consumes: `Candidate`, `Requirements`, `estimates.*`, `stage1.Stage1`, `envelope.envelope`, `srmcore.maps.{build_map}`, `srmcore.maps.results.key_numbers`, `srmcore.model.errors.{InputError, MapFailed, MeshRejected, WorkerCrashed}`.
- Produces:
  - `@dataclass(frozen=True) StageTwoGrid(n_angles: int = 10, n_currents: int = 5)`
  - `speed_grid(req, n=12) -> np.ndarray` (rpm; includes `base_speed_rpm` and `max_speed_rpm` exactly, plus 10 %, 25 % and 50 % of base)
  - `requirement_ratios(env, req) -> tuple[float, float]`: (torque at base speed / required, minimum power over base..max speed / required)
  - `@dataclass(frozen=True) Evaluation` with fields `id: str`, `design: Design`, `status: str` (`"ok"`, `"cancelled"`, or the exception class name), `error: str`, `mass_kg: float`, `i_peak: float`, `torque_ratio: float`, `power_ratio: float`, `peak_power_w: float`, `power_density_kw_per_kg: float`, `efficiency_base: float`, `feasible: bool`, `envelope: Envelope | None`, `key: KeyNumbers | None`. Failed evaluations have NaN metrics and `feasible=False`.
  - `evaluate_stage2(candidate, req, stage, *, grid=StageTwoGrid(), solver="ngsolve", workers=None, cache_dir=None, progress=None, cancel=None) -> Evaluation` where `stage` is the candidate's `Stage1`.
  - `pareto_mask(values: np.ndarray, maximize: Sequence[bool]) -> np.ndarray`: boolean mask of non-dominated rows (ties are all kept).

- [ ] **Step 1: Write the failing tests**

`tests/app/test_app_pareto.py`:

```python
import numpy as np

from srmapp.pareto import pareto_mask


def test_dominated_point_is_removed():
    v = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 1.0]])
    assert pareto_mask(v, (True, True)).tolist() == [False, True, True]


def test_minimise_and_maximise_mix():
    # mass down, power up
    v = np.array([[10.0, 5.0], [8.0, 5.0], [8.0, 7.0], [12.0, 9.0]])
    assert pareto_mask(v, (False, True)).tolist() == [False, False, True, True]


def test_duplicates_are_kept():
    v = np.array([[1.0, 1.0], [1.0, 1.0]])
    assert pareto_mask(v, (True, True)).tolist() == [True, True]


def test_single_and_empty():
    assert pareto_mask(np.array([[1.0, 2.0, 3.0]]), (True, True, True)).tolist() == [True]
    assert pareto_mask(np.empty((0, 2)), (True, True)).tolist() == []
```

`tests/app/test_app_evaluate.py`:

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
from srmapp.sizing.generator import Candidate
from srmapp.sizing.stage1 import stage1
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MapFailed


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _cand():
    return Candidate("c0", Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


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


def test_failed_map_becomes_an_evaluation_and_does_not_raise():
    with mock.patch("srmapp.evaluate.build_map", side_effect=MapFailed(["3 of 50 points failed"], 3)):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert isinstance(e, Evaluation)
    assert e.status == "MapFailed" and "3 of 50" in e.error
    assert not e.feasible and math.isnan(e.torque_ratio) and e.envelope is None


def test_cancelled_map_is_reported():
    partial = synthetic_map(complete=False)
    with mock.patch("srmapp.evaluate.build_map", return_value=partial):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert e.status == "cancelled" and not e.feasible


def test_evaluation_of_a_synthetic_map_fills_the_metrics():
    m = make_8_6()
    with mock.patch("srmapp.evaluate.build_map", return_value=synthetic_map(n_angles=24)), \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), m))
    assert e.status == "ok" and e.error == ""
    assert e.mass_kg > 0 and e.peak_power_w > 0
    assert e.power_density_kw_per_kg == pytest.approx(e.peak_power_w / 1000 / e.mass_kg)
    assert 0 < e.efficiency_base <= 1
    assert e.feasible == (e.torque_ratio >= 1 and e.power_ratio >= 1)


@pytest.mark.slow
def test_real_8_6_evaluation():
    pytest.importorskip("ngsolve")
    req = _req(peak_power_w=2000.0, peak_torque_nm=6.4, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    e = evaluate_stage2(_cand(), req, stage1(req, make_8_6()), grid=StageTwoGrid(8, 4), workers=4)
    assert e.status == "ok", e.error
    assert 1.0 < e.envelope.torque[0] < stage1(req, make_8_6()).torque_upper
    assert e.key is not None and e.key.peak_torque > 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_pareto.py tests/app/test_app_evaluate.py -m "not slow" -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`src/srmapp/pareto.py`:

```python
"""Non-dominated sorting."""
from collections.abc import Sequence

import numpy as np


def pareto_mask(values: np.ndarray, maximize: Sequence[bool]) -> np.ndarray:
    """True for rows no other row dominates. Columns flagged in `maximize` are better when larger, the rest
    when smaller; identical rows are all kept."""
    v = np.asarray(values, float)
    if v.size == 0:
        return np.zeros(0, dtype=bool)
    v = v * np.where(np.asarray(maximize), 1.0, -1.0)
    mask = np.ones(len(v), dtype=bool)
    for k in range(len(v)):
        dominated_by = np.all(v >= v[k], axis=1) & np.any(v > v[k], axis=1)
        mask[k] = not dominated_by.any()
    return mask
```

`src/srmapp/evaluate.py`:

```python
"""Stage 2: reduced FEM map of one candidate plus the drive envelope and its scores (v0 spec §4.4-4.6).
Peak-only and unvalidated: no losses beyond copper, no thermal limit."""
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from srmcore.maps import build_map
from srmcore.maps.results import KeyNumbers, key_numbers
from srmcore.model.design import Design
from srmcore.model.errors import InputError, MapFailed, MeshRejected, WorkerCrashed

from .drive.envelope import Envelope, envelope
from .requirements import Requirements
from .sizing.estimates import phase_resistance
from .sizing.generator import Candidate
from .sizing.stage1 import Stage1

_NAN = float("nan")


@dataclass(frozen=True)
class StageTwoGrid:
    """Reduced map grid. Provisional until measured against the `screening` map (examples/v0_grid_study.py)."""
    n_angles: int = 10
    n_currents: int = 5


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
class Evaluation:
    id: str
    design: Design
    status: str                 # "ok", "cancelled", or the name of the exception that stopped the evaluation
    error: str
    mass_kg: float
    i_peak: float
    torque_ratio: float         # achieved / required, at base speed
    power_ratio: float          # achieved / required, worst over base..max speed
    peak_power_w: float
    power_density_kw_per_kg: float
    efficiency_base: float      # copper-only, at base speed
    feasible: bool
    envelope: Envelope | None
    key: KeyNumbers | None


def _failed(candidate: Candidate, stage: Stage1, status: str, error: str) -> Evaluation:
    return Evaluation(candidate.id, candidate.design, status, error, stage.mass.total, stage.i_peak,
                      _NAN, _NAN, _NAN, _NAN, _NAN, False, None, None)


def evaluate_stage2(candidate: Candidate, req: Requirements, stage: Stage1, *, grid: StageTwoGrid = StageTwoGrid(),
                    solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                    progress: Callable[[int, int], None] | None = None,
                    cancel: Callable[[], bool] | None = None) -> Evaluation:
    design = candidate.design
    machine = design.machine
    try:
        result = build_map(design, stage.i_peak, solver=solver, workers=workers, n_angles=grid.n_angles,
                           n_currents=grid.n_currents, cache_dir=cache_dir, progress=progress, cancel=cancel)
    except (MapFailed, MeshRejected, InputError, WorkerCrashed) as exc:
        return _failed(candidate, stage, type(exc).__name__, str(exc))
    if not result.complete:
        return _failed(candidate, stage, "cancelled", "map cancelled")
    env = envelope(result, machine, req.bus_voltage_v, phase_resistance(machine), speed_grid(req))
    torque_ratio, power_ratio = requirement_ratios(env, req)
    peak_power = float(np.max(env.power))
    at_base = int(np.argmin(np.abs(env.speeds_rpm - req.base_speed_rpm)))
    return Evaluation(candidate.id, design, "ok", "", stage.mass.total, stage.i_peak, torque_ratio, power_ratio,
                      peak_power, peak_power / 1000 / stage.mass.total, float(env.efficiency[at_base]),
                      torque_ratio >= 1.0 and power_ratio >= 1.0, env, key_numbers(result, machine))
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_pareto.py tests/app/test_app_evaluate.py -m "not slow" -q`
Expected: pass. Then `.venv\Scripts\python -m pytest tests/app/test_app_evaluate.py -m slow -q` (about 30 s); expected pass.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/evaluate.py src/srmapp/pareto.py tests/app/test_app_evaluate.py tests/app/test_app_pareto.py
git commit -m "feat(app): stage-2 evaluation and Pareto mask"
```

---

### Task 7: Search pipeline, example and grid study

**Files:**
- Create: `src/srmapp/pipeline.py`, `examples/v0_search.py`, `examples/v0_grid_study.py`
- Test: `tests/app/test_app_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `@dataclass(frozen=True) SearchSettings(n_candidates: int = 200, seed: int = 0, shortlist: int = 40, grid: StageTwoGrid = StageTwoGrid(), margin: float = 1.0)`
  - `@dataclass(frozen=True) SearchResult(requirements, sampled: int, dropped: dict[str, int], stage1_rejected: int, evaluations: tuple[Evaluation, ...], cancelled: bool)` with method `pareto(self, maximize=(False, True, True)) -> tuple[Evaluation, ...]` over `(mass_kg, power_density_kw_per_kg, efficiency_base)` for feasible evaluations only.
  - `run_search(req, settings=SearchSettings(), *, solver="ngsolve", workers=None, cache_dir=None, progress=None, cancel=None) -> SearchResult`; `progress(done, total)` counts stage-2 designs; `cancel()` is polled before each design and passed into `evaluate_stage2`.

Shortlist rule: passers of stage 1 are ranked by `torque_upper / mass` (highest first) and the first `settings.shortlist` are evaluated.

- [ ] **Step 1: Write the failing tests**

```python
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6

from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation
from srmapp.pipeline import SearchResult, SearchSettings, run_search
from srmapp.requirements import Requirements
from srmapp.sizing.generator import sample_candidates


def _req(**kw):
    values = dict(peak_power_w=5_000.0, peak_torque_nm=16.0, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _fake(candidate, req, stage, **kw):
    if kw["cancel"] is not None and kw["cancel"]():
        return Evaluation(candidate.id, candidate.design, "cancelled", "map cancelled", stage.mass.total, stage.i_peak,
                          *([float("nan")] * 5), False, None, None)
    return Evaluation(candidate.id, candidate.design, "ok", "", stage.mass.total, stage.i_peak, 1.2, 1.1,
                      5500.0, 5.5 / stage.mass.total, 0.9, True,
                      Envelope(*([np.zeros(2)] * 8)), None)


def test_search_runs_stages_in_order_and_respects_shortlist():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        res = run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                         SearchSettings(n_candidates=12, shortlist=3, seed=1))
    assert isinstance(res, SearchResult)
    assert res.sampled > 0 and ev.call_count == len(res.evaluations) == 3
    assert not res.cancelled


def test_stage1_rejections_are_counted():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        res = run_search(_req(peak_torque_nm=5000.0, peak_power_w=1.57e6),
                         SearchSettings(n_candidates=8, shortlist=3, seed=1))
    assert res.stage1_rejected == res.sampled and res.evaluations == ()


def test_cancel_returns_partial_results():
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 2
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        res = run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                         SearchSettings(n_candidates=12, shortlist=6, seed=1), cancel=cancel)
    assert res.cancelled
    assert 0 < len(res.evaluations) < 6
    assert all(e.status == "ok" for e in res.evaluations)


def test_progress_counts_designs():
    seen = []
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0), SearchSettings(n_candidates=12, shortlist=3, seed=1),
                   progress=lambda done, total: seen.append((done, total)))
    assert seen[-1] == (3, 3) and [d for d, _ in seen] == [1, 2, 3]


def test_pareto_uses_feasible_designs_only():
    cands, _ = sample_candidates(_req(), 4, seed=0)

    def ev(i, feasible, mass, density, eff):
        c = cands[i]
        return Evaluation(c.id, c.design, "ok", "", mass, 10.0, 1.1, 1.1, 1000.0, density, eff, feasible, None, None)
    evals = (ev(0, True, 10.0, 3.0, 0.9), ev(1, True, 12.0, 2.0, 0.8), ev(2, False, 5.0, 9.0, 0.99),
             ev(3, True, 8.0, 3.5, 0.85))
    res = SearchResult(_req(), 4, {}, 0, evals, False)
    ids = {e.id for e in res.pareto()}
    assert ids == {evals[0].id, evals[3].id}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/app/test_app_pipeline.py -q`
Expected: FAIL (`ModuleNotFoundError: srmapp.pipeline`).

- [ ] **Step 3: Implement**

`src/srmapp/pipeline.py`:

```python
"""Requirements to scored candidates: generate, stage-1 filter, stage-2 evaluation, Pareto set (v0 spec §4)."""
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .evaluate import Evaluation, StageTwoGrid, evaluate_stage2
from .pareto import pareto_mask
from .requirements import Requirements
from .sizing.generator import sample_candidates
from .sizing.stage1 import stage1


@dataclass(frozen=True)
class SearchSettings:
    n_candidates: int = 200
    seed: int = 0
    shortlist: int = 40
    grid: StageTwoGrid = field(default_factory=StageTwoGrid)
    margin: float = 1.0


@dataclass(frozen=True)
class SearchResult:
    requirements: Requirements
    sampled: int
    dropped: dict[str, int]
    stage1_rejected: int
    evaluations: tuple[Evaluation, ...]
    cancelled: bool

    def pareto(self, maximize=(False, True, True)) -> tuple[Evaluation, ...]:
        """Non-dominated feasible designs over (mass, power density, copper-only efficiency at base speed)."""
        ok = [e for e in self.evaluations if e.feasible]
        if not ok:
            return ()
        values = np.array([[e.mass_kg, e.power_density_kw_per_kg, e.efficiency_base] for e in ok])
        return tuple(e for e, keep in zip(ok, pareto_mask(values, maximize)) if keep)


def run_search(req: Requirements, settings: SearchSettings = SearchSettings(), *, solver: str = "ngsolve",
               workers: int | None = None, cache_dir=None,
               progress: Callable[[int, int], None] | None = None,
               cancel: Callable[[], bool] | None = None) -> SearchResult:
    candidates, dropped = sample_candidates(req, settings.n_candidates, seed=settings.seed)
    scored = [(c, stage1(req, c.design.machine, settings.margin)) for c in candidates]
    passing = [(c, s) for c, s in scored if s.passes]
    passing.sort(key=lambda cs: cs[1].torque_upper / cs[1].mass.total, reverse=True)
    shortlist = passing[:settings.shortlist]
    evaluations: list[Evaluation] = []
    cancelled = False
    for done, (candidate, stage) in enumerate(shortlist, start=1):
        if cancel is not None and cancel():
            cancelled = True
            break
        evaluation = evaluate_stage2(candidate, req, stage, grid=settings.grid, solver=solver, workers=workers,
                                     cache_dir=cache_dir, cancel=cancel)
        if evaluation.status == "cancelled":
            cancelled = True
            break
        evaluations.append(evaluation)
        if progress is not None:
            progress(done, len(shortlist))
    return SearchResult(req, len(candidates), dropped, len(scored) - len(passing), tuple(evaluations), cancelled)
```

`examples/v0_search.py`:

```python
"""Run a small requirements-driven search and print the scored candidates.

    python examples\v0_search.py [n_candidates] [shortlist]

Peak-only and unvalidated. Stage 2 takes tens of seconds per design."""
import sys
import time

from srmapp.pipeline import SearchSettings, run_search
from srmapp.requirements import Requirements

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    shortlist = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    req = Requirements(peak_power_w=10_000.0, peak_torque_nm=32.0, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    t0 = time.perf_counter()
    res = run_search(req, SearchSettings(n_candidates=n, shortlist=shortlist),
                     progress=lambda d, t: print(f"  {d}/{t} designs", flush=True))
    print(f"sampled {res.sampled}, dropped {res.dropped}, stage 1 rejected {res.stage1_rejected}, "
          f"evaluated {len(res.evaluations)} in {time.perf_counter() - t0:.0f} s")
    front = {e.id for e in res.pareto()}
    print(f"{'id':14}{'poles':>7}{'OD mm':>7}{'mass kg':>9}{'T ratio':>9}{'P ratio':>9}{'kW/kg':>7}{'eff':>6}  status")
    for e in res.evaluations:
        m = e.design.machine
        print(f"{e.id:14}{m.n_stator_poles:>4}/{m.n_rotor_poles:<2}{m.stator_outer_diameter * 1e3:7.0f}{e.mass_kg:9.2f}"
              f"{e.torque_ratio:9.2f}{e.power_ratio:9.2f}{e.power_density_kw_per_kg:7.2f}{e.efficiency_base:6.2f}  "
              f"{e.status}{' *' if e.id in front else ''}")
    print("* = Pareto front (feasible designs; mass down, kW/kg up, copper-only efficiency up)")
```

`examples/v0_grid_study.py`:

```python
"""Compare reduced stage-2 map grids with the 12 x 8 `screening` map on the example 8/6 (I_max 20 A).

    python examples\v0_grid_study.py

Prints the relative error of peak torque, La and the low-speed envelope torque, and the wall time per grid."""
import time

from conftest import make_8_6

from srmapp.drive.envelope import envelope
from srmcore.maps import build_map
from srmcore.maps.results import key_numbers
from srmcore.model.design import Design, MeshSettings

GRIDS = [(12, 8), (8, 4), (10, 5), (10, 6), (12, 5), (12, 6)]

if __name__ == "__main__":
    machine = make_8_6()
    design = Design(machine=machine, mesh=MeshSettings(preset="screening"))
    rows = {}
    for n_a, n_i in GRIDS:
        t0 = time.perf_counter()
        r = build_map(design, 20.0, n_angles=n_a, n_currents=n_i)
        wall = time.perf_counter() - t0
        k = key_numbers(r, machine)
        env = envelope(r, machine, 400.0, 0.1, [300.0, 3000.0, 9000.0])
        rows[(n_a, n_i)] = (k.peak_torque, k.la, *env.torque, wall)
    ref = rows[GRIDS[0]]
    print(f"{'grid':>8}{'T_peak':>9}{'La':>9}{'T@300':>9}{'T@3000':>9}{'T@9000':>9}{'wall s':>8}   (rel. error vs 12x8)")
    for g, v in rows.items():
        err = [abs(a - b) / abs(b) for a, b in zip(v[:5], ref[:5])]
        print(f"{g[0]:>4}x{g[1]:<3}" + "".join(f"{e:9.2%}" for e in err) + f"{v[5]:8.0f}")
```

(`examples/` scripts import `conftest` from `tests/`; run them with `set PYTHONPATH=tests` or `$env:PYTHONPATH="tests"`.)

- [ ] **Step 4: Run to verify tests pass, then measure the grid**

Run: `.venv\Scripts\python -m pytest tests/app -m "not slow" -q`
Expected: pass.

Run: `$env:PYTHONPATH="tests"; .venv\Scripts\python examples\v0_grid_study.py` (about 6 minutes). Choose the smallest grid whose peak torque and envelope torque errors are all under 3 % and whose La error is under 5 %; if that differs from `StageTwoGrid(10, 5)`, change the defaults in `evaluate.py` and rerun `tests/app`. Record the table and the chosen grid in `docs/m4-handoff.md` under a new heading "v0a grid study" (values as printed; no commentary beyond the choice).

Run: `$env:PYTHONPATH="tests"; .venv\Scripts\python examples\v0_search.py 24 6`
Expected: prints a table of six evaluated designs; a design with `status` other than `ok` is acceptable but report each such status and error text in your handoff note.

- [ ] **Step 5: Commit**

```bash
git add src/srmapp/pipeline.py examples/v0_search.py examples/v0_grid_study.py tests/app/test_app_pipeline.py src/srmapp/evaluate.py docs/m4-handoff.md
git commit -m "feat(app): search pipeline, example and grid study"
```

---

### Task 8: Documentation

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/specs/2026-09-30-v0-walking-skeleton-design.md`

- [ ] **Step 1: Update `CLAUDE.md`**

In "What this is" add one sentence after the Current state paragraph: "`src/srmapp/` holds the requirements-driven search (requirements, candidate generator, stage-1 filter, drive envelope, stage-2 evaluation, Pareto set); it imports `srmcore` public modules and `srmcore` never imports it (`tests/app/test_app_layering.py`)." In "Commands" add:

```
python examples\v0_search.py [n_candidates] [shortlist]   # requirements-driven search on a small budget (set PYTHONPATH=tests)
python examples\v0_grid_study.py                            # reduced map grids against the 12 x 8 screening map (set PYTHONPATH=tests)
```

- [ ] **Step 2: Align the v0 spec with what was built**

In `2026-09-30-v0-walking-skeleton-design.md`:
- §4.3 Stage 1: replace "magnetic-circuit estimate of peak torque and the voltage limit" with "closed-form upper bound on peak torque (saturated pole flux times the peak current, one energy rectangle per stroke) and the mass limit; the voltage limit is left to stage 2".
- §5 Layering: state the package is `srmapp` (`requirements`, `sizing`, `drive`, `evaluate`, `pareto`, `pipeline`) with the web layer to follow in plan v0b.
- §4.6: replace the score list with "peak torque, peak power, mass, power density (kW/kg), copper-only efficiency at base speed"; and §9 open item "Third Pareto axis" with "Pareto axes are mass, power density and copper-only efficiency at base speed; torque ripple is not computed in v0".
- §4: add "Peak current is J_PEAK = 15 A/mm² times the conductor area (provisional until the thermal model)."

- [ ] **Step 3: Run the fast suite**

Run: `.venv\Scripts\python -m pytest -m "not slow" -q`
Expected: all pass, under 10 minutes.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-09-30-v0-walking-skeleton-design.md
git commit -m "docs: srmapp overview and v0 spec alignment"
```

---

## Self-Review

**Spec coverage** (v0 spec): §3 requirements → Task 1. §4.1 generator → Task 3. §4.2 mass → Task 2. §4.3 stage 1 → Task 4 (voltage limit moved to stage 2, aligned in Task 8). §4.4 reduced FEM map → Tasks 6, 7 (grid measured). §4.5 drive model → Task 5. §4.6 scoring and §4.7 Pareto → Tasks 6, 7. §6 optimisation is out of this plan (second plan). §5 web layer is plan v0b. §7 tests: generator determinism/validity (Task 3), stage-1 bound against the engine (Task 4), drive closed form (Task 5), Pareto (Task 6), pipeline lifecycle (Task 7); the API/frontend tests belong to v0b.

**Placeholder scan:** none; every step has code or an exact command. The two measured-and-adjust steps (Task 2 mesh comparison, Task 7 grid choice) state the action and the stop condition.

**Type consistency:** `Stage1(mass, i_peak, torque_upper, passes, reason)` is used the same way in Tasks 4, 6, 7; `Envelope` has 8 array fields in the order (speeds_rpm, torque, power, copper_loss, theta_on, theta_off, work_torque, work_loop) in Tasks 5, 6, 7 tests; `Evaluation` field order matches between `_failed`, `evaluate_stage2` and the Task 7 test helpers; `Candidate(id, design)` everywhere.

**Review Focus coverage:** mm-looking OD (Task 1 test), restrictive limits (Task 3 test), undecayed flux (Task 5 test), map exceptions (Task 6 test), cancel (Task 7 test).
