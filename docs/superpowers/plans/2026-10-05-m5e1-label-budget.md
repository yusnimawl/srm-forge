# M5e1 EM-validated label and uncertainty budget — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `em_validate(design, map)` decides the "EM-validated" label (§8.5) and returns the §8.4 worst-case uncertainty budget; `iron_b_peak` becomes mesh-independent.

**Architecture:** `b_peak` becomes the area-weighted 99.9th percentile of iron |B| (`maps/point.py`); the `iron_b_peak` check compares it with the last stacked B-H point. A new `maps/validation.py` solves 4 key points on the `full` and `reference` meshes and with Js ±2 %, builds label checks from those solves plus `fem_checks`, and sums the budget rows. Nothing is stored in HDF5.

**Tech Stack:** Python 3.12+, numpy, NGSolve (primary) / scikit-fem, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-m5e1-label-budget-design.md` (read it first).

## Global Constraints

- SI units everywhere. Comments describe the code as it is now (no task or plan history).
- Import rules (`tests/test_import_rules.py`): `maps` may import every lower layer; never import `gmsh`, `skfem`, `ngsolve`, `netgen` outside `geometry/`, `mesh/`, `solvers/`.
- `srmcore.materials` exports nothing: import from `srmcore.materials.library` / `.laws` / `.schema`.
- Test file basenames must be unique (`tests/` has no `__init__.py`).
- Fast suite is at 9:21 of a 10 min budget: new fast tests must not run FEM solves except the one assertion added to an existing solve in Task 1. Long tests get `@pytest.mark.slow`.
- **Hard rule for implementers: edit files only with the Edit/Write tools. Never rewrite files with sed, printf, shell redirection or scripts.** Write the report file the controller names.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01CbruYpPDmwKKLAxkRybGjo
  ```
- Run Python as `.venv\Scripts\python` from the repo root `D:\y\srm-designer`.

## Review Focus

1. A key-point solve that is NONCONVERGED must make its convergence check `fail` (NaN value, "non-finite" detail), never `pass` — test in Task 4.
2. Stator and rotor on different materials: the Js variant must change both laws and the budget must use the worse grade — test in Task 3 (law swap) and Task 4 (grade).
3. A `screening` map passed to `em_validate` must return `label=None` with `preset` failing, not raise — test in Task 4.
4. `iron_b_peak` with NaN `b_peak` must stay non-pass (existing `test_nan_in_a_field_is_not_a_pass` must keep passing) — Task 1.
5. Cached maps built with the old `b_peak` definition must not be served: the srmcore version moves to 0.3.0 and the editable install is refreshed so `importlib.metadata.version("srmcore")` reports it — Task 1.

---

### Task 1: `b_peak` as area 99.9th percentile; `iron_b_peak` against the last B-H point; version 0.3.0

**Files:**
- Modify: `src/srmcore/maps/point.py` (add `B_PEAK_QUANTILE`, `area_quantile`, element areas, `b_peak` line ~52, field comment ~36)
- Modify: `src/srmcore/maps/run.py:47` (field comment)
- Modify: `src/srmcore/maps/checks.py` (the `iron_b_peak` lines ~120 and ~146-147)
- Modify: `src/srmcore/maps/dataset.py` (any `b_peak` description text, if present)
- Modify: `pyproject.toml` (`version = "0.3.0"`), `src/srmcore/__init__.py` (`__version__ = "0.3.0"`)
- Test: `tests/maps/test_point.py`, `tests/maps/test_checks.py`
- Regenerate: `tests/maps/goldens_8_6.json`

**Interfaces:**
- Produces: `srmcore.maps.point.B_PEAK_QUANTILE = 0.999`; `srmcore.maps.point.area_quantile(values: np.ndarray, areas: np.ndarray, q: float = B_PEAK_QUANTILE) -> float`; `iron_b_peak` check value = max(`b_peak`) / B_last, limit 1.0, status `warn` above.

- [ ] **Step 1: Write the failing tests**

Add to `tests/maps/test_point.py` (import `area_quantile` from `srmcore.maps.point`):

```python
def test_area_quantile_ignores_a_tiny_hot_element():
    values = np.array([1.0] * 999 + [9.0])
    areas = np.array([1.0] * 999 + [1e-6])
    assert area_quantile(values, areas) == 1.0


def test_area_quantile_of_a_uniform_field_is_that_field():
    assert area_quantile(np.full(5, 2.0), np.arange(1.0, 6.0)) == 2.0


def test_area_quantile_sees_a_hot_region_with_real_area():
    assert area_quantile(np.array([1.0, 3.0]), np.array([0.5, 0.5])) == 3.0
```

