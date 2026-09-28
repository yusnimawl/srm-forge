# M1 — Geometry & Mesh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a validated radial SRM design into a fixed stator mesh + fixed rotor mesh joined by a moving band that can be re-triangulated at any rotor angle, with named regions, mesh controls, a quality report and a plot.

**Architecture:** Pure-Python `srmcore` package (src layout). `model/` holds Pydantic schemas, errors and the closed-form design validator. `topology/` computes the exact 2D outline (lines + minor arcs) with numpy only. `geometry/` turns the outline into Gmsh OCC surfaces with named regions. `mesh/` resolves mesh settings, drives Gmsh sizing through a callback, extracts stator/rotor parts, builds the moving band with a zipper triangulation, and reports quality.

**Tech Stack:** Python 3.12, numpy, pydantic 2, gmsh (pip wheel, Python API), matplotlib (Agg), pytest, hypothesis.

**Spec:** `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` (M1 row of §9; details in §3, §4, §8.1, §8.2).

**Scope of this plan:** milestone M1 only. M2–M5 each get their own plan after the previous milestone lands (M3's go/no-go and M1 findings change their details).

## Global Constraints

- Python `>=3.12,<3.13`; package `srmcore` in `src/srmcore`; tests in `tests/`.
- SI units internally everywhere (metres, radians, amperes); conversion only at UI/import edges.
- Allowed internal imports (spec §3.2), enforced by `tests/test_import_rules.py`:
  `model`: none · `materials`: model · `fields`: model · `topology`: model · `geometry`: model, topology · `mesh`: model, geometry · `physics`: model, materials, mesh · `solvers`: model, materials, physics, fields · `post`: model, materials, physics, fields · `maps`: all of the above · `project`: model, maps.
- Only `solvers/` imports `ngsolve`/`netgen`; only `geometry/` and `mesh/` import `gmsh`.
- Layers exchange plain data (numpy arrays, Pydantic models, frozen dataclasses) — never Gmsh/NGSolve objects.
- Full-machine model is the default (no sector solving in M1).
- Validator errors raise `InputError` naming the offending parameter and rule.
- Element order in M1: linear triangles (P1).
- CI: Windows + Linux. Fast suite on every commit (< 10 min); tests marked `slow` run nightly/on demand.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (preceded by a blank line).

## Review Focus

1. **Design entered in millimetres instead of metres** (e.g. stator OD = 160) → `InputError` naming the parameter with rule `units`, never a runaway mesh. Pinned in Task 3.
2. **Rotor angle negative, ≥ 2π, or huge** → `mesh_at_angle` wraps and produces exactly the same mesh as the wrapped angle. Pinned in Task 10.
3. **Sharp corners (zero fillet, zero taper)** → outline, geometry and mesh still build; `pole_root` refinement falls back to corner points. Pinned in Tasks 5 and 11.
4. **Liner/clearance/fillet so large the coil or slot vanishes** → `InputError` naming the parameter, not a Gmsh crash. Pinned in Tasks 5 and 6.
5. **Building two meshes in one process** (optimizer workers reuse a Gmsh session) → second build is identical to the first; no leaked model state. Pinned in Task 11.

## File Structure

```
pyproject.toml                         package metadata, deps, pytest config
.gitignore
.github/workflows/ci.yml               Windows + Linux fast suite
README.md                              dev setup
src/srmcore/__init__.py                version only
src/srmcore/{materials,fields,physics,solvers,post,maps,project}/__init__.py   empty placeholders
src/srmcore/model/__init__.py
src/srmcore/model/errors.py            ValidationIssue, InputError, MeshRejected
src/srmcore/model/design.py            RadialSRMParams, RegionMaterials, MeshSettings, EdgeRefinement, Design
src/srmcore/model/validator.py         validate_params(), validate_mesh_settings(), require_valid()
src/srmcore/topology/__init__.py
src/srmcore/topology/primitives.py     Line, Arc, rotate, mirror_y, line_circle_intersection, fillet_line_circle
src/srmcore/topology/radial.py         RadialOutline, CoilSide, build_outline(), periodicity()
src/srmcore/geometry/__init__.py
src/srmcore/geometry/session.py        gmsh_model() context manager (one Gmsh init per process)
src/srmcore/geometry/build.py          GeometryModel, build_geometry()
src/srmcore/mesh/__init__.py
src/srmcore/mesh/settings.py           ResolvedMeshSettings, resolve_mesh_settings()
src/srmcore/mesh/sizing.py             size_at()
src/srmcore/mesh/static.py             MeshPart, StaticMesh, build_static_mesh()
src/srmcore/mesh/band.py               zipper_band(), snap_angle()
src/srmcore/mesh/machine.py            MachineMesh, mesh_at_angle()
src/srmcore/mesh/quality.py            MeshQualityReport, triangle_quality(), quality_report(), check_quality()
src/srmcore/mesh/plot.py               plot_mesh()
tests/conftest.py                      reference designs 8/6, 12/8, 24/16
tests/test_import_rules.py
tests/model/test_design.py
tests/model/test_validator.py
tests/topology/test_primitives.py
tests/topology/test_radial.py
tests/topology/test_coils.py
tests/mesh/test_settings_sizing.py
tests/geometry/test_build.py
tests/mesh/test_static.py
tests/mesh/test_band.py
tests/mesh/test_machine.py
tests/mesh/test_quality_plot.py
tests/mesh/test_property.py
docs/reference-machines.md             M1 data-availability audit
```

---

### Task 1: Project scaffolding and import-rule enforcement

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `.github/workflows/ci.yml`
- Create: `src/srmcore/__init__.py` and empty `__init__.py` in `model, materials, fields, topology, geometry, mesh, physics, solvers, post, maps, project`
- Test: `tests/test_import_rules.py`

**Interfaces:**
- Consumes: nothing.
- Produces: installable package `srmcore`; `tests/test_import_rules.py::find_violations(src_root: Path) -> list[str]` (used only by tests).

- [ ] **Step 1: Create packaging and tooling files**

`pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "srmcore"
version = "0.1.0"
description = "Core engine of the SRM design tool: geometry, mesh, magnetostatics, maps"
requires-python = ">=3.12,<3.13"
dependencies = [
    "numpy>=1.26",
    "pydantic>=2.6",
    "gmsh>=4.12",
    "matplotlib>=3.8",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "hypothesis>=6.100"]

[tool.hatch.build.targets.wheel]
packages = ["src/srmcore"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
markers = ["slow: long-running validation tests (nightly or on demand)"]
```

`.gitignore`:
```
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.hypothesis/
build/
dist/
*.msh
out/
```

`README.md`:
````markdown
# srm-designer

Core engine (`srmcore`) of the SRM design tool. Spec: `docs/superpowers/specs/`.

## Dev setup

Windows (PowerShell):
```
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -m "not slow"
```

Linux:
```
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -m "not slow"
```
Linux needs `libglu1-mesa` for the gmsh wheel.
````

`.github/workflows/ci.yml`:
```yaml
name: ci
on: [push, pull_request]
jobs:
  fast:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libglu1-mesa libxcursor1 libxft2 libxinerama1
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -m "not slow"
```

`src/srmcore/__init__.py`:
```python
"""srmcore: core engine of the SRM design tool."""

__version__ = "0.1.0"
```

Create empty files `src/srmcore/<pkg>/__init__.py` for each of: `model, materials, fields, topology, geometry, mesh, physics, solvers, post, maps, project`.

- [ ] **Step 2: Create the venv and install**

Run (Windows): `py -3.12 -m venv .venv; .venv\Scripts\Activate.ps1; python -m pip install -e ".[dev]"`
Expected: ends with `Successfully installed ... srmcore-0.1.0 ...`. Then `python -c "import gmsh, srmcore; print(gmsh.__version__)"` prints a version ≥ 4.12.

- [ ] **Step 3: Write the import-rule test (with a self-test on a fake tree)**

`tests/test_import_rules.py`:
```python
"""Enforces the allowed-imports table of spec §3.2."""
import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "srmcore"

ALLOWED: dict[str, set[str]] = {
    "model": set(),
    "materials": {"model"},
    "fields": {"model"},
    "topology": {"model"},
    "geometry": {"model", "topology"},
    "mesh": {"model", "geometry"},
    "physics": {"model", "materials", "mesh"},
    "solvers": {"model", "materials", "physics", "fields"},
    "post": {"model", "materials", "physics", "fields"},
    "maps": {"model", "materials", "fields", "topology", "geometry",
             "mesh", "physics", "solvers", "post"},
    "project": {"model", "maps"},
}
THIRD_PARTY_OWNERS: dict[str, set[str]] = {
    "ngsolve": {"solvers"},
    "netgen": {"solvers"},
    "gmsh": {"geometry", "mesh"},
}


def _imported_modules(py_file: Path, src_root: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    package_parts = list(py_file.relative_to(src_root.parent).parts[:-1])
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.append(node.module or "")
            else:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                suffix = node.module.split(".") if node.module else []
                found.append(".".join(base + suffix))
    return found


def find_violations(src_root: Path) -> list[str]:
    violations: list[str] = []
    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(src_root).parts
        if len(rel) < 2:
            continue  # top-level srmcore/__init__.py is unconstrained
        owner = rel[0]
        for module in _imported_modules(py_file, src_root):
            parts = module.split(".")
            if parts[0] == src_root.name and len(parts) > 1:
                target = parts[1]
                if target != owner and target not in ALLOWED.get(owner, set()):
                    violations.append(f"{py_file.name} ({owner}) imports {module}")
            elif parts[0] in THIRD_PARTY_OWNERS and owner not in THIRD_PARTY_OWNERS[parts[0]]:
                violations.append(f"{py_file.name} ({owner}) imports {module}")
    return violations


def test_source_tree_obeys_import_rules():
    assert find_violations(SRC_ROOT) == []


def test_checker_detects_forbidden_internal_and_third_party(tmp_path):
    root = tmp_path / "srmcore"
    (root / "model").mkdir(parents=True)
    (root / "model" / "bad.py").write_text("from ..mesh import thing\n", encoding="utf-8")
    (root / "physics").mkdir()
    (root / "physics" / "bad.py").write_text("import gmsh\n", encoding="utf-8")
    (root / "mesh").mkdir()
    (root / "mesh" / "ok.py").write_text("from srmcore.geometry import x\nimport gmsh\n", encoding="utf-8")
    violations = find_violations(root)
    assert len(violations) == 2
    assert any("model" in v and "srmcore.mesh" in v for v in violations)
    assert any("physics" in v and "gmsh" in v for v in violations)
```

- [ ] **Step 4: Run it**

Run: `python -m pytest tests/test_import_rules.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore README.md .github src tests
git commit -m "chore: scaffold srmcore package and import-rule test" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Errors and design schema

**Files:**
- Create: `src/srmcore/model/errors.py`, `src/srmcore/model/design.py`
- Create: `tests/conftest.py`
- Test: `tests/model/test_design.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ValidationIssue(parameter: str, rule: str, message: str, severity: Literal["error","warning"]="error")` (frozen dataclass)
  - `InputError(issues: list[ValidationIssue])` — subclass of `ValueError`; attribute `.issues`
  - `MeshRejected(reasons: list[str], report: object)` — subclass of `RuntimeError`; attributes `.reasons`, `.report`
  - `RadialSRMParams` (frozen Pydantic model; fields below) with properties `stator_outer_radius`, `rotor_outer_radius`, `bore_radius`, `shaft_radius`, `stator_yoke_inner_radius`, `rotor_yoke_outer_radius`, `band_inner_radius`, `band_outer_radius`
  - `RegionMaterials`, `EdgeRefinement(size: float, growth: float = 1.3)`, `MeshSettings`, `Design(machine, mesh)` with `to_json() -> str`, `Design.from_json(text) -> Design`
  - pytest fixtures `srm_8_6`, `srm_12_8`, `srm_24_16` (each a `RadialSRMParams`) and `reference_design` (parametrised over the three)

- [ ] **Step 1: Write the fixtures**

`tests/conftest.py`:
```python
import math

import pytest

from srmcore.model.design import RadialSRMParams


def make_8_6(**overrides) -> RadialSRMParams:
    values = dict(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=0.160, rotor_outer_diameter=0.080, air_gap=0.0004,
        stack_length=0.100, shaft_diameter=0.020,
        stator_pole_arc=math.radians(20.0), rotor_pole_arc=math.radians(22.0),
        stator_yoke_thickness=0.012, rotor_yoke_thickness=0.012,
        stator_fillet_radius=0.001, rotor_fillet_radius=0.001,
        turns_per_pole=60, fill_factor=0.5,
        slot_liner_thickness=0.0005, coil_inner_clearance=0.001,
    )
    values.update(overrides)
    return RadialSRMParams(**values)


def make_12_8(**overrides) -> RadialSRMParams:
    values = dict(
        n_stator_poles=12, n_rotor_poles=8, n_phases=3,
        stator_outer_diameter=0.180, rotor_outer_diameter=0.100, air_gap=0.0003,
        stack_length=0.080, shaft_diameter=0.030,
        stator_pole_arc=math.radians(15.0), rotor_pole_arc=math.radians(16.0),
        stator_yoke_thickness=0.011, rotor_yoke_thickness=0.012,
        stator_fillet_radius=0.0008, rotor_fillet_radius=0.0008,
        turns_per_pole=30, fill_factor=0.5,
        slot_liner_thickness=0.0004, coil_inner_clearance=0.001,
    )
    values.update(overrides)
    return RadialSRMParams(**values)


def make_24_16(**overrides) -> RadialSRMParams:
    values = dict(
        n_stator_poles=24, n_rotor_poles=16, n_phases=3,
        stator_outer_diameter=0.200, rotor_outer_diameter=0.130, air_gap=0.0003,
        stack_length=0.060, shaft_diameter=0.050,
        stator_pole_arc=math.radians(7.5), rotor_pole_arc=math.radians(8.0),
        stator_yoke_thickness=0.009, rotor_yoke_thickness=0.010,
        stator_fillet_radius=0.0005, rotor_fillet_radius=0.0005,
        turns_per_pole=12, fill_factor=0.45,
        slot_liner_thickness=0.0003, coil_inner_clearance=0.0008,
    )
    values.update(overrides)
    return RadialSRMParams(**values)


@pytest.fixture
def srm_8_6() -> RadialSRMParams:
    return make_8_6()


@pytest.fixture
def srm_12_8() -> RadialSRMParams:
    return make_12_8()


@pytest.fixture
def srm_24_16() -> RadialSRMParams:
    return make_24_16()


@pytest.fixture(params=["8/6", "12/8", "24/16"])
def reference_design(request) -> RadialSRMParams:
    return {"8/6": make_8_6, "12/8": make_12_8, "24/16": make_24_16}[request.param]()
```

Note: these are plausible test machines, not the literature reference machines (those are chosen in Task 13).

- [ ] **Step 2: Write the failing tests**

`tests/model/test_design.py`:
```python
import pydantic
import pytest

from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.errors import InputError, MeshRejected, ValidationIssue


def test_derived_radii(srm_8_6):
    p = srm_8_6
    assert p.stator_outer_radius == pytest.approx(0.080)
    assert p.rotor_outer_radius == pytest.approx(0.040)
    assert p.bore_radius == pytest.approx(0.0404)
    assert p.shaft_radius == pytest.approx(0.010)
    assert p.stator_yoke_inner_radius == pytest.approx(0.068)
    assert p.rotor_yoke_outer_radius == pytest.approx(0.022)
    assert p.band_inner_radius == pytest.approx(0.040 + 0.0004 / 3)
    assert p.band_outer_radius == pytest.approx(0.040 + 2 * 0.0004 / 3)


def test_design_json_round_trip(srm_8_6):
    design = Design(machine=srm_8_6, mesh=MeshSettings(preset="screening", airgap_radial_layers=5))
    restored = Design.from_json(design.to_json())
    assert restored == design
    assert '"schema_version": 1' in design.to_json()


def test_unknown_field_rejected(srm_8_6):
    data = srm_8_6.model_dump()
    data["stator_od_mm"] = 160
    with pytest.raises(pydantic.ValidationError):
        RadialSRMParams(**data)


def test_wrong_schema_version_rejected(srm_8_6):
    data = srm_8_6.model_dump()
    data["schema_version"] = 2
    with pytest.raises(pydantic.ValidationError):
        RadialSRMParams(**data)


def test_input_error_lists_only_errors_in_message():
    issues = [
        ValidationIssue("air_gap", "positive", "must be > 0"),
        ValidationIssue("stator_pole_arc", "arc_order", "βs > βr", severity="warning"),
    ]
    err = InputError(issues)
    assert isinstance(err, ValueError)
    assert err.issues == issues
    assert "air_gap: [positive]" in str(err)
    assert "stator_pole_arc" not in str(err)


def test_mesh_rejected_carries_report():
    err = MeshRejected(["min angle 3.0° < 10.0°"], report={"n": 1})
    assert err.reasons == ["min angle 3.0° < 10.0°"]
    assert err.report == {"n": 1}
    assert "min angle" in str(err)
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/model/test_design.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'srmcore.model.design'`.

- [ ] **Step 4: Implement**

`src/srmcore/model/errors.py`:
```python
"""Error types shared by all layers."""
from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    parameter: str
    rule: str
    message: str
    severity: Severity = "error"


class InputError(ValueError):
    """A design violates a rule. Raised before any meshing."""

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = list(issues)
        lines = [f"{i.parameter}: [{i.rule}] {i.message}" for i in self.issues if i.severity == "error"]
        super().__init__("Invalid design:\n" + "\n".join(lines))


class MeshRejected(RuntimeError):
    """Mesh quality is below the configured thresholds."""

    def __init__(self, reasons: list[str], report: object):
        self.reasons = list(reasons)
        self.report = report
        super().__init__("Mesh rejected: " + "; ".join(self.reasons))
```

`src/srmcore/model/design.py`:
```python
"""Design schemas. All lengths in metres, all angles in radians."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RegionMaterials(_Frozen):
    stator: str = "M19"
    rotor: str = "M19"
    shaft: str = "steel_1010"
    coil: str = "copper"


class RadialSRMParams(_Frozen):
    schema_version: Literal[1] = SCHEMA_VERSION
    n_stator_poles: int
    n_rotor_poles: int
    n_phases: int
    stator_outer_diameter: float
    rotor_outer_diameter: float
    air_gap: float
    stack_length: float
    shaft_diameter: float
    stator_pole_arc: float
    rotor_pole_arc: float
    stator_pole_taper: float = 0.0
    rotor_pole_taper: float = 0.0
    stator_yoke_thickness: float
    rotor_yoke_thickness: float
    stator_fillet_radius: float = 0.0
    rotor_fillet_radius: float = 0.0
    turns_per_pole: int
    fill_factor: float
    slot_liner_thickness: float
    coil_inner_clearance: float
    lamination_thickness: float | None = None
    max_speed_rpm: float | None = None
    materials: RegionMaterials = RegionMaterials()

    @property
    def stator_outer_radius(self) -> float:
        return self.stator_outer_diameter / 2

    @property
    def rotor_outer_radius(self) -> float:
        return self.rotor_outer_diameter / 2

    @property
    def bore_radius(self) -> float:
        return self.rotor_outer_radius + self.air_gap

    @property
    def shaft_radius(self) -> float:
        return self.shaft_diameter / 2

    @property
    def stator_yoke_inner_radius(self) -> float:
        return self.stator_outer_radius - self.stator_yoke_thickness

    @property
    def rotor_yoke_outer_radius(self) -> float:
        return self.shaft_radius + self.rotor_yoke_thickness

    @property
    def band_inner_radius(self) -> float:
        return self.rotor_outer_radius + self.air_gap / 3

    @property
    def band_outer_radius(self) -> float:
        return self.rotor_outer_radius + 2 * self.air_gap / 3


class EdgeRefinement(_Frozen):
    size: float
    growth: float = 1.3


class MeshSettings(_Frozen):
    preset: Literal["screening", "full", "reference"] = "full"
    airgap_radial_layers: int = 4
    airgap_circumferential_divisions: int | None = None
    region_sizes: dict[str, float] = Field(default_factory=dict)
    refinement: dict[Literal["pole_tip", "pole_root"], EdgeRefinement] = Field(default_factory=dict)
    skin_depth_layers: int | None = None
    min_angle_deg: float = 10.0
    band_min_angle_deg: float = 5.0
    max_aspect_ratio: float = 12.0


class Design(_Frozen):
    schema_version: Literal[1] = SCHEMA_VERSION
    machine: RadialSRMParams
    mesh: MeshSettings = MeshSettings()

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Design":
        return cls.model_validate_json(text)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/model/test_design.py tests/test_import_rules.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/srmcore/model tests/conftest.py tests/model
git commit -m "feat(model): design schema, errors and reference test designs" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Closed-form design and mesh-settings validator

**Files:**
- Create: `src/srmcore/model/validator.py`
- Test: `tests/model/test_validator.py`

**Interfaces:**
- Consumes: `RadialSRMParams`, `MeshSettings`, `Design`, `ValidationIssue`, `InputError` (Task 2).
- Produces:
  - `validate_params(p: RadialSRMParams) -> list[ValidationIssue]`
  - `validate_mesh_settings(s: MeshSettings, p: RadialSRMParams) -> list[ValidationIssue]`
  - `require_valid(design: Design) -> list[ValidationIssue]` — raises `InputError` if any issue has severity `"error"`, otherwise returns the warnings.
  - `REGION_SIZE_KEYS: frozenset[str] = {"stator_iron","rotor_iron","shaft","coil","slot_air","airgap"}`

Geometric fit checks that need the exact outline (fillet fit, coil area, pole width at the yoke) live in `topology.radial.build_outline` (Tasks 5–6) because `model` may not import `topology`.

- [ ] **Step 1: Write the failing tests**

`tests/model/test_validator.py`:
```python
import math

import pytest

from conftest import make_8_6, make_12_8
from srmcore.model.design import Design, EdgeRefinement, MeshSettings
from srmcore.model.errors import InputError
from srmcore.model.validator import require_valid, validate_mesh_settings, validate_params


def _errors(issues):
    return {(i.parameter, i.rule) for i in issues if i.severity == "error"}


def _warnings(issues):
    return {(i.parameter, i.rule) for i in issues if i.severity == "warning"}


def test_reference_designs_are_valid(reference_design):
    assert _errors(validate_params(reference_design)) == set()


def test_millimetre_input_is_caught_as_units_error():
    p = make_8_6(stator_outer_diameter=160.0, rotor_outer_diameter=80.0, air_gap=0.4)
    errors = _errors(validate_params(p))
    assert ("stator_outer_diameter", "units") in errors
    assert ("air_gap", "units") in errors


def test_non_positive_lengths():
    errors = _errors(validate_params(make_8_6(air_gap=0.0, stack_length=-0.1)))
    assert ("air_gap", "positive") in errors
    assert ("stack_length", "positive") in errors


def test_negative_fillet_rejected():
    assert ("rotor_fillet_radius", "non_negative") in _errors(validate_params(make_8_6(rotor_fillet_radius=-1e-4)))


def test_phase_count_must_match_pole_numbers():
    assert ("n_phases", "phase_count") in _errors(validate_params(make_8_6(n_phases=3)))


def test_equal_pole_numbers_rejected():
    assert ("n_rotor_poles", "phase_count") in _errors(validate_params(make_8_6(n_rotor_poles=8)))


def test_self_starting_rule():
    p = make_8_6(stator_pole_arc=math.radians(12.0))  # min arc 12° < 360/(4*6) = 15°
    assert ("stator_pole_arc", "self_starting") in _errors(validate_params(p))


def test_self_starting_equality_is_allowed():
    assert _errors(validate_params(make_12_8())) == set()  # βs = 15° = 360/(3*8)


def test_pole_arc_sum_rule():
    p = make_8_6(stator_pole_arc=math.radians(28.0), rotor_pole_arc=math.radians(33.0))  # 61° ≥ 60°
    assert ("rotor_pole_arc", "pole_arc_sum") in _errors(validate_params(p))


def test_stator_arc_larger_than_rotor_is_only_a_warning():
    p = make_8_6(stator_pole_arc=math.radians(23.0), rotor_pole_arc=math.radians(21.0))
    issues = validate_params(p)
    assert _errors(issues) == set()
    assert ("stator_pole_arc", "arc_order") in _warnings(issues)


def test_radial_stack_rules():
    errors = _errors(validate_params(make_8_6(rotor_yoke_thickness=0.031)))  # 0.010 + 0.031 > 0.040
    assert ("rotor_yoke_thickness", "radial_stack") in errors
    errors = _errors(validate_params(make_8_6(stator_yoke_thickness=0.040)))  # 0.080 - 0.040 < 0.0404
    assert ("stator_yoke_thickness", "radial_stack") in errors


def test_fill_factor_range():
    assert ("fill_factor", "range") in _errors(validate_params(make_8_6(fill_factor=0.95)))


def test_thick_lamination_at_high_frequency_warns():
    p = make_8_6(lamination_thickness=0.00035, max_speed_rpm=15000)  # 6*15000/60 = 1.5 kHz
    assert ("lamination_thickness", "lamination_frequency") in _warnings(validate_params(p))


def test_mesh_settings_rules(srm_8_6):
    s = MeshSettings(
        airgap_radial_layers=3,
        airgap_circumferential_divisions=100,  # lcm(8, 6) = 24 does not divide 100
        region_sizes={"stator_iron": 0.002, "rotor": 0.002},
        refinement={"pole_tip": EdgeRefinement(size=0.0, growth=0.9)},
        skin_depth_layers=3,
    )
    errors = _errors(validate_mesh_settings(s, srm_8_6))
    assert ("airgap_radial_layers", "min_layers") in errors
    assert ("airgap_circumferential_divisions", "band_divisions") in errors
    assert ("region_sizes.rotor", "unknown_region") in errors
    assert ("refinement.pole_tip.size", "positive") in errors
    assert ("refinement.pole_tip.growth", "range") in errors
    assert ("skin_depth_layers", "not_implemented") in errors


def test_require_valid_raises_with_parameter_names():
    design = Design(machine=make_8_6(air_gap=-1.0))
    with pytest.raises(InputError) as info:
        require_valid(design)
    assert "air_gap" in str(info.value)


def test_require_valid_returns_warnings(srm_8_6):
    design = Design(machine=make_8_6(stator_pole_arc=math.radians(23.0), rotor_pole_arc=math.radians(21.0)))
    warnings = require_valid(design)
    assert [w.rule for w in warnings] == ["arc_order"]
```

`tests` must be importable as a path for `from conftest import ...`: add to `pyproject.toml` under `[tool.pytest.ini_options]` the line `pythonpath = ["tests"]`.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/model/test_validator.py -v`
Expected: `ModuleNotFoundError: No module named 'srmcore.model.validator'`.

- [ ] **Step 3: Implement**

`src/srmcore/model/validator.py`:
```python
"""Closed-form validation of designs and mesh settings (runs in milliseconds, before meshing)."""
import math

from .design import Design, MeshSettings, RadialSRMParams
from .errors import InputError, ValidationIssue

REGION_SIZE_KEYS = frozenset({"stator_iron", "rotor_iron", "shaft", "coil", "slot_air", "airgap"})

# Plausible ranges in metres; values outside almost always mean wrong units (mm instead of m).
_UNIT_RANGES: dict[str, tuple[float, float]] = {
    "stator_outer_diameter": (0.01, 2.0),
    "rotor_outer_diameter": (0.005, 2.0),
    "air_gap": (1e-5, 0.01),
    "stack_length": (1e-3, 2.0),
}
_TOL = 1e-9


def _err(parameter: str, rule: str, message: str) -> ValidationIssue:
    return ValidationIssue(parameter, rule, message, "error")


def _warn(parameter: str, rule: str, message: str) -> ValidationIssue:
    return ValidationIssue(parameter, rule, message, "warning")


def validate_params(p: RadialSRMParams) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for name in ("n_stator_poles", "n_rotor_poles", "n_phases"):
        if getattr(p, name) < 2:
            issues.append(_err(name, "positive", "must be at least 2"))
    if p.turns_per_pole < 1:
        issues.append(_err("turns_per_pole", "positive", "must be at least 1"))
    if p.n_stator_poles == p.n_rotor_poles:
        issues.append(_err("n_rotor_poles", "phase_count", "rotor and stator pole numbers must differ"))
    elif min(p.n_stator_poles, p.n_rotor_poles, p.n_phases) >= 2:
        expected = p.n_stator_poles // math.gcd(p.n_stator_poles, p.n_rotor_poles)
        if p.n_phases != expected:
            issues.append(_err("n_phases", "phase_count",
                               f"{p.n_stator_poles}/{p.n_rotor_poles} implies {expected} phases, got {p.n_phases}"))

    for name in ("stator_outer_diameter", "rotor_outer_diameter", "air_gap", "stack_length",
                 "shaft_diameter", "stator_yoke_thickness", "rotor_yoke_thickness",
                 "stator_pole_arc", "rotor_pole_arc", "fill_factor"):
        if getattr(p, name) <= 0:
            issues.append(_err(name, "positive", "must be > 0"))
    for name in ("stator_fillet_radius", "rotor_fillet_radius", "slot_liner_thickness", "coil_inner_clearance"):
        if getattr(p, name) < 0:
            issues.append(_err(name, "non_negative", "must be >= 0"))

    for name, (lo, hi) in _UNIT_RANGES.items():
        value = getattr(p, name)
        if value > 0 and not (lo <= value <= hi):
            issues.append(_err(name, "units", f"{value} m is outside [{lo}, {hi}] m; lengths are in metres"))

    if p.fill_factor > 0.9:
        issues.append(_err("fill_factor", "range", "must be in (0, 0.9]"))
    for name in ("stator_pole_taper", "rotor_pole_taper"):
        if abs(getattr(p, name)) >= math.radians(15.0):
            issues.append(_err(name, "range", "taper magnitude must be below 15°"))

    if p.rotor_outer_diameter >= p.stator_outer_diameter:
        issues.append(_err("rotor_outer_diameter", "radial_stack", "rotor must be smaller than stator"))
    if p.rotor_yoke_outer_radius >= p.rotor_outer_radius:
        issues.append(_err("rotor_yoke_thickness", "radial_stack", "no room left for rotor poles"))
    if p.stator_yoke_inner_radius <= p.bore_radius:
        issues.append(_err("stator_yoke_thickness", "radial_stack", "no room left for stator poles"))

    if p.n_phases >= 2 and p.n_rotor_poles >= 2:
        bs, br = p.stator_pole_arc, p.rotor_pole_arc
        limit = 2 * math.pi / (p.n_phases * p.n_rotor_poles)
        if min(bs, br) < limit - _TOL:
            which = "stator_pole_arc" if bs <= br else "rotor_pole_arc"
            issues.append(_err(which, "self_starting",
                               f"min(βs, βr) = {math.degrees(min(bs, br)):.3f}° < 2π/(m·Nr) = {math.degrees(limit):.3f}°"))
        pitch = 2 * math.pi / p.n_rotor_poles
        if bs + br >= pitch - _TOL:
            issues.append(_err("rotor_pole_arc", "pole_arc_sum",
                               f"βs + βr = {math.degrees(bs + br):.3f}° must be < 2π/Nr = {math.degrees(pitch):.3f}°"))
        if bs > br:
            issues.append(_warn("stator_pole_arc", "arc_order", "βs > βr (valid, but unusual)"))

    if p.lamination_thickness is not None:
        if not (1e-5 <= p.lamination_thickness <= 2e-3):
            issues.append(_err("lamination_thickness", "units", "must be within [1e-5, 2e-3] m"))
        elif p.max_speed_rpm is not None and p.max_speed_rpm > 0:
            f_max = p.n_rotor_poles * p.max_speed_rpm / 60.0
            if f_max > 1000.0 and p.lamination_thickness > 0.2e-3:
                issues.append(_warn("lamination_thickness", "lamination_frequency",
                                    f"{p.lamination_thickness * 1e3:.2f} mm at {f_max:.0f} Hz: use ≤ 0.2 mm"))
    if p.max_speed_rpm is not None and p.max_speed_rpm <= 0:
        issues.append(_err("max_speed_rpm", "positive", "must be > 0"))
    return issues


def validate_mesh_settings(s: MeshSettings, p: RadialSRMParams) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if s.airgap_radial_layers < 4:
        issues.append(_err("airgap_radial_layers", "min_layers", "at least 4 element layers across the air gap"))
    if s.airgap_circumferential_divisions is not None:
        base = math.lcm(p.n_stator_poles, p.n_rotor_poles)
        n = s.airgap_circumferential_divisions
        if n < base or n % base != 0:
            issues.append(_err("airgap_circumferential_divisions", "band_divisions",
                               f"must be a positive multiple of lcm(Ns, Nr) = {base}"))
    for key, size in s.region_sizes.items():
        if key not in REGION_SIZE_KEYS:
            issues.append(_err(f"region_sizes.{key}", "unknown_region", f"allowed: {sorted(REGION_SIZE_KEYS)}"))
        elif size <= 0:
            issues.append(_err(f"region_sizes.{key}", "positive", "must be > 0"))
    for tag, ref in s.refinement.items():
        if ref.size <= 0:
            issues.append(_err(f"refinement.{tag}.size", "positive", "must be > 0"))
        if ref.growth < 1.0:
            issues.append(_err(f"refinement.{tag}.growth", "range", "must be >= 1.0"))
    if s.skin_depth_layers is not None:
        issues.append(_err("skin_depth_layers", "not_implemented", "skin-depth layers arrive with sub-project #2"))
    if not (0 < s.min_angle_deg < 60):
        issues.append(_err("min_angle_deg", "range", "must be in (0, 60)"))
    if not (0 < s.band_min_angle_deg < 60):
        issues.append(_err("band_min_angle_deg", "range", "must be in (0, 60)"))
    if s.max_aspect_ratio <= 1:
        issues.append(_err("max_aspect_ratio", "range", "must be > 1"))
    return issues


def require_valid(design: Design) -> list[ValidationIssue]:
    issues = validate_params(design.machine) + validate_mesh_settings(design.mesh, design.machine)
    if any(i.severity == "error" for i in issues):
        raise InputError(issues)
    return [i for i in issues if i.severity == "warning"]
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/model -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/srmcore/model/validator.py tests/model/test_validator.py
git commit -m "feat(model): closed-form design and mesh-settings validator" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Outline primitives (lines, minor arcs, intersections, fillets)

**Files:**
- Create: `src/srmcore/topology/primitives.py`
- Test: `tests/topology/test_primitives.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Point = tuple[float, float]`
  - `Line(start: Point, end: Point, tag: str = "")`, `Arc(start: Point, end: Point, center: Point, tag: str = "")` — frozen dataclasses; an `Arc` is always the **minor** arc (< π) from `start` to `end`.
  - `Segment = Line | Arc`
  - `rotate(p: Point, angle: float) -> Point`, `mirror_y(p: Point) -> Point`
  - `map_segment(seg: Segment, fn: Callable[[Point], Point]) -> Segment`, `reverse(seg: Segment) -> Segment`
  - `line_circle_intersection(p0: Point, d: Point, radius: float, t_ref: float | None = None) -> tuple[Point, float]` (circle centred at origin; `d` unit vector; smallest positive root, or the root closest to `t_ref`; raises `ValueError` if no intersection)
  - `Fillet(center: Point, on_line: Point, on_circle: Point, t_line: float)` and `fillet_line_circle(p0, d, n, circle_radius, fillet_radius, inside: bool) -> Fillet` (raises `ValueError` if the fillet does not fit)

- [ ] **Step 1: Write the failing tests**

`tests/topology/test_primitives.py`:
```python
import math

import pytest

from srmcore.topology.primitives import (
    Arc, Line, fillet_line_circle, line_circle_intersection, map_segment, mirror_y, reverse, rotate,
)


def test_rotate_quarter_turn():
    x, y = rotate((1.0, 0.0), math.pi / 2)
    assert x == pytest.approx(0.0, abs=1e-15)
    assert y == pytest.approx(1.0)


def test_mirror_and_map_and_reverse():
    arc = Arc((1.0, 0.1), (1.0, 0.2), (0.0, 0.0), "t")
    m = map_segment(arc, mirror_y)
    assert m == Arc((1.0, -0.1), (1.0, -0.2), (0.0, 0.0), "t")
    assert reverse(Line((0, 0), (1, 1), "x")) == Line((1, 1), (0, 0), "x")


def test_intersection_from_inside_and_outside():
    p, t = line_circle_intersection((0.5, 0.0), (1.0, 0.0), 1.0)
    assert p == pytest.approx((1.0, 0.0)) and t == pytest.approx(0.5)
    p, t = line_circle_intersection((2.0, 0.0), (-1.0, 0.0), 1.0)
    assert p == pytest.approx((1.0, 0.0)) and t == pytest.approx(1.0)


def test_intersection_miss_raises():
    with pytest.raises(ValueError):
        line_circle_intersection((0.0, 2.0), (1.0, 0.0), 1.0)


@pytest.mark.parametrize("inside,p0,d", [
    (True, (0.5, 0.1), (1.0, 0.0)),    # stator-like: fillet inside the yoke circle
    (False, (1.5, 0.1), (-1.0, 0.0)),  # rotor-like: fillet outside the rotor-yoke circle
])
def test_fillet_is_tangent_to_line_and_circle(inside, p0, d):
    r, R, n = 0.05, 1.0, (0.0, 1.0)
    f = fillet_line_circle(p0, d, n, R, r, inside=inside)
    cx, cy = f.center
    assert cy == pytest.approx(0.1 + r)                      # centre is r from the line
    assert math.hypot(cx, cy) == pytest.approx(R - r if inside else R + r)
    assert f.on_line[1] == pytest.approx(0.1)                 # tangent point lies on the line
    assert math.hypot(*f.on_circle) == pytest.approx(R)       # tangent point lies on the circle
    assert math.hypot(cx - f.on_circle[0], cy - f.on_circle[1]) == pytest.approx(r)
    assert f.t_line > 0


def test_fillet_too_large_raises():
    with pytest.raises(ValueError):
        fillet_line_circle((0.9, 0.1), (1.0, 0.0), (0.0, 1.0), 1.0, 0.5, inside=True)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/topology/test_primitives.py -v`
Expected: `ModuleNotFoundError: No module named 'srmcore.topology.primitives'`.

- [ ] **Step 3: Implement**

`src/srmcore/topology/primitives.py`:
```python
"""2D outline primitives. Points are (x, y) in metres; circles are centred at the origin unless stated."""
import math
from collections.abc import Callable
from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class Line:
    start: Point
    end: Point
    tag: str = ""


@dataclass(frozen=True)
class Arc:
    """Minor arc (< π) from start to end around center."""
    start: Point
    end: Point
    center: Point
    tag: str = ""


Segment = Line | Arc


def rotate(p: Point, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def mirror_y(p: Point) -> Point:
    return (p[0], -p[1])


def map_segment(seg: Segment, fn: Callable[[Point], Point]) -> Segment:
    if isinstance(seg, Line):
        return Line(fn(seg.start), fn(seg.end), seg.tag)
    return Arc(fn(seg.start), fn(seg.end), fn(seg.center), seg.tag)


def reverse(seg: Segment) -> Segment:
    if isinstance(seg, Line):
        return Line(seg.end, seg.start, seg.tag)
    return Arc(seg.end, seg.start, seg.center, seg.tag)


def line_circle_intersection(p0: Point, d: Point, radius: float,
                             t_ref: float | None = None) -> tuple[Point, float]:
    """Intersect p0 + t*d (|d| = 1) with |x| = radius.

    Returns the smallest positive root, or the root closest to t_ref when given.
    """
    px, py = p0
    dx, dy = d
    b = px * dx + py * dy
    c = px * px + py * py - radius * radius
    disc = b * b - c
    if disc < 0:
        raise ValueError("line does not reach the circle")
    sq = math.sqrt(disc)
    roots = (-b - sq, -b + sq)
    if t_ref is None:
        positive = [t for t in roots if t > 1e-15]
        if not positive:
            raise ValueError("circle is behind the line start")
        t = min(positive)
    else:
        t = min(roots, key=lambda r: abs(r - t_ref))
    return (px + t * dx, py + t * dy), t


@dataclass(frozen=True)
class Fillet:
    center: Point
    on_line: Point
    on_circle: Point
    t_line: float


def fillet_line_circle(p0: Point, d: Point, n: Point, circle_radius: float,
                       fillet_radius: float, inside: bool) -> Fillet:
    """Fillet of radius r tangent to the line p0 + t*d and to the circle |x| = R.

    n is the unit normal of the line pointing to the side the fillet lies on.
    inside=True: fillet inside the circle (|centre| = R - r); False: outside (|centre| = R + r).
    """
    r = fillet_radius
    _, t_corner = line_circle_intersection(p0, d, circle_radius)
    centre_radius = circle_radius - r if inside else circle_radius + r
    offset_start = (p0[0] + r * n[0], p0[1] + r * n[1])
    centre, t = line_circle_intersection(offset_start, d, centre_radius, t_ref=t_corner)
    if not (0.0 < t <= t_corner + 1e-12):
        raise ValueError("fillet does not fit on the line segment")
    on_line = (centre[0] - r * n[0], centre[1] - r * n[1])
    k = circle_radius / math.hypot(*centre)
    return Fillet(centre, on_line, (centre[0] * k, centre[1] * k), t)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/topology/test_primitives.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/topology/primitives.py tests/topology/test_primitives.py
git commit -m "feat(topology): outline primitives with line-circle intersection and fillets" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Radial SRM outline (stator bore boundary, rotor boundary, symmetry, refinement features)

**Files:**
- Modify: `src/srmcore/topology/primitives.py` (add `sample_segment`)
- Create: `src/srmcore/topology/radial.py`
- Test: `tests/topology/test_radial.py`

**Interfaces:**
- Consumes: `RadialSRMParams`, `InputError`, `ValidationIssue` (Task 2); primitives (Task 4).
- Produces:
  - `sample_segment(seg: Segment, max_step: float) -> list[Point]` (includes both endpoints)
  - `CoilSide(name: str, pole: int, phase: int, sign: int, boundary: tuple[Segment, ...])`
  - `RadialOutline(stator_outer_radius, stator_inner_boundary, bore_radius, rotor_outer_radius, rotor_outer_boundary, shaft_radius, band_inner_radius, band_outer_radius, coil_sides, refinement_features)` — frozen dataclass; `refinement_features: dict[str, tuple[Segment | Point, ...]]` with keys `"pole_tip"` and `"pole_root"`
  - `build_outline(p: RadialSRMParams) -> RadialOutline` (raises `InputError`, rule `pole_fit` / `coil_fit`)
  - `periodicity(p: RadialSRMParams) -> int` (= gcd(Ns, Nr))

Conventions: origin at the shaft centre; stator pole `k` centred at angle `2πk/Ns`; rotor at angle 0 has rotor pole 0 centred on +x (aligned with stator pole 0). Boundaries run counter-clockwise, starting with pole 0's face. Segment tags: `stator_pole_tip`, `stator_flank`, `stator_pole_root`, `stator_yoke`, and the same with `rotor_`.

- [ ] **Step 1: Write the failing tests**

`tests/topology/test_radial.py`:
```python
import math

import pytest

from conftest import make_8_6
from srmcore.model.errors import InputError
from srmcore.topology.primitives import Arc, Line, sample_segment
from srmcore.topology.radial import build_outline, periodicity


def _closed(segments, tol=1e-12):
    return all(math.dist(a.end, b.start) < tol for a, b in zip(segments, segments[1:] + segments[:1]))


def _area(segments):
    pts = [q for s in segments for q in sample_segment(s, 2e-4)[:-1]]
    return 0.5 * abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])))


def test_sample_segment_arc_stays_on_circle():
    arc = Arc((1.0, 0.0), (0.0, 1.0), (0.0, 0.0))
    pts = sample_segment(arc, 0.1)
    assert pts[0] == pytest.approx((1.0, 0.0)) and pts[-1] == pytest.approx((0.0, 1.0))
    assert all(math.hypot(*q) == pytest.approx(1.0) for q in pts)
    assert len(pts) >= 17  # quarter circle length 1.57 / 0.1


def test_boundaries_are_closed_and_counted(srm_8_6):
    o = build_outline(srm_8_6)
    assert _closed(list(o.stator_inner_boundary))
    assert _closed(list(o.rotor_outer_boundary))
    assert len(o.stator_inner_boundary) == 6 * 8   # face, flank, fillet, yoke, fillet, flank
    assert len(o.rotor_outer_boundary) == 6 * 6


def test_sharp_corners_have_four_segments_per_pole():
    o = build_outline(make_8_6(stator_fillet_radius=0.0, rotor_fillet_radius=0.0))
    assert len(o.stator_inner_boundary) == 4 * 8
    assert len(o.rotor_outer_boundary) == 4 * 6
    assert _closed(list(o.stator_inner_boundary)) and _closed(list(o.rotor_outer_boundary))
    roots = o.refinement_features["pole_root"]
    assert len(roots) == 2 * (8 + 6) and all(isinstance(r, tuple) for r in roots)


def test_faces_lie_on_their_circles(srm_8_6):
    o = build_outline(srm_8_6)
    for seg in o.stator_inner_boundary:
        if seg.tag == "stator_pole_tip":
            assert math.hypot(*seg.start) == pytest.approx(o.bore_radius)
    for seg in o.rotor_outer_boundary:
        if seg.tag == "rotor_pole_tip":
            assert math.hypot(*seg.end) == pytest.approx(o.rotor_outer_radius)


def test_rotor_pole_zero_is_centred_on_x_axis(srm_8_6):
    face = build_outline(srm_8_6).rotor_outer_boundary[0]
    assert face.tag == "rotor_pole_tip"
    assert face.start[1] == pytest.approx(-face.end[1])
    assert face.start[0] == pytest.approx(face.end[0])


def test_enclosed_areas_are_between_their_radii(reference_design):
    p = reference_design
    o = build_outline(p)
    assert math.pi * p.bore_radius**2 < _area(o.stator_inner_boundary) < math.pi * p.stator_yoke_inner_radius**2
    assert math.pi * p.rotor_yoke_outer_radius**2 < _area(o.rotor_outer_boundary) < math.pi * p.rotor_outer_radius**2


def test_refinement_features_with_fillets(srm_8_6):
    o = build_outline(srm_8_6)
    assert len(o.refinement_features["pole_tip"]) == 8 + 6
    roots = o.refinement_features["pole_root"]
    assert len(roots) == 2 * (8 + 6) and all(isinstance(r, Arc) for r in roots)


def test_band_radii_and_tags(srm_8_6):
    o = build_outline(srm_8_6)
    assert o.rotor_outer_radius < o.band_inner_radius < o.band_outer_radius < o.bore_radius
    tags = {s.tag for s in o.stator_inner_boundary}
    assert tags == {"stator_pole_tip", "stator_flank", "stator_pole_root", "stator_yoke"}
    assert any(isinstance(s, Line) for s in o.rotor_outer_boundary)


def test_periodicity(srm_8_6, srm_12_8, srm_24_16):
    assert (periodicity(srm_8_6), periodicity(srm_12_8), periodicity(srm_24_16)) == (2, 4, 8)


def test_oversized_fillet_is_an_input_error():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(stator_fillet_radius=0.02))
    assert any(i.parameter == "stator_fillet_radius" and i.rule == "pole_fit" for i in info.value.issues)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/topology/test_radial.py -v`
Expected: `ImportError` for `sample_segment` / `srmcore.topology.radial`.

- [ ] **Step 3: Add `sample_segment` to primitives**

Append to `src/srmcore/topology/primitives.py`:
```python
def sample_segment(seg: Segment, max_step: float) -> list[Point]:
    """Points along the segment, spaced at most max_step apart, both endpoints included."""
    if isinstance(seg, Line):
        length = math.dist(seg.start, seg.end)
        n = max(1, math.ceil(length / max_step))
        return [(seg.start[0] + (seg.end[0] - seg.start[0]) * i / n,
                 seg.start[1] + (seg.end[1] - seg.start[1]) * i / n) for i in range(n + 1)]
    cx, cy = seg.center
    r = math.dist(seg.start, seg.center)
    a0 = math.atan2(seg.start[1] - cy, seg.start[0] - cx)
    a1 = math.atan2(seg.end[1] - cy, seg.end[0] - cx)
    delta = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi   # minor arc, signed
    n = max(1, math.ceil(abs(delta) * r / max_step))
    return [(cx + r * math.cos(a0 + delta * i / n), cy + r * math.sin(a0 + delta * i / n)) for i in range(n + 1)]
```

- [ ] **Step 4: Implement the outline**

`src/srmcore/topology/radial.py`:
```python
"""Exact 2D outline of a radial SRM at rotor angle 0.

Origin at the shaft centre. Stator pole k is centred at 2πk/Ns; rotor pole 0 is centred on +x.
Boundaries run counter-clockwise starting with pole 0's face.
"""
import math
from dataclasses import dataclass

from ..model.design import RadialSRMParams
from ..model.errors import InputError, ValidationIssue
from .primitives import (
    Arc, Line, Point, Segment, fillet_line_circle, line_circle_intersection, mirror_y, rotate,
)

ORIGIN: Point = (0.0, 0.0)


@dataclass(frozen=True)
class CoilSide:
    name: str
    pole: int
    phase: int
    sign: int
    boundary: tuple[Segment, ...]


@dataclass(frozen=True)
class RadialOutline:
    stator_outer_radius: float
    stator_inner_boundary: tuple[Segment, ...]
    bore_radius: float
    rotor_outer_radius: float
    rotor_outer_boundary: tuple[Segment, ...]
    shaft_radius: float
    band_inner_radius: float
    band_outer_radius: float
    coil_sides: tuple[CoilSide, ...]
    refinement_features: dict[str, tuple[Segment | Point, ...]]


@dataclass(frozen=True)
class _PoleSide:
    """Upper (+y) half of one pole in its local frame, pole axis on +x."""
    face_end: Point
    flank_end: Point
    root_end: Point
    fillet_center: Point | None
    corner: Point


def periodicity(p: RadialSRMParams) -> int:
    return math.gcd(p.n_stator_poles, p.n_rotor_poles)


def _angle(q: Point) -> float:
    return math.atan2(q[1], q[0])


def _pole_side(face_radius: float, arc: float, taper: float, root_radius: float,
               fillet_radius: float, outward: bool, pitch: float) -> _PoleSide:
    half = arc / 2
    if half >= pitch / 2:
        raise ValueError("pole face is wider than the pole pitch")
    face_end = (face_radius * math.cos(half), face_radius * math.sin(half))
    d = (math.cos(taper), math.sin(taper)) if outward else (-math.cos(taper), math.sin(taper))
    n = (-d[1], d[0]) if d[0] > 0 else (d[1], -d[0])  # unit normal pointing away from the pole axis
    corner, _ = line_circle_intersection(face_end, d, root_radius)
    if fillet_radius > 0:
        f = fillet_line_circle(face_end, d, n, root_radius, fillet_radius, inside=outward)
        side = _PoleSide(face_end, f.on_line, f.on_circle, f.center, corner)
    else:
        side = _PoleSide(face_end, corner, corner, None, corner)
    if not (0.0 < _angle(side.root_end) < pitch / 2):
        raise ValueError("pole root leaves no room between neighbouring poles")
    return side


def _salient_boundary(n_poles: int, side: _PoleSide, prefix: str) -> tuple[tuple[Segment, ...], list[Point]]:
    pitch = 2 * math.pi / n_poles
    segs: list[Segment] = []
    for k in range(n_poles):
        a, a_next = k * pitch, ((k + 1) % n_poles) * pitch

        def here(q: Point) -> Point:
            return rotate(q, a)

        def nxt(q: Point) -> Point:
            return rotate(mirror_y(q), a_next)

        segs.append(Arc(here(mirror_y(side.face_end)), here(side.face_end), ORIGIN, f"{prefix}_pole_tip"))
        segs.append(Line(here(side.face_end), here(side.flank_end), f"{prefix}_flank"))
        if side.fillet_center is not None:
            segs.append(Arc(here(side.flank_end), here(side.root_end), here(side.fillet_center), f"{prefix}_pole_root"))
        segs.append(Arc(here(side.root_end), nxt(side.root_end), ORIGIN, f"{prefix}_yoke"))
        if side.fillet_center is not None:
            segs.append(Arc(nxt(side.root_end), nxt(side.flank_end), nxt(side.fillet_center), f"{prefix}_pole_root"))
        segs.append(Line(nxt(side.flank_end), nxt(side.face_end), f"{prefix}_flank"))
    corners = [rotate(c, k * pitch) for k in range(n_poles) for c in (side.corner, mirror_y(side.corner))]
    return tuple(segs), corners


def _fit_error(parameter: str, rule: str, exc: Exception) -> InputError:
    return InputError([ValidationIssue(parameter, rule, str(exc))])


def build_outline(p: RadialSRMParams) -> RadialOutline:
    try:
        stator_side = _pole_side(p.bore_radius, p.stator_pole_arc, p.stator_pole_taper,
                                 p.stator_yoke_inner_radius, p.stator_fillet_radius, True,
                                 2 * math.pi / p.n_stator_poles)
    except ValueError as exc:
        raise _fit_error("stator_fillet_radius" if p.stator_fillet_radius > 0 else "stator_pole_arc",
                         "pole_fit", exc) from exc
    try:
        rotor_side = _pole_side(p.rotor_outer_radius, p.rotor_pole_arc, p.rotor_pole_taper,
                                p.rotor_yoke_outer_radius, p.rotor_fillet_radius, False,
                                2 * math.pi / p.n_rotor_poles)
    except ValueError as exc:
        raise _fit_error("rotor_fillet_radius" if p.rotor_fillet_radius > 0 else "rotor_pole_arc",
                         "pole_fit", exc) from exc

    stator, stator_corners = _salient_boundary(p.n_stator_poles, stator_side, "stator")
    rotor, rotor_corners = _salient_boundary(p.n_rotor_poles, rotor_side, "rotor")

    tips = tuple(s for s in stator + rotor if s.tag.endswith("_pole_tip"))
    if p.stator_fillet_radius > 0 or p.rotor_fillet_radius > 0:
        roots: tuple[Segment | Point, ...] = tuple(s for s in stator + rotor if s.tag.endswith("_pole_root"))
        if p.stator_fillet_radius == 0:
            roots += tuple(stator_corners)
        if p.rotor_fillet_radius == 0:
            roots += tuple(rotor_corners)
    else:
        roots = tuple(stator_corners + rotor_corners)

    return RadialOutline(
        stator_outer_radius=p.stator_outer_radius,
        stator_inner_boundary=stator,
        bore_radius=p.bore_radius,
        rotor_outer_radius=p.rotor_outer_radius,
        rotor_outer_boundary=rotor,
        shaft_radius=p.shaft_radius,
        band_inner_radius=p.band_inner_radius,
        band_outer_radius=p.band_outer_radius,
        coil_sides=(),
        refinement_features={"pole_tip": tips, "pole_root": roots},
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/topology -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/srmcore/topology tests/topology/test_radial.py
git commit -m "feat(topology): exact radial SRM outline with fillets, tapers and refinement features" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Coil sides

**Files:**
- Modify: `src/srmcore/topology/radial.py` (add `_coil_sides`, fill `coil_sides` in `build_outline`)
- Test: `tests/topology/test_coils.py`

**Interfaces:**
- Consumes: Task 5.
- Produces: `RadialOutline.coil_sides` — `2·Ns` `CoilSide`s. Pole `k`: phase `k % m`, name `coil_{letter}{k//m + 1}{sign}`, polarity `+1` if `(k // m)` is even else `-1`; the upper (counter-clockwise) side carries `sign = polarity`, the lower side `-polarity`. Each boundary is 4 segments tagged `coil`: flank-parallel line, outer arc, slot-centreline-parallel line, inner arc.

Coil region (per upper side, local frame): inner radius `r_in = bore + coil_inner_clearance`; outer radius `r_out = yoke_inner − 2·fillet − liner` (stays clear of the fillet); pole-side edge = flank offset by `liner`; slot-side edge = slot centreline offset by `liner/2` (so two coils in one slot are `liner` apart).

- [ ] **Step 1: Write the failing tests**

`tests/topology/test_coils.py`:
```python
import math

import pytest

from conftest import make_8_6
from srmcore.model.errors import InputError
from srmcore.topology.primitives import sample_segment
from srmcore.topology.radial import build_outline


def _pts(coil):
    return [q for s in coil.boundary for q in sample_segment(s, 1e-4)]


def test_coil_count_names_and_signs(srm_8_6):
    coils = build_outline(srm_8_6).coil_sides
    assert len(coils) == 16
    assert len({c.name for c in coils}) == 16
    by_name = {c.name: c for c in coils}
    upper0 = [c for c in coils if c.pole == 0 and c.sign == +1][0]
    assert upper0.name == "coil_A1+"
    assert by_name["coil_A2-"].pole == 4 and by_name["coil_A2+"].pole == 4
    assert {c.phase for c in coils} == {0, 1, 2, 3}


def test_coil_boundaries_closed(reference_design):
    for c in build_outline(reference_design).coil_sides:
        segs = list(c.boundary)
        assert len(segs) == 4
        assert all(math.dist(a.end, b.start) < 1e-12 for a, b in zip(segs, segs[1:] + segs[:1]))


def test_coil_stays_inside_its_half_slot(srm_8_6):
    p = srm_8_6
    o = build_outline(p)
    upper0 = [c for c in o.coil_sides if c.pole == 0 and c.sign == +1][0]
    r_in = p.bore_radius + p.coil_inner_clearance
    r_out = p.stator_yoke_inner_radius - 2 * p.stator_fillet_radius - p.slot_liner_thickness
    for x, y in _pts(upper0):
        assert r_in - 1e-12 <= math.hypot(x, y) <= r_out + 1e-12
        assert p.stator_pole_arc / 2 < math.atan2(y, x) < math.pi / p.n_stator_poles


def test_coils_sharing_a_slot_are_one_liner_apart(srm_8_6):
    o = build_outline(srm_8_6)
    a = [c for c in o.coil_sides if c.pole == 0 and c.sign == +1][0]   # upper side of pole 0
    b = [c for c in o.coil_sides if c.pole == 1 and c.sign == -1][0]   # lower side of pole 1
    gap = min(math.dist(p, q) for p in _pts(a) for q in _pts(b))
    assert gap == pytest.approx(srm_8_6.slot_liner_thickness, rel=0.05)


def test_clearance_too_large_is_input_error():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(coil_inner_clearance=0.03))
    assert any(i.parameter == "coil_inner_clearance" and i.rule == "coil_fit" for i in info.value.issues)


def test_liner_too_thick_is_input_error():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(slot_liner_thickness=0.01))
    assert any(i.parameter == "slot_liner_thickness" and i.rule == "coil_fit" for i in info.value.issues)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/topology/test_coils.py -v`
Expected: FAIL — `assert 0 == 16` (coil_sides is empty).

- [ ] **Step 3: Implement**

Add to `src/srmcore/topology/radial.py` (above `build_outline`):
```python
def _upper_coil_boundary(p: RadialSRMParams) -> tuple[Segment, ...]:
    liner = p.slot_liner_thickness
    r_in = p.bore_radius + p.coil_inner_clearance
    r_out = p.stator_yoke_inner_radius - 2 * p.stator_fillet_radius - liner
    if r_out <= r_in:
        raise _fit_error("coil_inner_clearance", "coil_fit",
                         ValueError(f"coil radial extent {r_in:.5f}..{r_out:.5f} m is empty"))
    half = p.stator_pole_arc / 2
    face_end = (p.bore_radius * math.cos(half), p.bore_radius * math.sin(half))
    d = (math.cos(p.stator_pole_taper), math.sin(p.stator_pole_taper))
    n = (-d[1], d[0])
    # start well inside r_in so the first positive root is the crossing we want
    flank_start = (face_end[0] + liner * n[0] - p.bore_radius * d[0],
                   face_end[1] + liner * n[1] - p.bore_radius * d[1])
    alpha = math.pi / p.n_stator_poles
    u = (math.cos(alpha), math.sin(alpha))
    m = (math.sin(alpha), -math.cos(alpha))  # points from the slot centreline towards the pole
    centre_start = (0.5 * liner * m[0], 0.5 * liner * m[1])
    a, _ = line_circle_intersection(flank_start, d, r_in)
    b, _ = line_circle_intersection(flank_start, d, r_out)
    dd, _ = line_circle_intersection(centre_start, u, r_in)
    c, _ = line_circle_intersection(centre_start, u, r_out)
    if not (_angle(a) < _angle(dd) and _angle(b) < _angle(c)):
        raise _fit_error("slot_liner_thickness", "coil_fit", ValueError("no room for the coil between liners"))
    return (Line(a, b, "coil"), Arc(b, c, ORIGIN, "coil"), Line(c, dd, "coil"), Arc(dd, a, ORIGIN, "coil"))


def _coil_sides(p: RadialSRMParams) -> tuple[CoilSide, ...]:
    upper = _upper_coil_boundary(p)
    pitch = 2 * math.pi / p.n_stator_poles
    sides: list[CoilSide] = []
    for k in range(p.n_stator_poles):
        phase, group = k % p.n_phases, k // p.n_phases
        polarity = 1 if group % 2 == 0 else -1
        letter = chr(ord("A") + phase)
        a = k * pitch
        for sign, fn in ((polarity, lambda q: rotate(q, a)), (-polarity, lambda q: rotate(mirror_y(q), a))):
            boundary = tuple(map_segment(s, fn) for s in upper)
            sides.append(CoilSide(f"coil_{letter}{group + 1}{'+' if sign > 0 else '-'}", k, phase, sign, boundary))
    return tuple(sides)
```
Add `map_segment` to the primitives import list, and in `build_outline` replace `coil_sides=(),` with `coil_sides=_coil_sides(p),`.

Check the first element appended for pole `k` is the upper side (sign = polarity): yes, the first tuple entry uses the un-mirrored boundary.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/topology -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/topology/radial.py tests/topology/test_coils.py
git commit -m "feat(topology): coil sides with liner, clearance and fit checks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Mesh-settings resolution and the sizing function

**Files:**
- Create: `src/srmcore/mesh/settings.py`, `src/srmcore/mesh/sizing.py`
- Test: `tests/mesh/test_settings_sizing.py`

**Interfaces:**
- Consumes: `RadialSRMParams`, `MeshSettings` (Task 2); `REGION_SIZE_KEYS` (Task 3).
- Produces:
  - `ResolvedMeshSettings(gap_size: float, region_sizes: dict[str, float], refinement: dict[str, tuple[float, float]], band_divisions: int, min_angle_deg: float, band_min_angle_deg: float, max_aspect_ratio: float)` with property `band_pitch -> float` (radians)
  - `resolve_mesh_settings(p: RadialSRMParams, s: MeshSettings) -> ResolvedMeshSettings`
  - `size_at(x: float, y: float, base: float, features: list[tuple[np.ndarray, float, float]]) -> float` — `features` items are `(points (k,2), size_min, growth)`; result `min(base, size_min + (growth−1)·distance)` over features.

Preset numbers are **provisional** until the M5 mesh-convergence study sets them (spec §4.5): iron size = bore radius × {screening 0.08, full 0.04, reference 0.02}; band aspect (circumferential pitch ÷ gap size) = {3.0, 1.5, 1.0}; pole-tip refinement size = gap size × {3.0, 2.0, 1.5}; pole-root refinement size = iron size / 4; growth 1.3. Band divisions are rounded **up** to a multiple of lcm(Ns, Nr) so that rotating by a pole pitch maps band nodes onto band nodes.

- [ ] **Step 1: Write the failing tests**

`tests/mesh/test_settings_sizing.py`:
```python
import math

import numpy as np
import pytest

from srmcore.model.design import EdgeRefinement, MeshSettings
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.mesh.sizing import size_at


def test_full_preset_defaults(srm_8_6):
    r = resolve_mesh_settings(srm_8_6, MeshSettings())
    assert r.gap_size == pytest.approx(0.0004 / 4)
    assert r.band_divisions % 24 == 0
    r_mid = (srm_8_6.band_inner_radius + srm_8_6.band_outer_radius) / 2
    pitch_length = r_mid * r.band_pitch
    assert pitch_length <= 1.5 * r.gap_size + 1e-15   # divisions rounded up => pitch not above target
    assert pitch_length > 1.5 * r.gap_size * r.band_divisions / (r.band_divisions + 24)
    assert r.band_pitch == pytest.approx(2 * math.pi / r.band_divisions)
    assert set(r.region_sizes) == {"stator_iron", "rotor_iron", "shaft", "coil", "slot_air", "airgap"}
    assert r.region_sizes["airgap"] == r.gap_size


def test_presets_are_ordered(srm_8_6):
    s, f, ref = (resolve_mesh_settings(srm_8_6, MeshSettings(preset=k)) for k in ("screening", "full", "reference"))
    assert s.region_sizes["stator_iron"] > f.region_sizes["stator_iron"] > ref.region_sizes["stator_iron"]
    assert s.band_divisions < f.band_divisions < ref.band_divisions


def test_user_overrides(srm_8_6):
    s = MeshSettings(
        airgap_radial_layers=6,
        airgap_circumferential_divisions=480,
        region_sizes={"shaft": 0.01},
        refinement={"pole_tip": EdgeRefinement(size=5e-5, growth=1.2)},
    )
    r = resolve_mesh_settings(srm_8_6, s)
    assert r.gap_size == pytest.approx(0.0004 / 6)
    assert r.band_divisions == 480
    assert r.region_sizes["shaft"] == 0.01
    assert r.refinement["pole_tip"] == (5e-5, 1.2)
    assert r.refinement["pole_root"][1] == pytest.approx(1.3)


def test_size_at_base_feature_and_growth():
    pts = np.array([[0.0, 0.0]])
    features = [(pts, 0.001, 1.5)]
    assert size_at(0.0, 0.0, 0.01, features) == pytest.approx(0.001)
    assert size_at(0.004, 0.0, 0.01, features) == pytest.approx(0.001 + 0.5 * 0.004)
    assert size_at(1.0, 0.0, 0.01, features) == pytest.approx(0.01)
    assert size_at(1.0, 0.0, 0.01, []) == pytest.approx(0.01)
```
- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/mesh/test_settings_sizing.py -v`
Expected: `ModuleNotFoundError: No module named 'srmcore.mesh.settings'`.

- [ ] **Step 3: Implement**

`src/srmcore/mesh/settings.py`:
```python
"""Turn user mesh settings into concrete sizes. Preset numbers are provisional until the M5 convergence study."""
import math
from dataclasses import dataclass

from ..model.design import MeshSettings, RadialSRMParams


@dataclass(frozen=True)
class _Preset:
    iron_factor: float
    band_aspect: float
    tip_factor: float


PRESETS: dict[str, _Preset] = {
    "screening": _Preset(iron_factor=0.08, band_aspect=3.0, tip_factor=3.0),
    "full": _Preset(iron_factor=0.04, band_aspect=1.5, tip_factor=2.0),
    "reference": _Preset(iron_factor=0.02, band_aspect=1.0, tip_factor=1.5),
}
DEFAULT_GROWTH = 1.3


@dataclass(frozen=True)
class ResolvedMeshSettings:
    gap_size: float
    region_sizes: dict[str, float]
    refinement: dict[str, tuple[float, float]]
    band_divisions: int
    min_angle_deg: float
    band_min_angle_deg: float
    max_aspect_ratio: float

    @property
    def band_pitch(self) -> float:
        return 2 * math.pi / self.band_divisions


def resolve_mesh_settings(p: RadialSRMParams, s: MeshSettings) -> ResolvedMeshSettings:
    preset = PRESETS[s.preset]
    iron = p.bore_radius * preset.iron_factor
    sizes = {
        "stator_iron": iron, "rotor_iron": iron, "shaft": 2 * iron,
        "coil": iron, "slot_air": iron, "airgap": p.air_gap / s.airgap_radial_layers,
    }
    sizes.update(s.region_sizes)
    gap = sizes["airgap"]
    refinement = {
        "pole_tip": (preset.tip_factor * gap, DEFAULT_GROWTH),
        "pole_root": (iron / 4, DEFAULT_GROWTH),
    }
    for tag, ref in s.refinement.items():
        refinement[tag] = (ref.size, ref.growth)
    if s.airgap_circumferential_divisions is not None:
        divisions = s.airgap_circumferential_divisions
    else:
        base = math.lcm(p.n_stator_poles, p.n_rotor_poles)
        r_mid = (p.band_inner_radius + p.band_outer_radius) / 2
        target = 2 * math.pi * r_mid / (preset.band_aspect * gap)
        divisions = base * math.ceil(target / base)
    return ResolvedMeshSettings(
        gap_size=gap, region_sizes=sizes, refinement=refinement, band_divisions=divisions,
        min_angle_deg=s.min_angle_deg, band_min_angle_deg=s.band_min_angle_deg,
        max_aspect_ratio=s.max_aspect_ratio,
    )
```

`src/srmcore/mesh/sizing.py`:
```python
"""Pure sizing law used by the Gmsh size callback."""
import numpy as np


def size_at(x: float, y: float, base: float, features: list[tuple[np.ndarray, float, float]]) -> float:
    h = base
    for points, size_min, growth in features:
        distance = float(np.min(np.hypot(points[:, 0] - x, points[:, 1] - y)))
        h = min(h, size_min + (growth - 1.0) * distance)
    return h
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/mesh/test_settings_sizing.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/mesh/settings.py src/srmcore/mesh/sizing.py tests/mesh/test_settings_sizing.py
git commit -m "feat(mesh): mesh-settings resolution and sizing law" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Gmsh session and geometry with named regions

**Files:**
- Create: `src/srmcore/geometry/session.py`, `src/srmcore/geometry/build.py`
- Test: `tests/geometry/test_build.py`

**Interfaces:**
- Consumes: `RadialOutline`, `CoilSide`, `Line`, `Arc`, `sample_segment` (Tasks 4–6).
- Produces:
  - `gmsh_model() -> ContextManager[str]` — initialises Gmsh once per process (`interruptible=False`, terminal off), adds a fresh uniquely-named model, removes it on exit.
  - `GeometryModel(region_surfaces: dict[str, tuple[int, ...]], region_part: dict[str, str], region_size_key: dict[str, str], stator_outer_curve: int, band_outer_curve: int, band_inner_curve: int, band_inner_radius: float, band_outer_radius: float, refinement_points: dict[str, np.ndarray])` — tags valid only inside the `gmsh_model()` block that built it.
  - `build_geometry(outline: RadialOutline, feature_step: float) -> GeometryModel` — must be called inside `gmsh_model()`; synchronises; adds 2D physical groups named after regions and 1D groups `stator_outer`, `band_outer`, `band_inner`.
  - `STATOR_REGIONS = ("stator_iron", "slot_air", "airgap_stator")`, `ROTOR_REGIONS = ("rotor_iron", "shaft", "airgap_rotor")` — coil regions (`coil_*`) belong to the stator part.

Region layout: stator part = everything between the band's outer circle and the stator OD (`airgap_stator` = annulus band-outer..bore; `slot_air` = inside the bore boundary, outside the bore circle, minus coils). Rotor part = everything inside the band's inner circle (`airgap_rotor` includes the interpolar rotor air). The band annulus itself is **not** in Gmsh; Task 10 triangulates it.

- [ ] **Step 1: Write the failing tests**

`tests/geometry/test_build.py`:
```python
import math

import gmsh
import pytest

from srmcore.geometry.build import ROTOR_REGIONS, STATOR_REGIONS, build_geometry
from srmcore.geometry.session import gmsh_model
from srmcore.topology.radial import build_outline


def _area(tags):
    return sum(gmsh.model.occ.getMass(2, t) for t in tags)


def test_regions_parts_and_areas(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4)
        coil_names = {c.name for c in o.coil_sides}
        assert set(g.region_surfaces) == set(STATOR_REGIONS) | set(ROTOR_REGIONS) | coil_names
        assert all(len(t) >= 1 for t in g.region_surfaces.values())
        assert all(g.region_part[n] == "stator" for n in coil_names | set(STATOR_REGIONS))
        assert all(g.region_part[n] == "rotor" for n in ROTOR_REGIONS)
        assert g.region_size_key["coil_A1+"] == "coil"
        assert g.region_size_key["airgap_rotor"] == "airgap"

        stator_total = sum(_area(g.region_surfaces[n]) for n in g.region_surfaces if g.region_part[n] == "stator")
        rotor_total = sum(_area(g.region_surfaces[n]) for n in g.region_surfaces if g.region_part[n] == "rotor")
        assert stator_total == pytest.approx(math.pi * (o.stator_outer_radius**2 - o.band_outer_radius**2), rel=1e-6)
        assert rotor_total == pytest.approx(math.pi * o.band_inner_radius**2, rel=1e-6)
        assert _area(g.region_surfaces["shaft"]) == pytest.approx(math.pi * o.shaft_radius**2, rel=1e-6)
        assert all(_area(g.region_surfaces[n]) > 0 for n in coil_names)


def test_band_and_outer_curves_are_full_circles(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4)
        tags = {g.band_inner_curve, g.band_outer_curve, g.stator_outer_curve}
        assert len(tags) == 3
        for tag, radius in ((g.band_inner_curve, o.band_inner_radius),
                            (g.band_outer_curve, o.band_outer_radius),
                            (g.stator_outer_curve, o.stator_outer_radius)):
            assert gmsh.model.getType(1, tag) == "Circle"
            xmin, ymin, _, xmax, ymax, _ = gmsh.model.getBoundingBox(1, tag)
            assert xmax == pytest.approx(radius, rel=1e-4) and ymin == pytest.approx(-radius, rel=1e-4)
        names = {gmsh.model.getPhysicalName(d, t) for d, t in gmsh.model.getPhysicalGroups()}
        assert {"stator_outer", "band_outer", "band_inner", "stator_iron", "coil_A1+"} <= names


def test_refinement_points_sampled(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4)
    assert g.refinement_points["pole_tip"].shape[1] == 2
    assert len(g.refinement_points["pole_tip"]) > 14
    assert len(g.refinement_points["pole_root"]) >= 28


def test_session_isolation_and_reuse(srm_8_6):
    o = build_outline(srm_8_6)
    areas = []
    for _ in range(2):
        with gmsh_model() as name:
            g = build_geometry(o, feature_step=1e-4)
            areas.append(_area(g.region_surfaces["stator_iron"]))
        assert name not in gmsh.model.list()
    assert areas[0] == pytest.approx(areas[1], rel=1e-12)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/geometry/test_build.py -v`
Expected: `ModuleNotFoundError: No module named 'srmcore.geometry.build'`.

- [ ] **Step 3: Implement the session**

`src/srmcore/geometry/session.py`:
```python
"""One Gmsh initialisation per process; a fresh, isolated model per use."""
import itertools
from collections.abc import Iterator
from contextlib import contextmanager

import gmsh

_initialized = False
_counter = itertools.count()


@contextmanager
def gmsh_model() -> Iterator[str]:
    global _initialized
    if not _initialized:
        gmsh.initialize(readConfigFiles=False, interruptible=False)
        gmsh.option.setNumber("General.Terminal", 0)
        _initialized = True
    name = f"srm_{next(_counter)}"
    gmsh.model.add(name)
    try:
        yield name
    finally:
        gmsh.model.setCurrent(name)
        gmsh.model.remove()
```

- [ ] **Step 4: Implement the geometry build**

`src/srmcore/geometry/build.py`:
```python
"""Outline -> Gmsh OCC surfaces with named regions. Call inside geometry.session.gmsh_model()."""
from dataclasses import dataclass

import gmsh
import numpy as np

from ..topology.primitives import Line, Point, Segment, sample_segment
from ..topology.radial import RadialOutline

STATOR_REGIONS = ("stator_iron", "slot_air", "airgap_stator")
ROTOR_REGIONS = ("rotor_iron", "shaft", "airgap_rotor")


@dataclass(frozen=True)
class GeometryModel:
    region_surfaces: dict[str, tuple[int, ...]]
    region_part: dict[str, str]
    region_size_key: dict[str, str]
    stator_outer_curve: int
    band_outer_curve: int
    band_inner_curve: int
    band_inner_radius: float
    band_outer_radius: float
    refinement_points: dict[str, np.ndarray]


class _Points:
    def __init__(self) -> None:
        self._tags: dict[tuple[float, float], int] = {}

    def get(self, q: Point) -> int:
        key = (round(q[0], 12), round(q[1], 12))
        if key not in self._tags:
            self._tags[key] = gmsh.model.occ.addPoint(q[0], q[1], 0.0)
        return self._tags[key]


def _curves(segments: tuple[Segment, ...], points: _Points, centres: list[int]) -> list[int]:
    occ = gmsh.model.occ
    curves = []
    for s in segments:
        a, b = points.get(s.start), points.get(s.end)
        if isinstance(s, Line):
            curves.append(occ.addLine(a, b))
        else:
            c = occ.addPoint(s.center[0], s.center[1], 0.0)
            centres.append(c)
            curves.append(occ.addCircleArc(a, c, b))
    return curves


def _full_circle_on_boundary(surfaces: tuple[int, ...], radius: float, tol: float) -> int:
    boundary = gmsh.model.getBoundary([(2, s) for s in surfaces], combined=False, oriented=False)
    for _, tag in boundary:
        xmin, ymin, _, xmax, ymax, _ = gmsh.model.getBoundingBox(1, abs(tag))
        if all(abs(v - w) < tol for v, w in ((xmax, radius), (xmin, -radius), (ymax, radius), (ymin, -radius))):
            return abs(tag)
    raise RuntimeError(f"no full circle of radius {radius} on the boundary")


def _size_key(region: str) -> str:
    if region.startswith("coil_"):
        return "coil"
    if region.startswith("airgap_"):
        return "airgap"
    return region


def build_geometry(outline: RadialOutline, feature_step: float) -> GeometryModel:
    occ = gmsh.model.occ
    points = _Points()
    centres: list[int] = []

    # stator part
    outer_loop = occ.addCurveLoop([occ.addCircle(0, 0, 0, outline.stator_outer_radius)])
    bore_curves = _curves(outline.stator_inner_boundary, points, centres)
    stator_iron = occ.addPlaneSurface([outer_loop, occ.addCurveLoop(bore_curves)])
    inside_bore = occ.addPlaneSurface([occ.addCurveLoop(bore_curves)])
    coils = [(c.name, occ.addPlaneSurface([occ.addCurveLoop(_curves(c.boundary, points, centres))]))
             for c in outline.coil_sides]
    bore_disk = occ.addDisk(0, 0, 0, outline.bore_radius, outline.bore_radius)
    band_out_disk = occ.addDisk(0, 0, 0, outline.band_outer_radius, outline.band_outer_radius)
    slot_air, _ = occ.cut([(2, inside_bore)], [(2, bore_disk)] + [(2, t) for _, t in coils],
                          removeObject=True, removeTool=False)
    gap_stator, _ = occ.cut([(2, bore_disk)], [(2, band_out_disk)])

    # rotor part
    rotor_area = occ.addPlaneSurface([occ.addCurveLoop(_curves(outline.rotor_outer_boundary, points, centres))])
    shaft = occ.addDisk(0, 0, 0, outline.shaft_radius, outline.shaft_radius)
    band_in_disk = occ.addDisk(0, 0, 0, outline.band_inner_radius, outline.band_inner_radius)
    gap_rotor, _ = occ.cut([(2, band_in_disk)], [(2, rotor_area)], removeObject=True, removeTool=False)
    rotor_iron, _ = occ.cut([(2, rotor_area)], [(2, shaft)], removeObject=True, removeTool=False)

    occ.remove([(0, c) for c in centres])

    named: list[tuple[str, list[tuple[int, int]]]] = (
        [("stator_iron", [(2, stator_iron)]), ("slot_air", slot_air), ("airgap_stator", gap_stator)]
        + [(name, [(2, tag)]) for name, tag in coils]
        + [("rotor_iron", rotor_iron), ("shaft", [(2, shaft)]), ("airgap_rotor", gap_rotor)]
    )
    objects = [dt for _, dts in named for dt in dts]
    _, out_map = occ.fragment(objects, [])
    occ.synchronize()

    region_surfaces: dict[str, tuple[int, ...]] = {}
    index = 0
    for name, dts in named:
        tags: list[int] = []
        for _ in dts:
            tags.extend(t for d, t in out_map[index] if d == 2)
            index += 1
        region_surfaces[name] = tuple(sorted(set(tags)))
    all_tags = [t for tags in region_surfaces.values() for t in tags]
    if len(all_tags) != len(set(all_tags)):
        raise RuntimeError("a surface was assigned to two regions")

    region_part = {n: ("rotor" if n in ROTOR_REGIONS else "stator") for n in region_surfaces}
    tol = (outline.band_outer_radius - outline.band_inner_radius) / 4
    stator_outer = _full_circle_on_boundary(region_surfaces["stator_iron"], outline.stator_outer_radius, tol)
    band_outer = _full_circle_on_boundary(region_surfaces["airgap_stator"], outline.band_outer_radius, tol)
    band_inner = _full_circle_on_boundary(region_surfaces["airgap_rotor"], outline.band_inner_radius, tol)

    for name, tags in region_surfaces.items():
        gmsh.model.addPhysicalGroup(2, list(tags), name=name)
    gmsh.model.addPhysicalGroup(1, [stator_outer], name="stator_outer")
    gmsh.model.addPhysicalGroup(1, [band_outer], name="band_outer")
    gmsh.model.addPhysicalGroup(1, [band_inner], name="band_inner")

    refinement_points = {}
    for tag, features in outline.refinement_features.items():
        pts: list[Point] = []
        for f in features:
            pts.extend(sample_segment(f, feature_step) if not isinstance(f, tuple) else [f])
        refinement_points[tag] = np.asarray(pts, dtype=float).reshape(-1, 2)

    return GeometryModel(
        region_surfaces=region_surfaces, region_part=region_part,
        region_size_key={n: _size_key(n) for n in region_surfaces},
        stator_outer_curve=stator_outer, band_outer_curve=band_outer, band_inner_curve=band_inner,
        band_inner_radius=outline.band_inner_radius, band_outer_radius=outline.band_outer_radius,
        refinement_points=refinement_points,
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/geometry -v`
Expected: all pass. If `occ.remove` of arc centre points raises because Gmsh already dropped them, wrap it as `occ.remove([(0, c) for c in centres], recursive=False)` and keep the test green — the tests pin the regions, not the call.

- [ ] **Step 6: Commit**

```bash
git add src/srmcore/geometry tests/geometry
git commit -m "feat(geometry): gmsh session and OCC geometry with named regions and band circles" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Static stator and rotor meshes

**Files:**
- Modify: `pyproject.toml` (add `"scipy>=1.12"` to `dependencies`), `src/srmcore/mesh/sizing.py` (add `SizeField`), `src/srmcore/geometry/build.py` (add `build_machine_geometry`)
- Create: `src/srmcore/mesh/static.py`
- Test: `tests/mesh/test_static.py`

**Interfaces:**
- Consumes: `Design`, `require_valid` (Tasks 2–3); `resolve_mesh_settings`, `size_at` (Task 7); `gmsh_model`, `build_geometry`, `GeometryModel` (Task 8); `build_outline` (Task 5, via geometry).
- Produces:
  - `SizeField(features: list[tuple[np.ndarray, float, float]])`, callable `field(x, y, base) -> float` — same result as `size_at`, KD-tree accelerated.
  - `build_machine_geometry(p: RadialSRMParams, feature_step: float) -> GeometryModel`
  - `MeshPart(nodes: np.ndarray (n,2) float64, triangles: np.ndarray (m,3) int64 CCW, region_ids: np.ndarray (m,) int32)`
  - `StaticMesh(region_names: tuple[str, ...], stator: MeshPart, rotor: MeshPart, stator_ring: np.ndarray, rotor_ring: np.ndarray, outer_edges: np.ndarray, band_inner_radius: float, band_outer_radius: float, settings: ResolvedMeshSettings, warnings: tuple[ValidationIssue, ...])` — rings are node indices **into their own part**, sorted by angle, length `settings.band_divisions`; `outer_edges` are stator node index pairs on the stator OD; `region_names` sorted alphabetically (region id = position).
  - `orient_ccw(nodes: np.ndarray, triangles: np.ndarray) -> np.ndarray`
  - `build_static_mesh(design: Design) -> StaticMesh` — validates first (raises `InputError` before touching Gmsh).

- [ ] **Step 1: Add scipy and install**

In `pyproject.toml` `dependencies` add `"scipy>=1.12",`. Run: `python -m pip install -e ".[dev]"`. Expected: scipy installed.

- [ ] **Step 2: Write the failing tests**

`tests/mesh/test_static.py`:
```python
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError
from srmcore.mesh.sizing import SizeField, size_at
from srmcore.mesh.static import build_static_mesh, orient_ccw


@pytest.fixture(scope="module")
def static_8_6():
    return build_static_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _areas(nodes, tris):
    p = nodes[tris]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def test_size_field_matches_size_at():
    rng = np.random.default_rng(0)
    features = [(rng.random((50, 2)), 0.01, 1.3), (rng.random((5, 2)), 0.002, 1.1)]
    field = SizeField(features)
    for x, y in rng.random((20, 2)):
        assert field(x, y, 0.05) == pytest.approx(size_at(x, y, 0.05, features))


def test_orient_ccw_flips_clockwise():
    nodes = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    assert orient_ccw(nodes, np.array([[0, 2, 1]])).tolist() == [[0, 1, 2]]


def test_parts_are_valid_and_ccw(static_8_6):
    for part in (static_8_6.stator, static_8_6.rotor):
        assert len(part.nodes) > 0 and len(part.triangles) > 0
        assert np.all(_areas(part.nodes, part.triangles) > 0)
        assert part.triangles.max() < len(part.nodes)


def test_part_areas_match_geometry(static_8_6):
    p = make_8_6()
    s = static_8_6
    assert _areas(s.stator.nodes, s.stator.triangles).sum() == pytest.approx(
        math.pi * (p.stator_outer_radius**2 - p.band_outer_radius**2), rel=2e-3)
    assert _areas(s.rotor.nodes, s.rotor.triangles).sum() == pytest.approx(math.pi * p.band_inner_radius**2, rel=2e-3)


def test_every_region_has_triangles(static_8_6):
    s = static_8_6
    used = set(np.unique(s.stator.region_ids)) | set(np.unique(s.rotor.region_ids))
    assert used == set(range(len(s.region_names)))
    assert "coil_D2-" in s.region_names and "airgap_rotor" in s.region_names


def test_band_rings_are_uniform(static_8_6):
    s = static_8_6
    n = s.settings.band_divisions
    for nodes, ring, radius in ((s.stator.nodes, s.stator_ring, s.band_outer_radius),
                                (s.rotor.nodes, s.rotor_ring, s.band_inner_radius)):
        assert len(ring) == n   # if this is n+1 or n-1, fix the setTransfiniteCurve count in static.py
        xy = nodes[ring]
        assert np.allclose(np.hypot(xy[:, 0], xy[:, 1]), radius, rtol=1e-9)
        ang = np.mod(np.arctan2(xy[:, 1], xy[:, 0]), 2 * math.pi)
        assert np.allclose(np.diff(ang), 2 * math.pi / n, rtol=1e-6)


def test_outer_edges_on_stator_od(static_8_6):
    xy = static_8_6.stator.nodes[static_8_6.outer_edges.ravel()]
    assert np.allclose(np.hypot(xy[:, 0], xy[:, 1]), make_8_6().stator_outer_radius, rtol=1e-9)


def test_gap_elements_are_small(static_8_6):
    s = static_8_6
    gap_id = s.region_names.index("airgap_stator")
    tris = s.stator.triangles[s.stator.region_ids == gap_id]
    p = s.stator.nodes[tris]
    longest = np.max(np.linalg.norm(p - np.roll(p, 1, axis=1), axis=2))
    pitch_len = s.band_outer_radius * s.settings.band_pitch
    assert longest <= 1.3 * max(s.settings.gap_size, pitch_len)


def test_invalid_design_fails_before_gmsh():
    with pytest.raises(InputError):
        build_static_mesh(Design(machine=make_8_6(air_gap=-0.001)))
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/mesh/test_static.py -v`
Expected: `ImportError` for `SizeField` / `srmcore.mesh.static`.

- [ ] **Step 4: Implement `SizeField` and `build_machine_geometry`**

Append to `src/srmcore/mesh/sizing.py`:
```python
from scipy.spatial import cKDTree


class SizeField:
    """KD-tree accelerated equivalent of size_at, for the Gmsh size callback."""

    def __init__(self, features: list[tuple[np.ndarray, float, float]]):
        self._items = [(cKDTree(points), size_min, growth) for points, size_min, growth in features if len(points)]

    def __call__(self, x: float, y: float, base: float) -> float:
        h = base
        for tree, size_min, growth in self._items:
            distance, _ = tree.query((x, y))
            h = min(h, size_min + (growth - 1.0) * float(distance))
        return h
```
(Move the `from scipy.spatial import cKDTree` line to the top of the file with the other imports.)

Append to `src/srmcore/geometry/build.py`:
```python
def build_machine_geometry(p: RadialSRMParams, feature_step: float) -> GeometryModel:
    return build_geometry(build_outline(p), feature_step)
```
and add imports `from ..model.design import RadialSRMParams` and `from ..topology.radial import build_outline` (extend the existing `..topology.radial` import).

- [ ] **Step 5: Implement the static mesh**

`src/srmcore/mesh/static.py`:
```python
"""Mesh the stator part and the rotor part once (rotor at angle 0). The band is built later per angle."""
import math
from dataclasses import dataclass

import gmsh
import numpy as np

from ..geometry.build import GeometryModel, build_machine_geometry
from ..geometry.session import gmsh_model
from ..model.design import Design
from ..model.errors import ValidationIssue
from ..model.validator import require_valid
from .settings import ResolvedMeshSettings, resolve_mesh_settings
from .sizing import SizeField

TRIANGLE = 2
LINE = 1


@dataclass(frozen=True)
class MeshPart:
    nodes: np.ndarray
    triangles: np.ndarray
    region_ids: np.ndarray


@dataclass(frozen=True)
class StaticMesh:
    region_names: tuple[str, ...]
    stator: MeshPart
    rotor: MeshPart
    stator_ring: np.ndarray
    rotor_ring: np.ndarray
    outer_edges: np.ndarray
    band_inner_radius: float
    band_outer_radius: float
    settings: ResolvedMeshSettings
    warnings: tuple[ValidationIssue, ...]


def orient_ccw(nodes: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    p = nodes[triangles]
    signed = ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
              - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))
    out = triangles.copy()
    flip = signed < 0
    out[flip, 1], out[flip, 2] = triangles[flip, 2], triangles[flip, 1]
    return out


def _apply_mesh_options(geom: GeometryModel, resolved: ResolvedMeshSettings) -> None:
    opt = gmsh.option.setNumber
    opt("Mesh.MeshSizeExtendFromBoundary", 0)
    opt("Mesh.MeshSizeFromPoints", 0)
    opt("Mesh.MeshSizeFromCurvature", 0)
    opt("Mesh.Algorithm", 6)
    opt("Mesh.ElementOrder", 1)
    max_size = max(resolved.region_sizes.values())
    opt("Mesh.MeshSizeMax", max_size)
    for curve in (geom.band_inner_curve, geom.band_outer_curve):
        gmsh.model.mesh.setTransfiniteCurve(curve, resolved.band_divisions + 1)

    surface_size = {t: resolved.region_sizes[geom.region_size_key[name]]
                    for name, tags in geom.region_surfaces.items() for t in tags}
    curve_size: dict[int, float] = {}
    for _, c in gmsh.model.getEntities(1):
        up, _ = gmsh.model.getAdjacencies(1, c)
        curve_size[c] = min((surface_size[s] for s in up if s in surface_size), default=max_size)
    point_size: dict[int, float] = {}
    for _, q in gmsh.model.getEntities(0):
        up, _ = gmsh.model.getAdjacencies(0, q)
        point_size[q] = min((curve_size[c] for c in up if c in curve_size), default=max_size)
    by_dim = {0: point_size, 1: curve_size, 2: surface_size}
    field = SizeField([(geom.refinement_points[tag], size, growth)
                       for tag, (size, growth) in resolved.refinement.items() if tag in geom.refinement_points])

    def callback(dim: int, tag: int, x: float, y: float, z: float, lc: float) -> float:
        return field(x, y, by_dim.get(dim, {}).get(tag, max_size))

    gmsh.model.mesh.setSizeCallback(callback)


def _all_nodes() -> tuple[np.ndarray, np.ndarray]:
    tags, coords, _ = gmsh.model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    order = np.argsort(tags)
    return tags[order], np.asarray(coords, dtype=float).reshape(-1, 3)[order, :2]


def _extract_part(geom: GeometryModel, region_names: tuple[str, ...], part: str,
                  sorted_tags: np.ndarray, sorted_xy: np.ndarray) -> tuple[MeshPart, np.ndarray]:
    tri_blocks, id_blocks = [], []
    for rid, name in enumerate(region_names):
        if geom.region_part[name] != part:
            continue
        for surface in geom.region_surfaces[name]:
            types, _, node_tags = gmsh.model.mesh.getElements(2, surface)
            for etype, tags in zip(types, node_tags):
                if etype != TRIANGLE:
                    raise RuntimeError(f"unexpected element type {etype} in region {name}")
                block = np.asarray(tags, dtype=np.int64).reshape(-1, 3)
                tri_blocks.append(block)
                id_blocks.append(np.full(len(block), rid, dtype=np.int32))
    tri_tags = np.vstack(tri_blocks)
    used = np.unique(tri_tags)
    nodes = sorted_xy[np.searchsorted(sorted_tags, used)].copy()
    triangles = orient_ccw(nodes, np.searchsorted(used, tri_tags).astype(np.int64))
    return MeshPart(nodes, triangles, np.concatenate(id_blocks)), used


def _local(used: np.ndarray, tags: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(used, tags)
    if np.any(idx >= len(used)) or np.any(used[idx] != tags):
        raise RuntimeError("boundary node not found in its part")
    return idx


def _ring(curve: int, used: np.ndarray, nodes: np.ndarray, n: int) -> np.ndarray:
    tags, _, _ = gmsh.model.mesh.getNodes(1, curve, includeBoundary=True)
    idx = _local(used, np.unique(np.asarray(tags, dtype=np.int64)))
    angles = np.mod(np.arctan2(nodes[idx, 1], nodes[idx, 0]), 2 * math.pi)
    idx = idx[np.argsort(angles)]
    if len(idx) != n:
        raise RuntimeError(f"band ring has {len(idx)} nodes, expected {n}")
    return idx


def _edges(curve: int, used: np.ndarray) -> np.ndarray:
    types, _, node_tags = gmsh.model.mesh.getElements(1, curve)
    blocks = [np.asarray(t, dtype=np.int64).reshape(-1, 2) for e, t in zip(types, node_tags) if e == LINE]
    return _local(used, np.vstack(blocks).ravel()).reshape(-1, 2)


def build_static_mesh(design: Design) -> StaticMesh:
    warnings = require_valid(design)
    p = design.machine
    resolved = resolve_mesh_settings(p, design.mesh)
    with gmsh_model():
        geom = build_machine_geometry(p, feature_step=resolved.gap_size)
        _apply_mesh_options(geom, resolved)
        try:
            gmsh.model.mesh.generate(2)
        finally:
            gmsh.model.mesh.removeSizeCallback()
        region_names = tuple(sorted(geom.region_surfaces))
        sorted_tags, sorted_xy = _all_nodes()
        stator, stator_used = _extract_part(geom, region_names, "stator", sorted_tags, sorted_xy)
        rotor, rotor_used = _extract_part(geom, region_names, "rotor", sorted_tags, sorted_xy)
        n = resolved.band_divisions
        stator_ring = _ring(geom.band_outer_curve, stator_used, stator.nodes, n)
        rotor_ring = _ring(geom.band_inner_curve, rotor_used, rotor.nodes, n)
        outer_edges = _edges(geom.stator_outer_curve, stator_used)
    return StaticMesh(
        region_names=region_names, stator=stator, rotor=rotor,
        stator_ring=stator_ring, rotor_ring=rotor_ring, outer_edges=outer_edges,
        band_inner_radius=p.band_inner_radius, band_outer_radius=p.band_outer_radius,
        settings=resolved, warnings=tuple(warnings),
    )
```

- [ ] **Step 6: Run to verify pass**

Run: `python -m pytest tests/mesh/test_static.py -v`
Expected: all pass. If `test_band_rings_are_uniform` reports `n + 1` or `n − 1` ring nodes, Gmsh's closed-curve count convention differs from `band_divisions + 1`: change that argument in `_apply_mesh_options` to `resolved.band_divisions` (or `+ 2`) until the test passes — the test is the contract.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/srmcore/mesh src/srmcore/geometry/build.py tests/mesh/test_static.py
git commit -m "feat(mesh): static stator/rotor meshes with size callback and uniform band rings" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Moving band and the machine mesh at any rotor angle

**Files:**
- Create: `src/srmcore/mesh/band.py`, `src/srmcore/mesh/quality.py` (only `triangle_quality` in this task), `src/srmcore/mesh/machine.py`
- Test: `tests/mesh/test_band.py`, `tests/mesh/test_machine.py`

**Interfaces:**
- Consumes: `StaticMesh`, `orient_ccw` (Task 9); `MeshRejected` (Task 2).
- Produces:
  - `snap_angle(theta: float, divisions: int) -> tuple[float, int]` — nearest multiple of the band pitch and its index.
  - `zipper_band(inner_angles: np.ndarray, outer_angles: np.ndarray) -> np.ndarray` — `(n_in + n_out, 3)` int64 triangles; inner node `i` → `i`, outer node `j` → `n_in + j`; orientation not normalised.
  - `triangle_quality(nodes: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]` — per-triangle minimum angle (degrees) and aspect ratio (longest edge ÷ (2√3 · inradius); equilateral = 1).
  - `MachineMesh(nodes, triangles, region_ids, region_names, n_stator_nodes: int, outer_edges, rotor_angle: float, band_rows: slice)` — stator nodes first (indices `0..n_stator_nodes-1`), then rotor nodes; node numbering is identical at every angle; `region_names` = static names + `("moving_band",)`; `rotor_angle` wrapped to `[0, 2π)`.
  - `mesh_at_angle(static: StaticMesh, theta: float, check: bool = True) -> MachineMesh` — raises `MeshRejected` if `check` and any band triangle's minimum angle is below `static.settings.band_min_angle_deg`.

- [ ] **Step 1: Write the failing band tests**

`tests/mesh/test_band.py`:
```python
import math

import numpy as np
import pytest

from srmcore.mesh.band import snap_angle, zipper_band
from srmcore.mesh.static import orient_ccw

TAU = 2 * math.pi


def _rings(n_in, n_out, offset):
    a_in = np.arange(n_in) * TAU / n_in + offset
    a_out = np.arange(n_out) * TAU / n_out
    nodes = np.vstack([np.c_[np.cos(a_in), np.sin(a_in)], 1.1 * np.c_[np.cos(a_out), np.sin(a_out)]])
    return a_in, a_out, nodes


def _signed(nodes, tris):
    p = nodes[tris]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def _polygon_area(n, r):
    return 0.5 * n * r * r * math.sin(TAU / n)


def test_snap_angle():
    pitch = TAU / 24
    assert snap_angle(0.26, 24) == (pytest.approx(pitch), 1)
    assert snap_angle(-0.01, 24)[1] == 0


@pytest.mark.parametrize("n_in,n_out,offset_frac", [
    (12, 12, 0.0), (12, 12, 0.5), (12, 12, 0.3), (12, 12, 1.0), (12, 12, -0.2), (10, 14, 0.25),
])
def test_zipper_covers_annulus_exactly(n_in, n_out, offset_frac):
    a_in, a_out, nodes = _rings(n_in, n_out, offset_frac * TAU / n_in)
    tris = orient_ccw(nodes, zipper_band(a_in, a_out))
    assert len(tris) == n_in + n_out
    areas = _signed(nodes, tris)
    assert np.all(areas > 1e-9)
    assert areas.sum() == pytest.approx(_polygon_area(n_out, 1.1) - _polygon_area(n_in, 1.0), rel=1e-12)


def test_every_ring_edge_used_once():
    n = 12
    a_in, a_out, nodes = _rings(n, n, 0.37 * TAU / n)
    tris = zipper_band(a_in, a_out)
    edges = {}
    for t in tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key = (min(a, b), max(a, b))
            edges[key] = edges.get(key, 0) + 1
    for i in range(n):
        assert edges[(min(i, (i + 1) % n), max(i, (i + 1) % n))] == 1
        j, k = n + i, n + (i + 1) % n
        assert edges[(min(j, k), max(j, k))] == 1
```

- [ ] **Step 2: Write the failing machine tests**

`tests/mesh/test_machine.py`:
```python
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.model.design import Design, MeshSettings
from srmcore.mesh.machine import mesh_at_angle
from srmcore.mesh.quality import triangle_quality
from srmcore.mesh.static import build_static_mesh

TAU = 2 * math.pi


@pytest.fixture(scope="module")
def static_8_6():
    return build_static_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _areas(nodes, tris):
    p = nodes[tris]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def test_triangle_quality_reference_shapes():
    nodes = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, math.sqrt(3) / 2], [0.0, 1.0]])
    min_angle, aspect = triangle_quality(nodes, np.array([[0, 1, 2], [0, 1, 3]]))
    assert min_angle[0] == pytest.approx(60.0) and aspect[0] == pytest.approx(1.0)
    assert min_angle[1] == pytest.approx(45.0) and aspect[1] == pytest.approx(math.sqrt(2) / (2 * math.sqrt(3) * (1 - math.sqrt(2) / 2)))


def test_mesh_at_zero_is_complete_and_ccw(static_8_6):
    m = mesh_at_angle(static_8_6, 0.0)
    assert np.all(_areas(m.nodes, m.triangles) > 0)
    assert m.region_names[-1] == "moving_band"
    assert m.triangles[m.band_rows].shape[0] == 2 * static_8_6.settings.band_divisions
    assert _areas(m.nodes, m.triangles).sum() == pytest.approx(math.pi * make_8_6().stator_outer_radius**2, rel=2e-3)


def test_node_numbering_is_stable_and_rotor_rotates(static_8_6):
    theta = 0.123
    m0, m1 = mesh_at_angle(static_8_6, 0.0), mesh_at_angle(static_8_6, theta)
    ns = m0.n_stator_nodes
    assert np.array_equal(m0.nodes[:ns], m1.nodes[:ns])
    c, s = math.cos(theta), math.sin(theta)
    x, y = m0.nodes[ns:, 0], m0.nodes[ns:, 1]
    assert np.allclose(m1.nodes[ns:], np.c_[c * x - s * y, s * x + c * y], atol=1e-15)
    assert np.array_equal(m0.triangles[: m0.band_rows.start], m1.triangles[: m1.band_rows.start])


@pytest.mark.parametrize("shift", [TAU, -TAU, 7 * TAU])
def test_angle_wrapping(static_8_6, shift):
    a, b = mesh_at_angle(static_8_6, 0.4), mesh_at_angle(static_8_6, 0.4 + shift)
    assert b.rotor_angle == pytest.approx(a.rotor_angle, abs=1e-12)
    assert np.allclose(a.nodes, b.nodes, atol=1e-12)
    assert np.array_equal(a.triangles, b.triangles)


def test_band_quality_at_pitch_multiples_and_half_pitch(static_8_6):
    pitch = static_8_6.settings.band_pitch
    q = {}
    for k in (0.0, 1.0, 0.5, 3.25):
        m = mesh_at_angle(static_8_6, k * pitch)
        band = m.triangles[m.band_rows]
        q[k] = triangle_quality(m.nodes, band)[0].min()
        assert q[k] >= static_8_6.settings.band_min_angle_deg
    assert q[0.0] == pytest.approx(q[1.0], abs=1e-9)
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/mesh/test_band.py tests/mesh/test_machine.py -v`
Expected: `ModuleNotFoundError` for `srmcore.mesh.band` / `machine` / `quality`.

- [ ] **Step 4: Implement**

`src/srmcore/mesh/band.py`:
```python
"""Moving band: conforming triangulation between the rotor ring and the stator ring at any angle."""
import math

import numpy as np

TAU = 2 * math.pi


def snap_angle(theta: float, divisions: int) -> tuple[float, int]:
    pitch = TAU / divisions
    k = round(theta / pitch)
    return k * pitch, k


def zipper_band(inner_angles: np.ndarray, outer_angles: np.ndarray) -> np.ndarray:
    n_in = len(inner_angles)
    a_in = np.mod(inner_angles, TAU)
    a_out = np.mod(outer_angles, TAU)
    out_order = np.argsort(a_out, kind="stable")
    first_out = int(out_order[0])
    start = a_out[first_out]
    rel_in = np.mod(a_in - start, TAU)
    rel_out = np.mod(a_out - start, TAU)
    events = sorted([(float(rel_out[j]), 1, int(j)) for j in out_order[1:]]
                    + [(float(rel_in[i]), 0, i) for i in range(n_in)])
    last_out = first_out
    last_in = int(np.argmax(rel_in))
    tris: list[tuple[int, int, int]] = []
    for _, kind, idx in events:
        if kind == 1:
            tris.append((last_in, n_in + last_out, n_in + idx))
            last_out = idx
        else:
            tris.append((last_in, n_in + last_out, idx))
            last_in = idx
    tris.append((last_in, n_in + last_out, n_in + first_out))
    return np.asarray(tris, dtype=np.int64)
```

`src/srmcore/mesh/quality.py`:
```python
"""Triangle and mesh quality metrics."""
import numpy as np


def triangle_quality(nodes: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = nodes[triangles]
    a = np.linalg.norm(p[:, 1] - p[:, 2], axis=1)
    b = np.linalg.norm(p[:, 0] - p[:, 2], axis=1)
    c = np.linalg.norm(p[:, 0] - p[:, 1], axis=1)
    ang_a = np.arccos(np.clip((b * b + c * c - a * a) / (2 * b * c), -1.0, 1.0))
    ang_b = np.arccos(np.clip((a * a + c * c - b * b) / (2 * a * c), -1.0, 1.0))
    ang_c = np.pi - ang_a - ang_b
    min_angle = np.degrees(np.minimum(np.minimum(ang_a, ang_b), ang_c))
    area = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                        - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))
    inradius = area / (0.5 * (a + b + c))
    aspect = np.maximum(np.maximum(a, b), c) / (2 * np.sqrt(3) * inradius)
    return min_angle, aspect
```

`src/srmcore/mesh/machine.py`:
```python
"""Full machine mesh at a rotor angle: fixed stator + rotated rotor + re-triangulated moving band."""
import math
from dataclasses import dataclass

import numpy as np

from ..model.errors import MeshRejected
from .band import TAU, zipper_band
from .quality import triangle_quality
from .static import StaticMesh, orient_ccw


@dataclass(frozen=True)
class MachineMesh:
    nodes: np.ndarray
    triangles: np.ndarray
    region_ids: np.ndarray
    region_names: tuple[str, ...]
    n_stator_nodes: int
    outer_edges: np.ndarray
    rotor_angle: float
    band_rows: slice


def mesh_at_angle(static: StaticMesh, theta: float, check: bool = True) -> MachineMesh:
    wrapped = theta % TAU
    c, s = math.cos(wrapped), math.sin(wrapped)
    rotor_xy = static.rotor.nodes @ np.array([[c, s], [-s, c]])
    nodes = np.vstack([static.stator.nodes, rotor_xy])
    ns = len(static.stator.nodes)

    ring_in = static.rotor.nodes[static.rotor_ring]
    ring_out = static.stator.nodes[static.stator_ring]
    inner_angles = np.arctan2(ring_in[:, 1], ring_in[:, 0]) + wrapped
    outer_angles = np.arctan2(ring_out[:, 1], ring_out[:, 0])
    lookup = np.concatenate([ns + static.rotor_ring, static.stator_ring])
    band = orient_ccw(nodes, lookup[zipper_band(inner_angles, outer_angles)])

    triangles = np.vstack([static.stator.triangles, static.rotor.triangles + ns, band])
    band_id = len(static.region_names)
    region_ids = np.concatenate([static.stator.region_ids, static.rotor.region_ids,
                                 np.full(len(band), band_id, dtype=np.int32)])
    start = len(triangles) - len(band)
    if check:
        worst = float(triangle_quality(nodes, band)[0].min())
        if worst < static.settings.band_min_angle_deg:
            raise MeshRejected([f"band min angle {worst:.2f}° < {static.settings.band_min_angle_deg}°"],
                               report={"rotor_angle": wrapped, "band_min_angle_deg": worst})
    return MachineMesh(
        nodes=nodes, triangles=triangles, region_ids=region_ids,
        region_names=static.region_names + ("moving_band",), n_stator_nodes=ns,
        outer_edges=static.outer_edges, rotor_angle=wrapped, band_rows=slice(start, len(triangles)),
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/mesh/test_band.py tests/mesh/test_machine.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/srmcore/mesh/band.py src/srmcore/mesh/quality.py src/srmcore/mesh/machine.py tests/mesh/test_band.py tests/mesh/test_machine.py
git commit -m "feat(mesh): moving-band zipper triangulation and machine mesh at any rotor angle" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Quality report, quality gate, mesh plot and the public entry point

**Files:**
- Modify: `src/srmcore/mesh/quality.py` (add report + check)
- Create: `src/srmcore/mesh/plot.py`, `src/srmcore/mesh/api.py`
- Modify: `src/srmcore/mesh/__init__.py` (public exports)
- Test: `tests/mesh/test_quality_plot.py`

**Interfaces:**
- Consumes: Tasks 9–10.
- Produces:
  - `MeshQualityReport(n_nodes: int, n_triangles: int, min_angle_deg: float, max_aspect_ratio: float, band_min_angle_deg: float, triangles_per_region: dict[str, int])` — `min_angle_deg`/`max_aspect_ratio` exclude the band.
  - `quality_report(mesh: MachineMesh) -> MeshQualityReport`
  - `check_quality(report: MeshQualityReport, settings: ResolvedMeshSettings) -> None` — raises `MeshRejected` listing every violated threshold.
  - `plot_mesh(mesh: MachineMesh, path: str | Path, title: str | None = None) -> Path` (PNG, regions coloured).
  - `build_machine_mesh(design: Design) -> StaticMesh` — builds the static mesh, then gates quality at rotor angle 0 and at half a band pitch.
  - `srmcore.mesh` exports: `build_machine_mesh, mesh_at_angle, snap_angle, quality_report, check_quality, plot_mesh, StaticMesh, MachineMesh, MeshQualityReport`.

- [ ] **Step 1: Write the failing tests**

`tests/mesh/test_quality_plot.py`:
```python
import dataclasses

import numpy as np
import pytest

from conftest import make_8_6, make_12_8, make_24_16
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MeshRejected
from srmcore.mesh import build_machine_mesh, check_quality, mesh_at_angle, plot_mesh, quality_report


@pytest.fixture(scope="module")
def static_8_6():
    return build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def test_report_counts(static_8_6):
    m = mesh_at_angle(static_8_6, 0.0)
    r = quality_report(m)
    assert r.n_nodes == len(m.nodes) and r.n_triangles == len(m.triangles)
    assert sum(r.triangles_per_region.values()) == r.n_triangles
    assert r.triangles_per_region["moving_band"] == 2 * static_8_6.settings.band_divisions
    assert r.min_angle_deg >= static_8_6.settings.min_angle_deg
    assert r.max_aspect_ratio <= static_8_6.settings.max_aspect_ratio


def test_check_quality_lists_all_violations(static_8_6):
    r = quality_report(mesh_at_angle(static_8_6, 0.0))
    strict = dataclasses.replace(static_8_6.settings, min_angle_deg=59.0, band_min_angle_deg=59.0, max_aspect_ratio=1.01)
    with pytest.raises(MeshRejected) as info:
        check_quality(r, strict)
    assert len(info.value.reasons) == 3
    assert info.value.report is r


def test_build_machine_mesh_rejects_bad_quality():
    with pytest.raises(MeshRejected):
        build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening", min_angle_deg=59.0)))


def test_plot_writes_png(static_8_6, tmp_path):
    out = plot_mesh(mesh_at_angle(static_8_6, 0.1), tmp_path / "mesh.png", title="8/6 screening")
    assert out.exists() and out.stat().st_size > 10_000


def test_sharp_corners_mesh():
    s = build_machine_mesh(Design(machine=make_8_6(stator_fillet_radius=0.0, rotor_fillet_radius=0.0),
                                  mesh=MeshSettings(preset="screening")))
    assert len(mesh_at_angle(s, 0.0).triangles) > 0


def test_two_builds_in_one_process_are_identical(static_8_6):
    again = build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))
    assert np.array_equal(again.stator.nodes, static_8_6.stator.nodes)
    assert np.array_equal(again.rotor.triangles, static_8_6.rotor.triangles)
    assert again.region_names == static_8_6.region_names


@pytest.mark.slow
@pytest.mark.parametrize("factory", [make_12_8, make_24_16])
@pytest.mark.parametrize("preset", ["screening", "full"])
def test_other_reference_designs_mesh(factory, preset, tmp_path):
    s = build_machine_mesh(Design(machine=factory(), mesh=MeshSettings(preset=preset)))
    m = mesh_at_angle(s, 0.3 * s.settings.band_pitch)
    plot_mesh(m, tmp_path / f"{factory.__name__}_{preset}.png")
    check_quality(quality_report(m), s.settings)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/mesh/test_quality_plot.py -v -m "not slow"`
Expected: `ImportError: cannot import name 'build_machine_mesh' from 'srmcore.mesh'`.

- [ ] **Step 3: Implement the report and gate**

Append to `src/srmcore/mesh/quality.py` (add `from __future__ import annotations` as the first line of the file and the imports shown):
```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..model.errors import MeshRejected
from .settings import ResolvedMeshSettings

if TYPE_CHECKING:
    from .machine import MachineMesh


@dataclass(frozen=True)
class MeshQualityReport:
    n_nodes: int
    n_triangles: int
    min_angle_deg: float
    max_aspect_ratio: float
    band_min_angle_deg: float
    triangles_per_region: dict[str, int]


def quality_report(mesh: MachineMesh) -> MeshQualityReport:
    min_angle, aspect = triangle_quality(mesh.nodes, mesh.triangles)
    in_band = np.zeros(len(mesh.triangles), dtype=bool)
    in_band[mesh.band_rows] = True
    counts = np.bincount(mesh.region_ids, minlength=len(mesh.region_names))
    return MeshQualityReport(
        n_nodes=len(mesh.nodes), n_triangles=len(mesh.triangles),
        min_angle_deg=float(min_angle[~in_band].min()), max_aspect_ratio=float(aspect[~in_band].max()),
        band_min_angle_deg=float(min_angle[in_band].min()),
        triangles_per_region={name: int(counts[i]) for i, name in enumerate(mesh.region_names)},
    )


def check_quality(report: MeshQualityReport, settings: ResolvedMeshSettings) -> None:
    reasons = []
    if report.min_angle_deg < settings.min_angle_deg:
        reasons.append(f"min angle {report.min_angle_deg:.2f}° < {settings.min_angle_deg}°")
    if report.max_aspect_ratio > settings.max_aspect_ratio:
        reasons.append(f"aspect ratio {report.max_aspect_ratio:.2f} > {settings.max_aspect_ratio}")
    if report.band_min_angle_deg < settings.band_min_angle_deg:
        reasons.append(f"band min angle {report.band_min_angle_deg:.2f}° < {settings.band_min_angle_deg}°")
    if reasons:
        raise MeshRejected(reasons, report)
```
(`import numpy as np` is already at the top of the file.)

- [ ] **Step 4: Implement the plot and the entry point**

`src/srmcore/mesh/plot.py`:
```python
"""PNG plot of a machine mesh, coloured by region (backend-independent: no pyplot)."""
from pathlib import Path

from matplotlib.figure import Figure

from .machine import MachineMesh


def plot_mesh(mesh: MachineMesh, path: str | Path, title: str | None = None) -> Path:
    path = Path(path)
    fig = Figure(figsize=(8, 8))
    ax = fig.add_subplot()
    ax.tripcolor(mesh.nodes[:, 0], mesh.nodes[:, 1], mesh.triangles, facecolors=mesh.region_ids,
                 edgecolors="k", linewidth=0.05, cmap="tab20")
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(title or f"rotor angle {mesh.rotor_angle:.4f} rad, {len(mesh.triangles)} triangles")
    fig.savefig(path, dpi=200)
    return path
```

`src/srmcore/mesh/api.py`:
```python
"""Public entry point: validated, quality-gated static mesh."""
from ..model.design import Design
from .machine import mesh_at_angle
from .quality import check_quality, quality_report
from .static import StaticMesh, build_static_mesh


def build_machine_mesh(design: Design) -> StaticMesh:
    static = build_static_mesh(design)
    for theta in (0.0, static.settings.band_pitch / 2):
        check_quality(quality_report(mesh_at_angle(static, theta, check=False)), static.settings)
    return static
```

`src/srmcore/mesh/__init__.py`:
```python
from .api import build_machine_mesh
from .band import snap_angle
from .machine import MachineMesh, mesh_at_angle
from .plot import plot_mesh
from .quality import MeshQualityReport, check_quality, quality_report
from .static import StaticMesh

__all__ = ["build_machine_mesh", "snap_angle", "MachineMesh", "mesh_at_angle", "plot_mesh",
           "MeshQualityReport", "check_quality", "quality_report", "StaticMesh"]
```

- [ ] **Step 5: Run to verify pass (fast, then slow)**

Run: `python -m pytest tests/mesh/test_quality_plot.py -v -m "not slow"`
Expected: all pass.
Run: `python -m pytest tests/mesh/test_quality_plot.py -v -m slow`
Expected: 4 passed. Open one PNG from the pytest tmp dir and confirm by eye: poles, coils, slots and the air gap look right. If a `full` preset build fails the quality gate, report the numbers to the owner — preset values are provisional (spec §4.5) and changing them is an owner decision.

- [ ] **Step 6: Commit**

```bash
git add src/srmcore/mesh tests/mesh/test_quality_plot.py
git commit -m "feat(mesh): quality report and gate, mesh plot, build_machine_mesh entry point" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Property-based meshing tests over a bounded design box

**Files:**
- Test: `tests/mesh/test_property.py`

**Interfaces:**
- Consumes: `validate_params`, `build_outline` (via `build_machine_mesh`), `build_machine_mesh`, `mesh_at_angle`, `quality_report`, `InputError`.
- Produces: nothing new (tests only).

Property: **every design that passes validation and outline fit checks meshes, and the mesh is valid at an arbitrary rotor angle.** Designs rejected with `InputError` are legitimate rejections, not failures (`assume(False)`). Fast suite runs 5 examples; the `slow` variant runs 50.

- [ ] **Step 1: Write the tests**

`tests/mesh/test_property.py`:
```python
import math

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.errors import InputError
from srmcore.model.validator import validate_params
from srmcore.mesh import build_machine_mesh, mesh_at_angle, quality_report

TOPOLOGIES = [(6, 4, 3), (8, 6, 4), (12, 8, 3)]


@st.composite
def radial_designs(draw) -> RadialSRMParams:
    ns, nr, m = draw(st.sampled_from(TOPOLOGIES))
    rotor_od = draw(st.floats(0.05, 0.12))
    stator_od = rotor_od / draw(st.floats(0.5, 0.62))
    gap = draw(st.floats(0.00025, 0.0008))
    limit = 2 * math.pi / (m * nr)
    beta_s = draw(st.floats(1.02 * limit, 1.4 * limit))
    beta_r = draw(st.floats(beta_s, 1.6 * limit))
    return RadialSRMParams(
        n_stator_poles=ns, n_rotor_poles=nr, n_phases=m,
        stator_outer_diameter=stator_od, rotor_outer_diameter=rotor_od, air_gap=gap,
        stack_length=0.08, shaft_diameter=rotor_od * draw(st.floats(0.2, 0.35)),
        stator_pole_arc=beta_s, rotor_pole_arc=beta_r,
        stator_pole_taper=draw(st.floats(0.0, math.radians(5))),
        rotor_pole_taper=draw(st.floats(0.0, math.radians(5))),
        stator_yoke_thickness=stator_od * draw(st.floats(0.06, 0.1)),
        rotor_yoke_thickness=rotor_od * draw(st.floats(0.12, 0.2)),
        stator_fillet_radius=draw(st.sampled_from([0.0, 0.0005, 0.001])),
        rotor_fillet_radius=draw(st.sampled_from([0.0, 0.0005, 0.001])),
        turns_per_pole=40, fill_factor=0.5,
        slot_liner_thickness=0.0004, coil_inner_clearance=0.001,
    )


def _check(p: RadialSRMParams, theta_frac: float) -> None:
    assume(not any(i.severity == "error" for i in validate_params(p)))
    try:
        static = build_machine_mesh(Design(machine=p, mesh=MeshSettings(preset="screening")))
    except InputError:
        assume(False)
    m = mesh_at_angle(static, theta_frac * 2 * math.pi)
    tri = m.nodes[m.triangles]
    areas = 0.5 * ((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1])
                   - (tri[:, 2, 0] - tri[:, 0, 0]) * (tri[:, 1, 1] - tri[:, 0, 1]))
    assert np.all(areas > 0)
    assert areas.sum() == pytest.approx(math.pi * p.stator_outer_radius**2, rel=5e-3)
    assert len(static.stator_ring) == len(static.rotor_ring) == static.settings.band_divisions
    r = quality_report(m)
    assert r.band_min_angle_deg >= static.settings.band_min_angle_deg
    assert all(r.triangles_per_region[n] > 0 for n in m.region_names)


_COMMON = dict(deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])


@settings(max_examples=5, **_COMMON)
@given(radial_designs(), st.floats(0.0, 1.0))
def test_valid_designs_mesh_fast(p, theta_frac):
    _check(p, theta_frac)


@pytest.mark.slow
@settings(max_examples=50, **_COMMON)
@given(radial_designs(), st.floats(0.0, 1.0))
def test_valid_designs_mesh_many(p, theta_frac):
    _check(p, theta_frac)
```

- [ ] **Step 2: Run the fast property test**

Run: `python -m pytest tests/mesh/test_property.py -v -m "not slow"`
Expected: PASS. If Hypothesis reports a falsifying example, it is a real bug: reproduce it as a plain unit test in the module that owns the failure (topology, geometry or mesh), fix it there, and keep that test.

- [ ] **Step 3: Run the slow variant once**

Run: `python -m pytest tests/mesh/test_property.py -v -m slow`
Expected: PASS (a few minutes).

- [ ] **Step 4: Commit**

```bash
git add tests/mesh/test_property.py
git commit -m "test(mesh): property-based meshing over a bounded design box" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Reference-machine data audit

**Files:**
- Create: `docs/reference-machines.md`

**Interfaces:**
- Consumes: the PDF library in `D:\y\srm` (read-only) and the TEAM 24 page https://ngsolve.github.io/TEAM-problems/TEAM-24/team24.html.
- Produces: a decision record naming the validation machines for M5 (spec §2.3, §8.2 suite 5), or an escalation to the owner if none qualifies.

A machine **qualifies** only if the source gives all of: (a) every `RadialSRMParams` geometry field or enough dimensions to derive them, (b) a B-H curve (table or plot) for the lamination used, (c) measured flux linkage ψ(θ, i) and/or measured static torque T(θ, i) with stated currents. FEM-only curves do not satisfy (c).

- [ ] **Step 1: Create the audit document skeleton**

`docs/reference-machines.md`:
```markdown
# Reference machines for validation (M1 audit)

Criteria: (a) full geometry, (b) B-H data of the lamination, (c) MEASURED ψ(θ,i) and/or static T(θ,i).

| Candidate | Source file | Pages / figures | Topology | (a) geometry | (b) B-H | (c) measured ψ / T | Qualifies | Notes |
|---|---|---|---|---|---|---|---|---|
| TEAM Problem 24 | ngsolve.github.io TEAM-24 + original TEAM report | | SRM-like rig | | | | | voltage-step locked-rotor test; magnetostatic scope per spec §2.3 |
| Krishnan 8/6 design example | Switched Reluctance Motor Drives (Krishnan 2001) | | 8/6 | | | | | |
| Mak MASc thesis machine | Mak_Christopher_See-Hon_2020aug_MASc (1).pdf | | | | | | | |
| Azer PhD thesis machine | Azer_Peter_202006_PhD.pdf | | | | | | | |
| 24/16 traction SRM | THREE-PHASE 24 16 SWITCHED RELUCTANCE MACHINE ... .pdf | | 24/16 | | | | | |
| 24/16 NVH machine | Prediction of acoustic noise and vibration of a 24 16 traction switched reluctance machine.pdf | | 24/16 | | | | | |

## Decision

- 8/6 (or nearest) FEMM + measured reference: 
- 12/8 or 24/16 FEMM reference: 
- Measured-data SRM reference (beyond TEAM 24): 

## Parameter mapping for selected machines

(One `RadialSRMParams` table per selected machine: field, value in SI, source page, derived-or-stated.)
```

- [ ] **Step 2: Audit each candidate**

For each row, open the PDF and search for: dimension tables ("stator outer diameter", "air gap", "pole arc", "stack length"), magnetisation / B-H figures, and figures whose captions say "measured", "experimental" or "test" for flux linkage, inductance or static torque. Fill every cell with what was found and the page/figure number; write "not found" explicitly rather than leaving a cell empty. For TEAM 24 record which geometry and measured quantities are published (the NGSolve page links the original data).

- [ ] **Step 3: Record the decision and map parameters**

Fill the Decision section: pick the qualifying 8/6-class machine, the qualifying 12/8 or 24/16 machine, and at least one measured SRM reference. For each selected machine, write the full `RadialSRMParams` mapping table (values in metres/radians), marking each value "stated" or "derived (how)". If no SRM candidate satisfies (c), write that plainly under Decision and add it to spec §10 open items as a blocker for M5 that the owner must resolve (e.g. by locating another publication or planning a locked-rotor bench test).

- [ ] **Step 4: Commit**

```bash
git add docs/reference-machines.md
git commit -m "docs: audit of reference machines for validation" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## M1 exit check

- [ ] Run: `python -m pytest -m "not slow"` — all green, under 10 minutes.
- [ ] Run: `python -m pytest -m slow` — all green.
- [ ] Generate and look at mesh plots for 8/6 (screening and full) at angle 0 and at half a band pitch; attach them to the M1 review.
- [ ] `docs/reference-machines.md` has a Decision section filled in (or an explicit escalation).

## Notes and known risks (carry into the M2–M4 plans)

- **Air-gap element count.** Four isotropic layers across a 0.3–0.4 mm gap give roughly 20–50k triangles in the gap alone, even on the `screening` preset. That threatens the M4 speed budget (spec §7.2). The M4 plan must measure DOF per preset and, if needed, add structured (layered, anisotropic) gap meshing. The spec's "≥ 4 layers across the gap" requirement stays.
- **Preset numbers are provisional** (Task 7) until the M5 convergence study.
- **The Gmsh transfinite count convention** for closed curves is pinned by `test_band_rings_are_uniform` (Task 9), not by assumption.
- **Optional outer air ring** (spec §4.3, for yoke-saturation leakage) is not built in M1. It lands in the M2 plan together with the A = 0 boundary-condition choice, as a `stator_outer_air` region outside the stator OD.
- **Coil polarity** in region names follows the default alternating convention. The winding connection matrix (M2) is the authority on current direction; names are labels only.