In `test_matches_the_manual_chain`, after the existing asserts, add:

```python
    kind = np.array([problem.region_kind[n] for n in problem.region_names])[problem.element_region]
    iron = (kind == "stator_iron") | (kind == "rotor_iron")
    t = problem.nodes[problem.triangles[iron]]
    area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    b = np.hypot(solution.b[iron, 0], solution.b[iron, 1])
    assert result.b_peak == pytest.approx(area_quantile(b, area), rel=1e-12)
    assert result.b_peak < b.max()
```

In `tests/maps/test_checks.py`, replace `test_iron_b_peak_warns_above_1p5_js` with:

```python
def test_iron_b_peak_warns_above_the_last_bh_point():
    from srmcore.materials.laws import library_law
    b_last = min(library_law(M.materials.stator).bn, library_law(M.materials.rotor).bn)
    ok = by_name(good_map(b_peak=0.99 * b_last))["iron_b_peak"]
    assert ok.status == "pass" and ok.limit == 1.0 and ok.value == pytest.approx(0.99)
    assert by_name(good_map(b_peak=1.01 * b_last))["iron_b_peak"].status == "warn"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/maps/test_point.py tests/maps/test_checks.py -q`
Expected: FAIL (`area_quantile` cannot be imported; `iron_b_peak` value/limit differ).

- [ ] **Step 3: Implement**

In `src/srmcore/maps/point.py`, below the imports:

```python
B_PEAK_QUANTILE = 0.999   # area fraction of iron below b_peak; the element maximum diverges at the pole corners


def area_quantile(values: np.ndarray, areas: np.ndarray, q: float = B_PEAK_QUANTILE) -> float:
    """Smallest value v such that elements with value <= v hold at least the fraction q of the total area."""
    order = np.argsort(values)
    cum = np.cumsum(areas[order])
    return float(values[order][np.searchsorted(cum, q * cum[-1])])
```

Replace the `b_peak = ...max()` line in `solve_point` with:

```python
    t = problem.nodes[problem.triangles[iron]]
    area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    b_peak = area_quantile(np.hypot(solution.b[iron, 0], solution.b[iron, 1]), area)
```

Change the `PointResult.b_peak` comment to `# T: area-weighted B_PEAK_QUANTILE of |B| over the stator and rotor iron` and the same wording on `MapResult.b_peak` in `run.py`. If `dataset.py` describes `b_peak` in text, use the same wording.

In `src/srmcore/maps/checks.py`: import `from ..materials.laws import library_law`. Replace the `iron_b_peak` lines with:

```python
    # Above the last stacked B-H point the law is the Js tail, not data.
    b_last = min(library_law(m.materials.stator).bn, library_law(m.materials.rotor).bn)
    b = float(np.max(result.b_peak)) / b_last
    checks.append(_upper("iron_b_peak", b, 1.0,
                         "area p99.9 iron |B| / last stacked B-H point (beyond it the law is the Js tail)", bad="warn"))
```

(`m` is `design.machine` in `_map_checks`; check the local name there and use it. `js` is still used by `psi_bound`; leave that.)

Set `version = "0.3.0"` in `pyproject.toml` and `__version__ = "0.3.0"` in `src/srmcore/__init__.py`. Refresh the installed metadata: `.venv\Scripts\python -m pip install -e . --no-deps -q`, then check `.venv\Scripts\python -c "from importlib.metadata import version; print(version('srmcore'))"` prints `0.3.0`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/maps/test_point.py tests/maps/test_checks.py -q`
Expected: PASS (including `test_nan_in_a_field_is_not_a_pass`).

- [ ] **Step 5: Regenerate the goldens and run the slow golden test**

Run: `$env:SRM_REGEN_GOLDENS = "1"; .venv\Scripts\python -m pytest tests/maps/test_goldens.py -m slow -q; Remove-Item Env:SRM_REGEN_GOLDENS; .venv\Scripts\python -m pytest tests/maps/test_goldens.py -m slow -q`
Expected: `git diff tests/maps/goldens_8_6.json` shows only `"iron_b_peak": "warn"` → `"pass"` (key numbers unchanged to the printed digits). If anything else changes, stop and report.

- [ ] **Step 6: Commit**

```bash
git add src/srmcore/maps/point.py src/srmcore/maps/run.py src/srmcore/maps/checks.py src/srmcore/maps/dataset.py pyproject.toml src/srmcore/__init__.py tests/maps/test_point.py tests/maps/test_checks.py tests/maps/goldens_8_6.json
git commit -m "feat: b_peak as area p99.9 of iron |B|; iron_b_peak against the last B-H point; srmcore 0.3.0"
```

---

### Task 2: `digitisation_error` on soft-magnetic materials

**Files:**
- Modify: `src/srmcore/materials/schema.py:56-70` (`SoftMagneticMaterial`)
- Test: `tests/materials/test_material_library.py`

**Interfaces:**
- Produces: `SoftMagneticMaterial.digitisation_error: float | None` (relative B error of a digitised curve; `None` means 0 in the budget; `0 <= x < 0.5`).

- [ ] **Step 1: Write the failing test**

```python
def test_digitisation_error_is_optional_and_bounded():
    m = load_material("M19")
    assert m.digitisation_error is None
    data = m.model_dump()
    assert SoftMagneticMaterial.model_validate({**data, "digitisation_error": 0.02}).digitisation_error == 0.02
    for bad in (-0.01, 0.5):
        with pytest.raises(ValidationError):
            SoftMagneticMaterial.model_validate({**data, "digitisation_error": bad})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/materials/test_material_library.py -q`
Expected: FAIL (`digitisation_error` unknown / extra field).

- [ ] **Step 3: Implement**

In `SoftMagneticMaterial`, after `saturation_polarisation_source: str`:

```python
    digitisation_error: float | None = Field(default=None, ge=0, lt=0.5)   # relative B error of a digitised curve
```

- [ ] **Step 4: Run the materials tests**

Run: `.venv\Scripts\python -m pytest tests/materials -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/materials/schema.py tests/materials/test_material_library.py
git commit -m "feat: optional digitisation_error on soft-magnetic materials"
```

---

### Task 3: Key points and key-point solves (with Js scaling)

**Files:**
- Create: `src/srmcore/maps/validation.py`
- Test: `tests/maps/test_em_validation.py`

**Interfaces:**
- Consumes: `key_numbers(result, machine) -> KeyNumbers` (`maps/results.py`), `LA_CURRENT_FRACTION` (`maps/grids.py`), `mesh_at_angle`, `machine_problem`, `flux_linkage`, `arkkio_torque`, `library_law`, `law_for_material`, `load_material`, `SolveStatus`.
- Produces:
  ```python
  KEYS = ("la", "lu", "peak_torque", "psi_max")
  @dataclass(frozen=True)
  class KeyPoint:
      key: str        # one of KEYS
      angle: float    # rad
      current: float  # A in the excited circuit
  def key_points(result: MapResult, machine: RadialSRMParams) -> tuple[KeyPoint, ...]   # in KEYS order
  def js_laws(design: Design, factor: float) -> dict[int, ReluctivityLaw]
      # id(library_law(name)) -> law with Js·factor, for the stator and rotor materials; raises InputError when
      # the B-H data already exceed Js·factor
  def point_values(static: StaticMesh, design: Design, points: Sequence[KeyPoint], excited: str,
                   solver: SolverAdapter, js_factor: float = 1.0) -> dict[str, float]
      # la, lu -> ψ/i (H); psi_max -> ψ (Wb-turns); peak_torque -> |Arkkio torque| (N·m); NaN for a
      # NONCONVERGED solve
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/maps/test_em_validation.py`:

```python
"""em_validate and its parts (spec docs/superpowers/specs/2026-10-05-m5e1-label-budget-design.md)."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from map_fixtures import synthetic_map
from srmcore.maps.validation import KEYS, KeyPoint, js_laws, key_points
from srmcore.materials.laws import library_law
from srmcore.model.design import Design, MeshSettings, RegionMaterials
from srmcore.model.errors import InputError

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))


def test_key_points_follow_the_key_numbers():
    r = synthetic_map(n_angles=16)
    pts = {p.key: p for p in key_points(r, DESIGN.machine)}
    assert tuple(pts) == KEYS
    i_max = r.currents[-1]
    tau = 2 * math.pi / DESIGN.machine.n_rotor_poles
    assert pts["la"] == KeyPoint("la", 0.0, 0.05 * i_max)
    assert pts["lu"].angle == pytest.approx(tau / 2) and pts["lu"].current == pytest.approx(0.05 * i_max)
    assert pts["psi_max"] == KeyPoint("psi_max", 0.0, i_max)
    a, i = np.unravel_index(np.argmax(np.abs(r.torque_arkkio)), r.torque_arkkio.shape)
    assert pts["peak_torque"] == KeyPoint("peak_torque", float(r.angles[a]), float(r.currents[i]))


def test_js_laws_scale_both_iron_materials():
    d = DESIGN.model_copy(update={"machine": DESIGN.machine.model_copy(
        update={"materials": RegionMaterials(stator="M19", rotor="steel_1010")})})
    laws = js_laws(d, 1.02)
    for name in ("M19", "steel_1010"):
        base = library_law(name)
        assert laws[id(base)].js == pytest.approx(1.02 * base.js)
        assert laws[id(base)].bn == pytest.approx(base.bn)


def test_js_minus_two_percent_is_forbidden_by_the_m19_data():
    with pytest.raises(InputError):
        js_laws(DESIGN, 0.98)
```

`BHCurve.js` is the stacked Js, k·Js (checked: M19 2.03 T → 1.9894 T; ×1.02 → 2.0292 T), so it scales by the same factor.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/maps/test_em_validation.py -q`
Expected: FAIL (module `srmcore.maps.validation` missing).

- [ ] **Step 3: Implement**

Create `src/srmcore/maps/validation.py`:

```python
"""EM-validated label (spec §8.5) and the worst-case uncertainty budget of the key numbers (§8.4)."""
import dataclasses
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..fields.solution import SolveStatus
from ..materials.laws import ReluctivityLaw, law_for_material, library_law
from ..materials.library import load_material
from ..mesh.machine import mesh_at_angle
from ..mesh.static import StaticMesh
from ..model.design import Design, RadialSRMParams
from ..physics.build import machine_problem
from ..post.quantities import arkkio_torque, flux_linkage
from ..solvers.settings import SolverAdapter
from .grids import LA_CURRENT_FRACTION
from .results import key_numbers
from .run import MapResult

KEYS = ("la", "lu", "peak_torque", "psi_max")


@dataclass(frozen=True)
class KeyPoint:
    key: str
    angle: float      # rad
    current: float    # A in the excited circuit


def key_points(result: MapResult, machine: RadialSRMParams) -> tuple[KeyPoint, ...]:
    """Where each key number is read: La and Lu at LA_CURRENT_FRACTION · I_max, ψ_max at the aligned angle and
    I_max, peak torque at the grid point of largest |Arkkio torque|."""
    key = key_numbers(result, machine)
    i_lo = LA_CURRENT_FRACTION * key.i_max
    a, i = np.unravel_index(np.argmax(np.abs(result.torque_arkkio)), result.torque_arkkio.shape)
    return (KeyPoint("la", key.aligned_angle, i_lo), KeyPoint("lu", key.unaligned_angle, i_lo),
            KeyPoint("peak_torque", float(result.angles[a]), float(result.currents[i])),
            KeyPoint("psi_max", key.aligned_angle, key.i_max))


def js_laws(design: Design, factor: float) -> dict[int, ReluctivityLaw]:
    """id(library law) -> the same material's law with its saturation polarisation times `factor`, for the
    stator and rotor materials. Raises InputError when the B-H data already exceed the scaled Js."""
    out = {}
    for name in {design.machine.materials.stator, design.machine.materials.rotor}:
        mat = load_material(name)
        out[id(library_law(name))] = law_for_material(
            mat.model_copy(update={"saturation_polarisation": mat.saturation_polarisation * factor}))
    return out


def point_values(static: StaticMesh, design: Design, points: Sequence[KeyPoint], excited: str,
                 solver: SolverAdapter, js_factor: float = 1.0) -> dict[str, float]:
    """Each key number from one solve at its key point; NaN where the solve did not converge."""
    swap = js_laws(design, js_factor) if js_factor != 1.0 else {}
    out = {}
    for p in points:
        problem = machine_problem(mesh_at_angle(static, p.angle), design, {excited: p.current})
        if swap:
            problem = dataclasses.replace(problem, laws=tuple(swap.get(id(law), law) for law in problem.laws))
        sol = solver.solve(problem)
        if sol.status is SolveStatus.NONCONVERGED:
            out[p.key] = float("nan")
            continue
        psi = float(flux_linkage(problem, sol)[problem.winding.circuits.index(excited)])
        out[p.key] = {"la": psi / p.current, "lu": psi / p.current, "psi_max": psi,
                      "peak_torque": abs(arkkio_torque(problem, sol))}[p.key]
    return out
```

(`math` is used in Task 4; keep the import or add it there — the final file must have no unused imports.)

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/maps/test_em_validation.py tests/test_import_rules.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/maps/validation.py tests/maps/test_em_validation.py
git commit -m "feat: key points and key-point solves with Js scaling for em_validate"
```

---

### Task 4: Budget, label checks, `em_validate`, exports

**Files:**
- Modify: `src/srmcore/maps/validation.py`
- Modify: `src/srmcore/maps/__init__.py` (exports)
- Test: `tests/maps/test_em_validation.py`

**Interfaces:**
- Consumes: Task 3 (`KEYS`, `KeyPoint`, `key_points`, `point_values`), `fem_checks(design, result, *, solver, workers) -> tuple[Check, ...]`, `Check`, `_upper` (`maps/checks.py`), `end_winding_inductance(machine, image_factor) -> float` (H per phase, `maps/end_winding.py`), `build_machine_mesh`, `make_solver`, `require_complete`.
- Produces:
  ```python
  VALIDATED_VERSIONS: tuple[str, ...] = ()
  LABEL = "EM-validated"
  PSI_POINT_TOLERANCE = 0.005
  TORQUE_POINT_TOLERANCE = 0.01
  JS_STEP = 0.02
  GRADE_ALLOWANCE = {"A": 0.0, "B": 0.03, "C": 0.10}
  END_WINDING_IMAGE = (1.0, 2.0)          # bounds; the corrected values use the midpoint
  @dataclass(frozen=True) class BudgetRow: source: str; rel: dict[str, float]; note: str
  @dataclass(frozen=True) class UncertaintyBudget: values_2d: dict[str, float]; values: dict[str, float]; rows: tuple[BudgetRow, ...]; total: dict[str, float]
  @dataclass(frozen=True) class EmValidation: label: str | None; checks: tuple[Check, ...]; budget: UncertaintyBudget; engine_version: str; material_grades: dict[str, str]
  def em_validate(design: Design, result: MapResult, *, solver: str = "ngsolve", workers: int | None = None) -> EmValidation
  ```

`em_validate` steps:
1. `require_complete(result)`; `pts = key_points(result, design.machine)`; `adapter = make_solver(solver)`.
2. For `preset` in `("full", "reference")`: `d = design` with `mesh.preset = preset`; `vals[preset] = point_values(build_machine_mesh(d), d, pts, result.excited, adapter)`.
3. Own mesh: `own = design.mesh.preset`; `static = build_machine_mesh(design)`; `nominal = vals[own] if own in vals else point_values(static, design, pts, ...)`.
4. `plus = point_values(static, design, pts, ..., js_factor=1 + JS_STEP)`; `minus = point_values(..., js_factor=1 - JS_STEP)` inside `try/except InputError: minus = None`.
5. `fem = fem_checks(design, result, solver=solver, workers=workers)`.
6. Budget and checks as below; `label = LABEL if all(c.status == "pass" for c in checks) else None`.

Budget rows (relative; `rel(a, b) = abs(a - b) / abs(b)`):
- `mesh`: `rel(vals["full"][k], vals["reference"][k])` per key.
- `material`: Js part `abs(plus[k] - minus[k]) / 2 / abs(nominal[k])`, or `rel(plus[k], nominal[k])` when `minus is None`; plus `GRADE_ALLOWANCE[worst]`, `worst = max(grades)` (with "A" < "B" < "C" as strings). Note names `"Js ±2 %"` or `"Js +2 % only (B-H data exceed Js − 2 %)"` and the grade.
- `end_effect`: `l1, l2 = (end_winding_inductance(m, k) for k in END_WINDING_IMAGE)`; `half = (l2 - l1) / 2`; `l_mid = (l1 + l2) / 2`; values: `la + l_mid`, `lu + l_mid`, `psi_max + l_mid * i_max`, torque unchanged; rel: `half / values["la"]`, `half / values["lu"]`, `half * i_max / values["psi_max"]`, `0.0`. Note: `"end winding, image factor 1 to 2; iron-end 3D fringing not modelled"`.
- `digitisation`: `max(load_material(n).digitisation_error or 0.0 for n in (stator, rotor))` for every key.
- `values_2d` from `key_numbers(result, machine)` (`la`, `lu`, `peak_torque`, `psi_max`); `total[k] = sum(row.rel[k] for row in rows)`.

Checks:

```python
checks = (
    Check("engine_version", "pass" if version("srmcore") in VALIDATED_VERSIONS else "fail", float("nan"), float("nan"),
          f"srmcore {version('srmcore')}; validated versions: {', '.join(VALIDATED_VERSIONS) or 'none'}"),
    Check("preset", "pass" if own in ("full", "reference") else "fail", float("nan"), float("nan"),
          f"map preset {own}; the label needs full or reference"),
    Check("no_filled_points", "fail" if bool(np.any(result.filled)) else "pass", float(np.sum(result.filled)), 0.0,
          "points replaced by interpolation after a non-converged solve"),
    _upper("point_convergence_psi", max(rel(vals['full'][k], vals['reference'][k]) for k in ("la", "lu", "psi_max")),
           PSI_POINT_TOLERANCE, "full vs reference mesh ψ at the La, Lu and ψ_max points"),
    _upper("point_convergence_torque", rel(vals["full"]["peak_torque"], vals["reference"]["peak_torque"]),
           TORQUE_POINT_TOLERANCE, "full vs reference mesh torque at the peak-torque point, relative to peak torque"),
    *fem,
    Check("material_grade", "pass" if all(grades.values()) else "fail", float("nan"), float("nan"),
          f"stator {grades['stator']}, rotor {grades['rotor']}"),
)
```

`max` over values containing NaN: use `float(np.max([...]))` so a NaN propagates (Python's `max` can hide NaN); `_upper` then returns `fail` with "non-finite". For a `screening` map `fem_checks` returns `()`; add `Check("fem_checks", "fail", nan, nan, "held-out and band-radius checks run only on full and reference maps")` when `fem` is empty so the label can never pass without them.

- [ ] **Step 1: Write the failing tests** (append to `tests/maps/test_em_validation.py`; no FEM — the solves are monkeypatched)

```python
import dataclasses
from srmcore.maps import validation as V
from srmcore.maps.checks import Check

GOOD = {"la": 0.03, "lu": 0.004, "peak_torque": 12.0, "psi_max": 0.3}


def _patch(monkeypatch, *, ref_scale=1.0, minus_ok=True, nan_key=None, fem_status="pass", versions=()):
    def fake_values(static, design, points, excited, solver, js_factor=1.0):
        if js_factor < 1 and not minus_ok:
            raise InputError([])
        v = {k: x * (1 + 0.01 * (js_factor - 1) / V.JS_STEP) for k, x in GOOD.items()}
        if static == "reference":
            v = {k: x * ref_scale for k, x in v.items()}
        if nan_key and static == "full":
            v[nan_key] = float("nan")
        return v
    monkeypatch.setattr(V, "point_values", fake_values)
    monkeypatch.setattr(V, "build_machine_mesh", lambda d: d.mesh.preset)
    monkeypatch.setattr(V, "make_solver", lambda name, threads=None: None)
    monkeypatch.setattr(V, "fem_checks", lambda d, r, solver, workers: (
        () if d.mesh.preset == "screening" else (Check("held_out_psi", fem_status, 0.0, 0.005, ""),)))
    monkeypatch.setattr(V, "VALIDATED_VERSIONS", versions)


def _map():
    return synthetic_map(n_angles=16)


def test_label_awarded_only_when_every_check_passes(monkeypatch):
    from importlib.metadata import version
    _patch(monkeypatch, versions=(version("srmcore"),))
    v = V.em_validate(DESIGN, _map())
    assert v.label == V.LABEL and all(c.status == "pass" for c in v.checks)
    assert v.material_grades == {"stator": "C", "rotor": "C"}


def test_unvalidated_engine_version_blocks_the_label(monkeypatch):
    _patch(monkeypatch)
    v = V.em_validate(DESIGN, _map())
    assert v.label is None
    assert {c.name for c in v.checks if c.status != "pass"} == {"engine_version"}


def test_screening_map_is_never_labelled(monkeypatch):
    from importlib.metadata import version
    _patch(monkeypatch, versions=(version("srmcore"),))
    d = DESIGN.model_copy(update={"mesh": MeshSettings(preset="screening")})
    v = V.em_validate(d, _map())
    failed = {c.name for c in v.checks if c.status != "pass"}
    assert v.label is None and {"preset", "fem_checks"} <= failed


def test_filled_point_blocks_the_label(monkeypatch):
    _patch(monkeypatch)
    r = _map()
    filled = r.filled.copy(); filled[3, 2] = True
    v = V.em_validate(DESIGN, dataclasses.replace(r, filled=filled))
    assert {c.name: c.status for c in v.checks}["no_filled_points"] == "fail"


def test_mesh_difference_beyond_tolerance_fails_and_enters_the_budget(monkeypatch):
    _patch(monkeypatch, ref_scale=1.01)
    v = V.em_validate(DESIGN, _map())
    status = {c.name: c.status for c in v.checks}
    assert status["point_convergence_psi"] == "fail" and status["point_convergence_torque"] == "pass"
    mesh = next(r for r in v.budget.rows if r.source == "mesh")
    assert mesh.rel["la"] == pytest.approx(0.01 / 1.01)


def test_nonconverged_key_point_fails_its_check(monkeypatch):
    _patch(monkeypatch, nan_key="peak_torque")
    c = {c.name: c for c in V.em_validate(DESIGN, _map()).checks}["point_convergence_torque"]
    assert c.status == "fail" and "non-finite" in c.detail


def test_budget_rows_sum_and_use_the_corrected_values(monkeypatch):
    from srmcore.maps.end_winding import end_winding_inductance
    from srmcore.maps.results import key_numbers
    _patch(monkeypatch)
    r = _map()
    b = V.em_validate(DESIGN, r).budget
    assert [row.source for row in b.rows] == ["mesh", "material", "end_effect", "digitisation"]
    for k in V.KEYS:
        assert b.total[k] == pytest.approx(sum(row.rel[k] for row in b.rows))
    key = key_numbers(r, DESIGN.machine)
    l1, l2 = (end_winding_inductance(DESIGN.machine, f) for f in V.END_WINDING_IMAGE)
    assert b.values_2d["la"] == key.la
    assert b.values["la"] == pytest.approx(key.la + (l1 + l2) / 2)
    assert b.values["peak_torque"] == key.peak_torque
    material = next(row for row in b.rows if row.source == "material")
    assert material.rel["la"] == pytest.approx(0.01 + V.GRADE_ALLOWANCE["C"])     # Js ±2 % gives ±1 % in the fake
    end = next(row for row in b.rows if row.source == "end_effect")
    assert end.rel["peak_torque"] == 0.0 and end.rel["la"] == pytest.approx((l2 - l1) / 2 / b.values["la"])


def test_js_minus_forbidden_uses_plus_only(monkeypatch):
    _patch(monkeypatch, minus_ok=False)
    material = next(row for row in V.em_validate(DESIGN, _map()).budget.rows if row.source == "material")
    assert material.rel["la"] == pytest.approx(0.01 + V.GRADE_ALLOWANCE["C"])
    assert "+2 % only" in material.note


def test_worse_grade_sets_the_allowance(monkeypatch):
    real = V.load_material
    def graded(name):
        m = real(name)
        return m.model_copy(update={"confidence": "B"}) if name == "steel_1010" else m
    monkeypatch.setattr(V, "load_material", graded)
    _patch(monkeypatch)
    d = DESIGN.model_copy(update={"machine": DESIGN.machine.model_copy(
        update={"materials": RegionMaterials(stator="steel_1010", rotor="M19")})})
    v = V.em_validate(d, _map())
    assert v.material_grades == {"stator": "B", "rotor": "C"}
    material = next(row for row in v.budget.rows if row.source == "material")
    assert material.rel["la"] == pytest.approx(0.01 + V.GRADE_ALLOWANCE["C"])
```

Notes for the implementer: the fake keys the mesh by the preset string because `build_machine_mesh` is patched to return it. `em_validate` must call `point_values`, `build_machine_mesh`, `make_solver`, `fem_checks` and `load_material` through the module globals of `validation.py` (plain `from ... import name` at the top of the module, called by bare name) so the monkeypatches take effect. The synthetic map's 16 angles include θ = 0 and its currents include 5 % of I_max.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/maps/test_em_validation.py -q`
Expected: the new tests FAIL (`em_validate` missing).

- [ ] **Step 3: Implement** the constants, dataclasses and `em_validate` in `validation.py` as specified above (imports: `from importlib.metadata import version`, `from ..mesh import build_machine_mesh`, `from ..model.errors import InputError`, `from ..solvers.factory import make_solver`, `from .checks import Check, _upper`, `from .end_winding import end_winding_inductance`, `from .fem_checks import fem_checks`, `from .run import require_complete`). Add to `src/srmcore/maps/__init__.py`: `from .validation import VALIDATED_VERSIONS, BudgetRow, EmValidation, UncertaintyBudget, em_validate` and the five names in `__all__` (sorted as the list is now).

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/maps/test_em_validation.py tests/test_import_rules.py -q`
Expected: PASS. Then the whole fast suite once: `.venv\Scripts\python -m pytest -m "not slow" -q` — expected all pass; report the wall time.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/maps/validation.py src/srmcore/maps/__init__.py tests/maps/test_em_validation.py
git commit -m "feat: em_validate: EM-validated label checks and worst-case uncertainty budget"
```

---

### Task 5: Slow end-to-end test, example, docs

**Files:**
- Create: `examples/em_validate_8_6.py`
- Test: `tests/maps/test_em_validation.py` (one slow test)
- Modify: `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` (§9 M5 row, §10 two [M5a→M5] items, §11 entry), `CLAUDE.md`, `docs/m5-roadmap.md`
- Create: `docs/handoff-2026-10-05-m5e2.md`

**Interfaces:**
- Consumes: `em_validate`, `build_map(design, i_max, *, solver, n_angles, n_currents, workers, cache_dir)`.

- [ ] **Step 1: Slow test** (append to `tests/maps/test_em_validation.py`):

```python
@pytest.mark.slow
def test_em_validate_end_to_end_on_the_8_6_full_mesh(tmp_path):
    pytest.importorskip("ngsolve")
    from srmcore.maps import build_map, em_validate
    r = build_map(DESIGN, 20.0, n_angles=16, n_currents=6, cache_dir=tmp_path)
    v = em_validate(DESIGN, r)
    status = {c.name: c.status for c in v.checks}
    assert v.label is None and status["engine_version"] == "fail"
    for name in ("preset", "no_filled_points", "point_convergence_psi", "point_convergence_torque", "material_grade"):
        assert status[name] == "pass", name
    assert {"held_out_psi", "held_out_torque", "band_radius"} <= set(status)
    for k in ("la", "lu", "peak_torque", "psi_max"):
        assert 0 < v.budget.total[k] < 0.5 and np.isfinite(v.budget.values[k])
    assert "+2 % only" in next(row for row in v.budget.rows if row.source == "material").note
```

(The coarse 16 × 6 grid keeps the test short; held-out results are not asserted here — the example below runs the default `full` grid.)

Run: `.venv\Scripts\python -m pytest tests/maps/test_em_validation.py -m slow -q` — expected PASS; report the time.

- [ ] **Step 2: Example** `examples/em_validate_8_6.py`: builds the 8/6 golden design (same parameters as `tests/maps/test_goldens.py::_design`) at preset `full`, `build_map(design, 20.0, workers=int(sys.argv[1]) if len(sys.argv) > 1 else None)` with default grids, `em_validate`, prints every check (name, status, value, limit, detail), the budget table (rows × keys in %, total) and 2D vs corrected values, and the label. `if __name__ == "__main__":` guard (spawn pool on Windows). Add it to the CLAUDE.md commands list: `python examples\em_validate_8_6.py [workers]   # EM-validated checks and uncertainty budget on the 8/6 full map (about 1 h)`.

- [ ] **Step 3: Docs**
  - Spec §10: mark "[M5a→M5] Band noise" and "[M5a→M5] `iron_b_peak` definition" as decided 2026-10-05 (see §11).
  - Spec §11: add a 2026-10-05 row "M5e1 label and budget (owner decisions)" listing decisions 1–12 of the M5e1 spec in one paragraph, with the spike numbers.
  - Spec §9 M5 row: add "label logic and uncertainty budgets done in M5e1 (`maps/validation.py`)".
  - CLAUDE.md: current state (M5e1 done, M5e2 next), version 0.3.0, a "Map products" item 9 for `maps/validation.py` `em_validate` (label checks, budget rows, `VALIDATED_VERSIONS` empty until M5e2), the `b_peak` definition (area p99.9) in item 7, and under Conventions: "Map check warnings are informational; no optimizer or search may use a `warn` as a constraint."
  - `docs/m5-roadmap.md` M5e: split into M5e1 (done, link the spec) and M5e2 (remaining scope: library adds, validation report including the `em_validate_8_6` result, add the version to `VALIDATED_VERSIONS`, CI slow suite on Linux, speed budgets, adaptive `reference` only if a design fails).
  - `docs/handoff-2026-10-05-m5e2.md`: start prompt `read docs/handoff-2026-10-05-m5e2.md and start M5e2`, state of the repo, M5e2 scope and owner decisions still open (speed budgets, library data sources for 10JNEX900 / Hiperco 50A / 50HS / M43, CI slow-suite runner and time, report format), process notes copied from `docs/handoff-2026-10-03-m5bcde.md`.

- [ ] **Step 4: Commit**

```bash
git add examples/em_validate_8_6.py tests/maps/test_em_validation.py docs CLAUDE.md
git commit -m "test,docs: em_validate end to end on the 8/6, example, M5e1 decisions and M5e2 handoff"
```

The controller then runs `examples\em_validate_8_6.py` detached (default `full` grid) and records its result in `docs/m5e1-results.md` and the M5e2 handoff.
