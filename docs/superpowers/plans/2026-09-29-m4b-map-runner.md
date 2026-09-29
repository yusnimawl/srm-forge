# M4b Map Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a ψ/T map of a design over an angle × current grid: grids and presets, a serial runner with the spec's failed-point policy, an HDF5 dataset with provenance hash and cache, and a process pool. Then measure a real `screening` map against its 30 s budget.

**Architecture:** `maps/grids.py` makes the grids. `maps/run.py` sweeps one excited circuit over the grid with `solve_point`, applies the failure policy and returns a frozen `MapResult`. `maps/dataset.py` hashes provenance and reads and writes HDF5 and the cache. `maps/pool.py` maps angle jobs over a stdlib `ProcessPoolExecutor` (spawn, one retry after a crash). `maps/api.py` `build_map` ties them together: cache lookup, then mesh, then run, then store. The parent builds the `StaticMesh` once and workers receive the arrays; workers never start a Gmsh session.

**Tech Stack:** numpy, scipy (PCHIP), h5py (new required dependency), stdlib `concurrent.futures`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` §7.2 (map generation, dataset, parallelism, cache, speed budget), §8.1 (error policy), §11 (decision log). Handoff: `docs/m4-handoff.md`.

## Decisions from the grilling rounds (owner-approved 2026-09-29)

- Pool first, then measure a real map before spending on speed (M4a left cold solves at 4.5–5.3 s against 4 s). If a real `screening` map exceeds 30 s, the first M4c item is structured air-gap meshing.
- M4b is 4 tasks: grids and presets; serial runner with error policy; HDF5 dataset with hash and cache; process pool with the public `build_map` and the measurement.
- Workers get the mesh from the parent (deviation from the spec's "one Gmsh session each"; record in §11).
- `h5py` is a required dependency (3.16 has cp314 wheels).
- No mirror reduction: the full rotor pole pitch is solved. The angle grid is denser near alignment; overlap-start clustering waits for M4c's held-out interpolation check.
- Current grid: I_max·(k/(n−1))², first point 0. Knee refinement waits for real maps.
- Failed points: interpolate NONCONVERGED points along current (PCHIP) and flag them. The map fails if more than 2 % of points fail, or any point at the aligned angle or at I_max fails. The overlap-window rule is M4c.
- Solver by name, default `ngsolve`, no silent fallback: a missing NGSolve raises a clear error. The provenance hash records solver name and version.
- One parallel task = one angle with all its currents. `ProcessPoolExecutor` with spawn; a `BrokenProcessPool` is retried once in a fresh pool, then `WorkerCrashed`. Cancel keeps partial results.
- `cache_dir` is an explicit argument with no global default; only complete maps are stored.

Decisions made while writing this plan (owner: confirm or overrule):
- **Excitation and layout:** a diagonal map excites one circuit (default `A`) and stores ψ of all circuits, so `psi[angle, current, circuit]` includes the mutual flux linkage into the unexcited circuits.
- **No continuation between currents:** M4a measured under 20 % iteration savings from warm starts, and independent points parallelise and fail independently.
- **Default worker count:** half of `os.cpu_count()` (assumes two hardware threads per physical core; `psutil` is not a dependency).

## Global Constraints

- Element order 1 and quadrature order 2 in every adapter. Newton tolerances stay as in `NewtonSettings`. Cross-solver agreement stays at 1e-4 (`tests/solvers/test_cross_solver.py` stays green).
- `skfem_reference.py`: additive changes only (the `version` attribute in Task 3).
- Import rules (`tests/test_import_rules.py`): `maps` may import model, materials, mesh, physics, solvers, post, fields. Only `solvers/` imports `ngsolve`, `netgen`, `skfem`. Only `geometry/` and `mesh/` import `gmsh`.
- SI units (rad, A, Wb-turns, N·m, J). Frozen dataclasses across layers.
- Python >= 3.12, numpy >= 2.0. Test file basenames unique (`tests/` has no `__init__.py`). Fast suite stays under 10 minutes (currently about 4); no wall-clock assertions; tests that run a real map use tiny grids.
- Comments explain the code as it is; no task or plan history.
- Leave the open owner decisions (`self_starting` rule, `MIN_WEB_WIDTH`) unchanged.
- Commit only after the owner approves. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

Failure modes the spec implies but no task would otherwise exercise, most likely first:

1. Failure-policy edges: exactly one failed point in a 64-point grid passes (1.6 %); a failure at the aligned angle or at I_max always fails the map; zero failures returns the arrays untouched (Task 2).
2. Cancellation: an incomplete result is never policy-filled and never stored in the cache; unrun points are marked NOT_RUN with NaN data (Tasks 2, 3).
3. Worker crash: the first crash is retried in a fresh pool and finished results are kept; a second crash raises `WorkerCrashed` (Task 4).
4. Cache keys: changing any design parameter, the grid, the excited circuit or the solver version changes the hash; a leftover `.tmp` file from an interrupted write is never read as a cache hit (Task 3).
5. Angle grid with a small `n` or a coarse band pitch: duplicates dropped, 0 always first, nothing at or beyond the rotor pole pitch (Task 1).

---

## File Structure

- Create: `src/srmcore/maps/grids.py`, `run.py`, `dataset.py`, `pool.py`, `api.py`
- Create: `src/srmcore/solvers/factory.py`
- Create: `tests/maps/test_grids.py`, `test_run.py`, `test_dataset.py`, `test_pool.py`, `test_build_map.py`
- Create: `examples/build_map_8_6.py`
- Modify: `src/srmcore/model/errors.py` (`MapFailed`, `WorkerCrashed`), `src/srmcore/maps/__init__.py` (export `build_map`, `MapResult`)
- Modify: `src/srmcore/solvers/settings.py`, `skfem_reference.py`, `ngsolve_adapter.py` (`version`), `pyproject.toml` (`h5py`)
- Modify: `CLAUDE.md`, spec §10/§11, `docs/m4-handoff.md`

---

### Task 1: Angle and current grids

**Files:**
- Create: `src/srmcore/maps/grids.py`
- Test: `tests/maps/test_grids.py`

**Interfaces:**
- Consumes: `snap_angle(theta, divisions) -> (angle, k)` from `srmcore.mesh`, `RadialSRMParams.n_rotor_poles`, `resolve_mesh_settings(machine, mesh_settings).band_divisions`.
- Produces: `GRID_SIZES: dict[str, tuple[int, int]]`; `angle_grid(machine, band_divisions, n, cluster=0.5) -> np.ndarray`; `current_grid(i_max, n, exponent=2.0) -> np.ndarray`.

- [ ] **Step 1: Write the failing tests** (`tests/maps/test_grids.py`)

```python
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.grids import GRID_SIZES, angle_grid, current_grid
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import MeshSettings

MACHINE = make_8_6()
TAU_R = 2 * math.pi / MACHINE.n_rotor_poles


def _divisions(preset):
    return resolve_mesh_settings(MACHINE, MeshSettings(preset=preset)).band_divisions


@pytest.mark.parametrize("preset", ["screening", "full"])
def test_angle_grid_is_sorted_on_the_band_grid_inside_one_pole_pitch(preset):
    divisions, n = _divisions(preset), GRID_SIZES[preset][0]
    a = angle_grid(MACHINE, divisions, n)
    pitch = 2 * math.pi / divisions
    assert a[0] == 0.0 and np.all(np.diff(a) > 0) and a[-1] < TAU_R - 1e-9
    assert len(a) <= n
    assert np.allclose(a / pitch, np.round(a / pitch), atol=1e-9)


def test_angle_grid_is_denser_near_alignment():
    a = angle_grid(MACHINE, _divisions("full"), 30)
    gaps = np.diff(a)
    assert gaps[:2].mean() <= gaps[len(gaps) // 2 - 1: len(gaps) // 2 + 1].mean()


def test_tiny_grid_and_coarse_band_pitch_drop_duplicates_but_keep_zero():
    a = angle_grid(MACHINE, band_divisions=MACHINE.n_rotor_poles * 2, n=30)   # 2 band steps per pole pitch
    assert list(a) == pytest.approx([0.0, TAU_R / 2])
    assert list(angle_grid(MACHINE, _divisions("screening"), 1)) == [0.0]


def test_current_grid_starts_at_zero_ends_at_i_max_and_is_denser_at_low_current():
    c = current_grid(20.0, 8)
    assert c[0] == 0.0 and c[-1] == 20.0 and np.all(np.diff(c) > 0)
    assert np.diff(c)[0] < np.diff(c)[-1]
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/maps/test_grids.py -v`; Expected: FAIL (`ModuleNotFoundError: srmcore.maps.grids`).

- [ ] **Step 3: Implement** `src/srmcore/maps/grids.py`

```python
"""Angle and current grids of a map (spec §7.2)."""
import math

import numpy as np

from ..mesh.band import snap_angle
from ..model.design import RadialSRMParams

# (angles, currents) per fidelity preset, following the mesh preset. Provisional until the M5 study.
GRID_SIZES = {"screening": (8, 8), "full": (30, 20), "reference": (60, 40)}


def angle_grid(machine: RadialSRMParams, band_divisions: int, n: int, cluster: float = 0.5) -> np.ndarray:
    """Up to n rotor angles over one rotor pole pitch [0, 2π/Nr), θ = 0 aligned, snapped to the band
    pitch. The warp θ = τ·(u − cluster·sin(2πu)/2π) is densest at alignment (spacing ratio between the
    unaligned and aligned ends is (1 + cluster)/(1 − cluster)). Snapping can merge neighbours, so fewer
    than n angles may come back."""
    tau = 2 * math.pi / machine.n_rotor_poles
    pitch = 2 * math.pi / band_divisions
    u = np.arange(n) / n
    theta = tau * (u - cluster * np.sin(2 * math.pi * u) / (2 * math.pi))
    steps = sorted({snap_angle(t, band_divisions)[1] for t in theta})
    return np.array([k * pitch for k in steps if k * pitch < tau - 1e-9])


def current_grid(i_max: float, n: int, exponent: float = 2.0) -> np.ndarray:
    """n currents from 0 to i_max, denser at low current: i_max·(k/(n−1))^exponent."""
    return i_max * (np.arange(n) / (n - 1)) ** exponent
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/maps/test_grids.py tests/test_import_rules.py -v`; Expected: PASS. If the coarse-pitch test finds a different count, print the grid and report before changing the test.

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/maps/grids.py tests/maps/test_grids.py
git commit -m "feat(maps): angle and current grids for a map"
```

---

### Task 2: Serial runner, `MapResult` and the failed-point policy

**Files:**
- Create: `src/srmcore/maps/run.py`, `src/srmcore/solvers/factory.py`
- Modify: `src/srmcore/model/errors.py` (add `MapFailed`)
- Test: `tests/maps/test_run.py`

**Interfaces:**
- Consumes: `solve_point(static, design, angle, currents, solver, initial=None, keep_field=False) -> PointResult` (`srmcore.maps.point`), `SolveStatus`.
- Produces:
  - `make_solver(name: str) -> SolverAdapter` (`srmcore.solvers.factory`): `"ngsolve"` or `"skfem_reference"`; anything else `ValueError`; a missing NGSolve raises `ImportError` mentioning `srmcore[ngsolve]`.
  - `MapFailed(RuntimeError)` with `.reasons: list[str]` and `.n_failed: int` (`srmcore.model.errors`).
  - `MapResult` (frozen, `eq=False`): `angles (n_a,)`, `currents (n_i,)`, `circuits: tuple[str, ...]`, `excited: str`, `psi (n_a, n_i, n_c)`, `torque_arkkio`, `torque_virtual_work`, `coenergy` `(n_a, n_i)`, `iterations int (n_a, n_i)`, `status int8 (n_a, n_i)` with codes `STATUS_OK = 0`, `STATUS_FALLBACK = 1`, `STATUS_NONCONVERGED = 2`, `STATUS_NOT_RUN = -1`, `filled bool (n_a, n_i)`, `complete: bool`.
  - `solve_angle(static, design, solver, angle, currents, excited) -> dict[str, np.ndarray]` with keys `psi, torque_arkkio, torque_virtual_work, coenergy, iterations, status` (one row each).
  - `apply_failure_policy(result) -> MapResult`.
  - `run_map(static, design, angles, currents, solver_name="ngsolve", excited="A", progress=None, cancel=None) -> MapResult`: `progress(done, total)` after each angle; `cancel() -> bool` checked before each angle.

- [ ] **Step 1: Write the failing tests** (`tests/maps/test_run.py`)

```python
"""Serial map runner: layout, failed-point policy, cancellation. Solves are faked except in the last test."""
import numpy as np
import pytest

from conftest import make_8_6
from srmcore.fields.solution import SolveStatus
from srmcore.maps import run
from srmcore.maps.point import PointResult, solve_point
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MapFailed

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
CIRCUITS = ("A", "B", "C", "D")
ANGLES = np.arange(8) * 0.01
CURRENTS = np.arange(8) * 2.5          # 64 points: one failure is 1.6 %, two are 3.1 %


def _fake(monkeypatch, failing=()):
    """solve_point stand-in, linear in current so PCHIP reproduces it exactly; `failing` is a set of
    (angle index, current index) that come back NONCONVERGED with garbage values."""
    bad = {(round(float(ANGLES[a]), 9), round(float(CURRENTS[i]), 9)) for a, i in failing}

    def fake(static, design, angle, currents, solver, **kw):
        amps = currents["A"]
        failed = (round(angle, 9), round(amps, 9)) in bad
        psi = np.array([0.01 * (1 + angle) * amps, 0.0, 0.0, 0.0])
        return PointResult(
            angle=angle, circuits=CIRCUITS, currents=np.array([amps, 0.0, 0.0, 0.0]),
            psi=np.full(4, 1e9) if failed else psi, torque_arkkio=1e9 if failed else 0.5 * amps,
            torque_virtual_work=0.5 * amps, coenergy=0.3 * amps,
            status=SolveStatus.NONCONVERGED if failed else SolveStatus.OK,
            iterations=3, fallbacks=(), load_fraction=1.0)

    monkeypatch.setattr(run, "solve_point", fake)
    monkeypatch.setattr(run, "make_solver", lambda *a, **k: object())


def _run(**kw):
    return run.run_map(None, DESIGN, ANGLES, CURRENTS, **kw)


def test_layout_and_no_failures(monkeypatch):
    _fake(monkeypatch)
    r = _run()
    assert r.psi.shape == (8, 8, 4) and r.torque_arkkio.shape == (8, 8)
    assert r.circuits == CIRCUITS and r.excited == "A" and r.complete
    assert np.all(r.status == run.STATUS_OK) and not r.filled.any()
    assert np.allclose(r.psi[3, 5, 0], 0.01 * (1 + ANGLES[3]) * CURRENTS[5])


def test_one_interior_failure_is_interpolated_and_flagged(monkeypatch):
    _fake(monkeypatch, failing={(2, 3)})
    r = _run()
    assert r.filled[2, 3] and r.filled.sum() == 1 and r.status[2, 3] == run.STATUS_NONCONVERGED
    assert r.psi[2, 3, 0] == pytest.approx(0.01 * (1 + ANGLES[2]) * CURRENTS[3], rel=1e-9)
    assert r.torque_arkkio[2, 3] == pytest.approx(0.5 * CURRENTS[3], rel=1e-9)


@pytest.mark.parametrize("failing, reason", [
    ({(0, 3)}, "aligned"), ({(4, 7)}, "I_max"), ({(2, 2), (3, 3)}, "2 %")])
def test_map_fails_on_the_policy_conditions(monkeypatch, failing, reason):
    _fake(monkeypatch, failing=failing)
    with pytest.raises(MapFailed) as e:
        _run()
    assert any(reason in r for r in e.value.reasons) and e.value.n_failed == len(failing)


def test_cancel_keeps_partial_results_unfilled(monkeypatch):
    _fake(monkeypatch, failing={(0, 3)})           # would fail the policy if it were applied
    calls = []
    r = _run(cancel=lambda: len(calls) >= 3, progress=lambda done, total: calls.append(done))
    assert not r.complete and calls == [1, 2, 3]
    assert np.all(r.status[3:] == run.STATUS_NOT_RUN) and np.isnan(r.psi[3:]).all()
    assert np.all(r.status[:3] != run.STATUS_NOT_RUN)


def test_unknown_excited_circuit_is_rejected(monkeypatch):
    _fake(monkeypatch)
    with pytest.raises(ValueError, match="excited"):
        _run(excited="Z")


def test_real_solves_match_solve_point():
    static = build_machine_mesh(DESIGN)
    pitch = static.settings.band_pitch
    angles, currents = np.array([0.0, 2 * pitch]), np.array([0.0, 5.0])
    r = run.run_map(static, DESIGN, angles, currents, solver_name="skfem_reference")
    solver = run.make_solver("skfem_reference")
    direct = solve_point(static, DESIGN, angles[1], {"A": 5.0}, solver)
    assert r.circuits == direct.circuits
    assert np.allclose(r.psi[1, 1], direct.psi, rtol=1e-9)
    assert r.torque_arkkio[1, 1] == pytest.approx(direct.torque_arkkio, rel=1e-9)
    assert np.all(r.psi[:, 0] == 0.0)
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/maps/test_run.py -v`; Expected: FAIL (`cannot import name 'MapFailed'` / no module `srmcore.maps.run`).

- [ ] **Step 3: Implement.** Read `model/errors.py` and follow its style.

`model/errors.py`, add:

```python
class MapFailed(RuntimeError):
    """A map violates the failed-point policy (spec §8.1)."""

    def __init__(self, reasons: list[str], n_failed: int):
        self.reasons = list(reasons)
        self.n_failed = n_failed
        super().__init__("Map failed: " + "; ".join(self.reasons))
```

`solvers/factory.py`:

```python
"""Solver adapters by name, so a worker process can build its own."""
from .settings import SolverAdapter


def make_solver(name: str) -> SolverAdapter:
    if name == "ngsolve":
        try:
            from .ngsolve_adapter import NgsolveAdapter
        except ImportError as e:
            raise ImportError("the 'ngsolve' solver needs the optional extra: pip install srmcore[ngsolve]") from e
        return NgsolveAdapter()
    if name == "skfem_reference":
        from .skfem_reference import SkfemReference
        return SkfemReference()
    raise ValueError(f"unknown solver {name!r}; choose 'ngsolve' or 'skfem_reference'")
```

`maps/run.py`:

```python
"""Serial map runner: one excited circuit swept over an angle × current grid (spec §7.2, §8.1).

Every point is an independent solve from A = 0. Warm starts from the neighbouring current saved under
20 % of the Newton iterations on the 8/6, so points stay independent and parallelise per angle."""
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from ..fields.solution import SolveStatus
from ..model.design import Design
from ..model.errors import MapFailed
from ..solvers.factory import make_solver
from ..solvers.settings import SolverAdapter
from .point import solve_point

STATUS_OK, STATUS_FALLBACK, STATUS_NONCONVERGED, STATUS_NOT_RUN = 0, 1, 2, -1
_CODE = {SolveStatus.OK: STATUS_OK, SolveStatus.OK_WITH_FALLBACK: STATUS_FALLBACK,
         SolveStatus.NONCONVERGED: STATUS_NONCONVERGED}
# Spec §8.1: the map fails when more than this fraction of its points fail.
MAX_FAILED_FRACTION = 0.02
_FIELDS = ("psi", "torque_arkkio", "torque_virtual_work", "coenergy")


@dataclass(frozen=True, eq=False)
class MapResult:
    """ψ and torque of a design with `excited` carrying the current and the other circuits open; ψ holds
    every circuit's flux linkage. `status` uses the STATUS_* codes; `filled` marks points replaced by
    interpolation; unrun points (cancelled map) are STATUS_NOT_RUN with NaN data."""
    angles: np.ndarray                 # rad, θ = 0 aligned
    currents: np.ndarray               # A in the excited circuit
    circuits: tuple[str, ...]
    excited: str
    psi: np.ndarray                    # (n_angles, n_currents, n_circuits), Wb-turns
    torque_arkkio: np.ndarray          # (n_angles, n_currents), N·m
    torque_virtual_work: np.ndarray
    coenergy: np.ndarray               # J
    iterations: np.ndarray
    status: np.ndarray
    filled: np.ndarray
    complete: bool


def solve_angle(static, design: Design, solver: SolverAdapter, angle: float, currents,
                excited: str) -> dict[str, np.ndarray]:
    """All currents at one angle: one array per MapResult field, first axis over currents."""
    points = [solve_point(static, design, angle, {excited: float(i)}, solver) for i in currents]
    return {
        "psi": np.array([p.psi for p in points]),
        "torque_arkkio": np.array([p.torque_arkkio for p in points]),
        "torque_virtual_work": np.array([p.torque_virtual_work for p in points]),
        "coenergy": np.array([p.coenergy for p in points]),
        "iterations": np.array([p.iterations for p in points]),
        "status": np.array([_CODE[p.status] for p in points], dtype=np.int8),
    }


def apply_failure_policy(result: MapResult) -> MapResult:
    """Interpolate isolated NONCONVERGED points along current (PCHIP) and flag them, or raise MapFailed
    when more than 2 % of the points fail or the aligned angle or I_max has a failure."""
    failed = result.status == STATUS_NONCONVERGED
    n_failed = int(failed.sum())
    if n_failed == 0:
        return result
    reasons = []
    if n_failed / failed.size > MAX_FAILED_FRACTION:
        reasons.append(f"{n_failed} of {failed.size} points failed (limit 2 %)")
    if failed[result.angles == 0.0].any():
        reasons.append("a point at the aligned position failed")
    if failed[:, -1].any():
        reasons.append("a point at I_max failed")
    if reasons:
        raise MapFailed(reasons, n_failed)
    data = {name: getattr(result, name).copy() for name in _FIELDS}
    for a in np.flatnonzero(failed.any(axis=1)):
        good, bad = ~failed[a], failed[a]
        for values in data.values():
            values[a][bad] = PchipInterpolator(result.currents[good], values[a][good], axis=0)(result.currents[bad])
    return dataclasses.replace(result, **data, filled=failed.copy())


def run_map(static, design: Design, angles: np.ndarray, currents: np.ndarray, solver_name: str = "ngsolve",
            excited: str = "A", progress: Callable[[int, int], None] | None = None,
            cancel: Callable[[], bool] | None = None) -> MapResult:
    solver = make_solver(solver_name)
    circuits = tuple(chr(ord("A") + k) for k in range(design.machine.n_phases))
    if excited not in circuits:
        raise ValueError(f"excited circuit {excited!r} is not one of {circuits}")
    n_a, n_i = len(angles), len(currents)
    data = {name: np.full((n_a, n_i, len(circuits)) if name == "psi" else (n_a, n_i), np.nan) for name in _FIELDS}
    iterations = np.zeros((n_a, n_i), dtype=np.int32)
    status = np.full((n_a, n_i), STATUS_NOT_RUN, dtype=np.int8)
    complete = True
    for a, angle in enumerate(angles):
        if cancel is not None and cancel():
            complete = False
            break
        row = solve_angle(static, design, solver, float(angle), currents, excited)
        for name in _FIELDS:
            data[name][a] = row[name]
        iterations[a], status[a] = row["iterations"], row["status"]
        if progress is not None:
            progress(a + 1, n_a)
    result = MapResult(np.asarray(angles, float), np.asarray(currents, float), circuits, excited,
                       **data, iterations=iterations, status=status,
                       filled=np.zeros((n_a, n_i), dtype=bool), complete=complete)
    return apply_failure_policy(result) if complete else result
```

Update the `SolverAdapter` import in `run.py` if it goes unused after Task 4; keep imports honest.

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/maps tests/test_import_rules.py -v`; Expected: PASS (the real-solve test builds a screening mesh, about 8 s, plus two solves).

- [ ] **Step 5: Commit**

```bash
git add src/srmcore/maps/run.py src/srmcore/solvers/factory.py src/srmcore/model/errors.py tests/maps/test_run.py
git commit -m "feat(maps): serial map runner with the failed-point policy"
```

---

### Task 3: HDF5 dataset, provenance hash and cache

**Files:**
- Create: `src/srmcore/maps/dataset.py`
- Modify: `pyproject.toml` (`"h5py>=3.10"` in `dependencies`), `src/srmcore/solvers/settings.py` (`SolverAdapter.version: str`), `skfem_reference.py` (`version = skfem.__version__`), `ngsolve_adapter.py` (`version = ng.__version__`)
- Test: `tests/maps/test_dataset.py`

**Interfaces:**
- Consumes: `MapResult` (Task 2), `Design.to_json()`, `SolverAdapter.name`.
- Produces:
  - `provenance(design, angles, currents, excited, solver) -> dict` (JSON-serialisable).
  - `provenance_hash(prov: dict) -> str` (16 hex chars).
  - `write_map(path, result, prov)` (atomic: writes `<path>.tmp`, then `os.replace`), `read_map(path) -> tuple[MapResult, dict]`.
  - `cached_map(cache_dir, prov) -> MapResult | None`; `store_map(cache_dir, result, prov) -> Path | None` (None when the result is incomplete).

- [ ] **Step 1: Write the failing tests** (`tests/maps/test_dataset.py`)

```python
import dataclasses
import json

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps import dataset
from srmcore.maps.run import STATUS_OK, MapResult
from srmcore.model.design import Design, MeshSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
ANGLES, CURRENTS = np.array([0.0, 0.01, 0.02]), np.array([0.0, 5.0])
SOLVER = SkfemReference()


def _result(complete=True):
    rng = np.random.default_rng(0)
    return MapResult(
        ANGLES, CURRENTS, ("A", "B", "C", "D"), "A", rng.random((3, 2, 4)), rng.random((3, 2)),
        rng.random((3, 2)), rng.random((3, 2)), np.full((3, 2), 7, dtype=np.int32),
        np.full((3, 2), STATUS_OK, dtype=np.int8), np.zeros((3, 2), dtype=bool), complete)


def _prov(design=DESIGN, angles=ANGLES, currents=CURRENTS, excited="A", solver=SOLVER):
    return dataset.provenance(design, angles, currents, excited, solver)


def test_write_read_round_trip(tmp_path):
    r, prov = _result(), _prov()
    dataset.write_map(tmp_path / "m.h5", r, prov)
    back, back_prov = dataset.read_map(tmp_path / "m.h5")
    for f in dataclasses.fields(MapResult):
        a, b = getattr(r, f.name), getattr(back, f.name)
        assert np.array_equal(a, b) if isinstance(a, np.ndarray) else a == b
    assert back_prov == prov and not list(tmp_path.glob("*.tmp"))


def test_hash_changes_with_every_input():
    base = dataset.provenance_hash(_prov())
    assert base == dataset.provenance_hash(_prov())
    other_design = Design(machine=make_8_6(air_gap=0.0005), mesh=MeshSettings(preset="screening"))
    variants = [_prov(design=other_design), _prov(angles=ANGLES[:2]), _prov(currents=CURRENTS * 2),
                _prov(excited="B")]
    stale = _prov()
    stale["solver_version"] = "0.0.0"
    variants.append(stale)
    assert len({base, *(dataset.provenance_hash(p) for p in variants)}) == 1 + len(variants)


def test_cache_only_holds_complete_maps(tmp_path):
    prov = _prov()
    assert dataset.cached_map(tmp_path, prov) is None
    assert dataset.store_map(tmp_path, _result(complete=False), prov) is None
    assert dataset.cached_map(tmp_path, prov) is None
    path = dataset.store_map(tmp_path, _result(), prov)
    assert path.exists() and dataset.cached_map(tmp_path, prov) is not None
    assert dataset.cached_map(tmp_path, _prov(excited="B")) is None


def test_interrupted_write_is_never_a_hit(tmp_path):
    prov = _prov()
    (tmp_path / f"map_{dataset.provenance_hash(prov)}.h5.tmp").write_bytes(b"partial")
    assert dataset.cached_map(tmp_path, prov) is None


def test_corrupt_or_mismatched_cache_file_is_a_miss(tmp_path):
    prov = _prov()
    path = tmp_path / f"map_{dataset.provenance_hash(prov)}.h5"
    path.write_bytes(b"not hdf5")
    assert dataset.cached_map(tmp_path, prov) is None


def test_provenance_is_json_serialisable():
    json.dumps(_prov(), sort_keys=True)
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/maps/test_dataset.py -v`; Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`pyproject.toml`: add `"h5py>=3.10",` to `dependencies`. Run `python -m pip install -e ".[dev,ngsolve]"` to pick it up.

`solvers/settings.py`: in `SolverAdapter` add `version: str` next to `name: str`. In `skfem_reference.py`: `import skfem` and class attribute `version = skfem.__version__` on `SkfemReference` (additive). In `ngsolve_adapter.py`: class attribute `version = ng.__version__` on `NgsolveAdapter`.

`maps/dataset.py`:

```python
"""Map dataset: provenance hash, HDF5 file with labelled axes, and the complete-maps-only cache (spec §7.2)."""
import hashlib
import json
import os
from importlib.metadata import version
from pathlib import Path

import h5py
import numpy as np

from ..model.design import Design
from ..solvers.settings import SolverAdapter
from .run import MapResult

_DIMS = {"angles": ("angle",), "currents": ("current",), "psi": ("angle", "current", "circuit"),
         "torque_arkkio": ("angle", "current"), "torque_virtual_work": ("angle", "current"),
         "coenergy": ("angle", "current"), "iterations": ("angle", "current"),
         "status": ("angle", "current"), "filled": ("angle", "current")}


def provenance(design: Design, angles: np.ndarray, currents: np.ndarray, excited: str,
               solver: SolverAdapter) -> dict:
    """Everything that decides the numbers in a map. The design JSON covers geometry, mesh and materials."""
    return {"srmcore": version("srmcore"), "design": json.loads(design.to_json()),
            "angles": np.asarray(angles, float).tolist(), "currents": np.asarray(currents, float).tolist(),
            "excited": excited, "solver": solver.name, "solver_version": solver.version}


def provenance_hash(prov: dict) -> str:
    return hashlib.sha256(json.dumps(prov, sort_keys=True).encode()).hexdigest()[:16]


def write_map(path, result: MapResult, prov: dict) -> None:
    """Write via a temporary file and rename, so a reader never sees a half-written map."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with h5py.File(tmp, "w") as f:
        for name, dims in _DIMS.items():
            f.create_dataset(name, data=getattr(result, name)).attrs["dims"] = list(dims)
        f.create_dataset("circuits", data=np.array(result.circuits, dtype="S"))
        f.attrs.update(excited=result.excited, complete=result.complete,
                       provenance=json.dumps(prov, sort_keys=True), hash=provenance_hash(prov))
    os.replace(tmp, path)


def read_map(path) -> tuple[MapResult, dict]:
    with h5py.File(path, "r") as f:
        arrays = {name: f[name][()] for name in _DIMS}
        circuits = tuple(c.decode() for c in f["circuits"][()])
        result = MapResult(**arrays, circuits=circuits, excited=str(f.attrs["excited"]),
                           complete=bool(f.attrs["complete"]))
        return result, json.loads(f.attrs["provenance"])


def _path(cache_dir, prov: dict) -> Path:
    return Path(cache_dir) / f"map_{provenance_hash(prov)}.h5"


def cached_map(cache_dir, prov: dict) -> MapResult | None:
    """The stored map for this provenance, or None if absent, unreadable, incomplete or for other provenance."""
    path = _path(cache_dir, prov)
    if not path.exists():
        return None
    try:
        result, stored = read_map(path)
    except OSError:
        return None
    return result if result.complete and stored == prov else None


def store_map(cache_dir, result: MapResult, prov: dict) -> Path | None:
    """Only complete maps are cached."""
    if not result.complete:
        return None
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    path = _path(cache_dir, prov)
    write_map(path, result, prov)
    return path
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/maps tests/solvers tests/test_import_rules.py -q -m "not slow"`; Expected: PASS. If `provenance` equality after the JSON round trip fails on floats or tuples, fix by normalising in `provenance`, not by loosening the test.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/srmcore/maps/dataset.py src/srmcore/solvers tests/maps/test_dataset.py
git commit -m "feat(maps): HDF5 map dataset, provenance hash and cache"
```

---

### Task 4: Process pool, `build_map`, and the real-map measurement

**Files:**
- Create: `src/srmcore/maps/pool.py`, `src/srmcore/maps/api.py`, `examples/build_map_8_6.py`
- Modify: `src/srmcore/maps/run.py` (use `map_ordered`; add `workers`), `src/srmcore/maps/__init__.py`, `src/srmcore/solvers/factory.py` (`threads`), `src/srmcore/solvers/ngsolve_adapter.py` (thread pinning hook if needed), `src/srmcore/model/errors.py` (`WorkerCrashed`)
- Modify docs: `CLAUDE.md`, spec §10/§11, `docs/m4-handoff.md`
- Test: `tests/maps/test_pool.py`, `tests/maps/test_build_map.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces:
  - `WorkerCrashed(RuntimeError)` with `.items: list[int]`.
  - `map_ordered(fn, items, *, workers=1, initializer=None, initargs=(), cancel=None, progress=None) -> list`: results in item order, `None` for items not run (cancel). `workers <= 1` runs in-process. Otherwise a spawn `ProcessPoolExecutor`; a `BrokenProcessPool` re-runs the unfinished items once in a fresh pool, a second one raises `WorkerCrashed`.
  - `make_solver(name, threads=None)`: with `threads` and NGSolve, pins `ngsolve.SetNumThreads(threads)`.
  - `run_map(..., workers=1)`: same as Task 2 plus `workers`; results identical to serial.
  - `build_map(design, i_max, *, solver="ngsolve", excited="A", workers=None, n_angles=None, n_currents=None, cache_dir=None, progress=None, cancel=None) -> MapResult`; `workers=None` means `max(1, (os.cpu_count() or 2) // 2)`.

- [ ] **Step 1: Write the failing tests**

`tests/maps/test_pool.py`:

```python
import os

import pytest

from srmcore.maps.pool import map_ordered
from srmcore.model.errors import WorkerCrashed


def test_results_keep_item_order_in_process_and_in_a_pool():
    assert map_ordered(abs, [-1, -2, -3]) == [1, 2, 3]
    assert map_ordered(abs, [-1, -2, -3, -4], workers=2) == [1, 2, 3, 4]


def test_cancel_returns_none_for_unrun_items():
    seen = []
    out = map_ordered(abs, [-1, -2, -3], cancel=lambda: len(seen) >= 1, progress=lambda d, t: seen.append(d))
    assert out == [1, None, None]


def test_a_crashing_worker_is_retried_once_then_reported():
    with pytest.raises(WorkerCrashed) as e:
        map_ordered(os._exit, [1], workers=2)
    assert e.value.items == [0]
```

`tests/maps/test_build_map.py`:

```python
import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps import api
from srmcore.maps.run import run_map
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


def test_pool_result_equals_serial_result():
    static = build_machine_mesh(DESIGN)
    angles, currents = np.array([0.0, 2 * static.settings.band_pitch]), np.array([0.0, 5.0])
    serial = run_map(static, DESIGN, angles, currents, solver_name="skfem_reference", workers=1)
    pooled = run_map(static, DESIGN, angles, currents, solver_name="skfem_reference", workers=2)
    assert np.allclose(pooled.psi, serial.psi, rtol=1e-9, atol=1e-15)
    assert np.allclose(pooled.torque_arkkio, serial.torque_arkkio, rtol=1e-9, atol=1e-15)
    assert np.array_equal(pooled.status, serial.status)


def test_second_call_is_served_from_the_cache_without_meshing(tmp_path, monkeypatch):
    kw = dict(i_max=5.0, solver="skfem_reference", n_angles=2, n_currents=2, cache_dir=tmp_path, workers=1)
    first = api.build_map(DESIGN, **kw)
    monkeypatch.setattr(api, "build_machine_mesh", lambda d: pytest.fail("meshed on a cache hit"))
    second = api.build_map(DESIGN, **kw)
    assert np.array_equal(first.psi, second.psi) and second.complete
    assert len(list(tmp_path.glob("map_*.h5"))) == 1


def test_cancelled_map_is_not_cached(tmp_path):
    r = api.build_map(DESIGN, 5.0, solver="skfem_reference", n_angles=2, n_currents=2, cache_dir=tmp_path,
                      workers=1, cancel=lambda: True)
    assert not r.complete and not list(tmp_path.glob("map_*.h5"))


def test_excited_circuit_must_exist():
    with pytest.raises(ValueError, match="excited"):
        api.build_map(DESIGN, 5.0, solver="skfem_reference", excited="Z", n_angles=2, n_currents=2)
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/maps/test_pool.py tests/maps/test_build_map.py -v`; Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

`model/errors.py`, add:

```python
class WorkerCrashed(RuntimeError):
    """A pool worker died twice on the same items (spec §8.1)."""

    def __init__(self, items: list[int]):
        self.items = list(items)
        super().__init__(f"worker process crashed twice on items {self.items}")
```

`maps/pool.py`:

```python
"""Ordered map over a process pool with one retry after a worker crash (spec §7.2, §8.1)."""
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context

from ..model.errors import WorkerCrashed

# Each worker runs single-threaded numerics; the pool supplies the parallelism. Children read these at
# spawn time, so they stay set for the life of the process.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")


def _pass(fn, items, results, pending, workers, initializer, initargs, cancel, progress) -> None:
    with ProcessPoolExecutor(workers, mp_context=get_context("spawn"), initializer=initializer,
                             initargs=initargs) as pool:
        futures = {pool.submit(fn, items[k]): k for k in pending}
        for future in as_completed(futures):
            k = futures[future]
            results[k] = future.result()             # raises BrokenProcessPool if a worker died
            pending.remove(k)
            if progress is not None:
                progress(len(items) - len(pending), len(items))
            if cancel is not None and cancel():
                pool.shutdown(wait=True, cancel_futures=True)
                pending.clear()
                return


def map_ordered(fn: Callable, items: Iterable, *, workers: int = 1, initializer: Callable | None = None,
                initargs: tuple = (), cancel: Callable[[], bool] | None = None,
                progress: Callable[[int, int], None] | None = None) -> list:
    """fn over items, results in item order, None for items not run because `cancel` fired. `workers <= 1`
    runs in this process. A worker crash re-runs the unfinished items once in a fresh pool; a second crash
    raises WorkerCrashed."""
    items = list(items)
    results: list = [None] * len(items)
    if workers <= 1:
        if initializer is not None:
            initializer(*initargs)
        for k, item in enumerate(items):
            if cancel is not None and cancel():
                break
            results[k] = fn(item)
            if progress is not None:
                progress(k + 1, len(items))
        return results
    pending = list(range(len(items)))
    for attempt in range(2):
        try:
            _pass(fn, items, results, pending, workers, initializer, initargs, cancel, progress)
            return results
        except BrokenProcessPool:
            if attempt == 1:
                raise WorkerCrashed(sorted(pending)) from None
    raise AssertionError("unreachable")
```

`solvers/factory.py`: `make_solver(name, threads=None)`; in the `ngsolve` branch, after building the adapter: `if threads is not None: import ngsolve; ngsolve.SetNumThreads(threads)` (the import stays inside `solvers/`). Check `NgsolveAdapter`'s tests still pass.

`maps/run.py`: replace the serial loop in `run_map` with `map_ordered`. Module-level worker state:

```python
_WORKER: dict = {}


def _init_worker(static, design, solver_name, threads) -> None:
    _WORKER.update(static=static, design=design, solver=make_solver(solver_name, threads), )


def _solve_job(job):
    angle, currents, excited = job
    return solve_angle(_WORKER["static"], _WORKER["design"], _WORKER["solver"], angle, currents, excited)
```

`run_map(..., workers: int = 1, ...)`: validate `excited` as before, build `jobs = [(float(a), currents, excited) for a in angles]`, call

```python
rows = map_ordered(_solve_job, jobs, workers=workers, initializer=_init_worker,
                   initargs=(static, design, solver_name, 1 if workers > 1 else None),
                   cancel=cancel, progress=progress)
```

then fill the arrays from the non-None rows and set `complete = all(row is not None for row in rows)`. Remove the now-unused `make_solver` call and `SolverAdapter` import if nothing else needs them, but keep `make_solver` imported by name in `run.py` only if the Task 2 tests still monkeypatch it: update those tests to patch `run._init_worker` or `run.make_solver` consistently (the tests must still pass without loosening any assertion).

`maps/api.py`:

```python
"""Public entry: a map of a design, from cache or by solving (spec §7.2)."""
import os
from collections.abc import Callable

import numpy as np

from ..mesh import build_machine_mesh
from ..mesh.settings import resolve_mesh_settings
from ..model.design import Design
from ..solvers.factory import make_solver
from .dataset import cached_map, provenance, store_map
from .grids import GRID_SIZES, angle_grid, current_grid
from .run import MapResult, run_map


def build_map(design: Design, i_max: float, *, solver: str = "ngsolve", excited: str = "A",
              workers: int | None = None, n_angles: int | None = None, n_currents: int | None = None,
              cache_dir=None, progress: Callable[[int, int], None] | None = None,
              cancel: Callable[[], bool] | None = None) -> MapResult:
    """ψ and torque of `design` over an angle × current grid with `excited` carrying the current. Grid sizes
    default to the design's fidelity preset. A complete map is stored in and served from `cache_dir`."""
    adapter = make_solver(solver)
    circuits = [chr(ord("A") + k) for k in range(design.machine.n_phases)]
    if excited not in circuits:
        raise ValueError(f"excited circuit {excited!r} is not one of {circuits}")
    default_a, default_i = GRID_SIZES[design.mesh.preset]
    divisions = resolve_mesh_settings(design.machine, design.mesh).band_divisions
    angles = angle_grid(design.machine, divisions, n_angles or default_a)
    currents = current_grid(i_max, n_currents or default_i)
    prov = provenance(design, angles, currents, excited, adapter)
    if cache_dir is not None and (hit := cached_map(cache_dir, prov)) is not None:
        return hit
    # ponytail: half the logical CPUs stands in for the physical core count; psutil is not a dependency.
    workers = workers if workers is not None else max(1, (os.cpu_count() or 2) // 2)
    result = run_map(build_machine_mesh(design), design, angles, currents, solver_name=solver, excited=excited,
                     workers=workers, progress=progress, cancel=cancel)
    if cache_dir is not None:
        store_map(cache_dir, result, prov)
    return result
```

`maps/__init__.py`: `from .api import build_map` and `from .run import MapResult`, with `__all__`.

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/maps tests/solvers tests/test_import_rules.py -q -m "not slow"`; Expected: PASS. Then the full fast suite: `python -m pytest -m "not slow" -q` (must stay under 10 minutes).

- [ ] **Step 5: Measure a real map (the M4b speed check).** Create `examples/build_map_8_6.py`: builds the 8/6 `screening` map with `i_max = 20 A`, `workers` from `argv[1]` (default `None`), solver from `argv[2]` (default `ngsolve`), a progress line per angle, and prints elapsed time (mesh build reported separately), the status counts, the number of filled points, the peak torque, and the aligned-to-unaligned flux-linkage ratio at the lowest non-zero current. Run it with 4 and with 8 workers (foreground, long timeout) and record: wall time, per-solve time, iterations range, failed-point count. Compare with the 30 s `screening` budget (spec §7.2). Do not add speed work: put the numbers and the options (structured air-gap mesh, tangent assembly speed, reuse of the Newton factorisation for L_inc) in `docs/m4-handoff.md`.

- [ ] **Step 6: Docs.**
  - `CLAUDE.md`: Current state (M4b done, M4c next), new "Map pipeline (M4b)" section (grids → `run_map` with the failure policy → `dataset` hash/HDF5/cache → `pool` → `build_map`), Commands (`examples\build_map_8_6.py [workers] [solver]`), `h5py` in dependencies.
  - Spec §11: rows for the decisions above (h5py required; parent-built mesh instead of a Gmsh session per worker; excitation layout; no mirror reduction, no continuation; warped angle grid and power-law current grid; solver by name with no fallback). §10: open items for M4c (overlap-start angle clustering, saturation-knee current refinement, physical core count, reuse of the Newton factorisation for L_inc, temperature in the map key).
  - `docs/m4-handoff.md`: state line "M4b done, M4c next"; carried-in items for M4c (inverse tables, overlap map and coupling check, exports, §7.3 checks, screening-vs-full fidelity check, per-pole force arrays) plus the measured map times.

- [ ] **Step 7: Commit**

```bash
git add -A src tests examples CLAUDE.md docs
git commit -m "feat(maps): process pool, build_map and the M4b docs"
```

---

## Self-review

- **Spec coverage (M4 row, this plan's share):** grids + fidelity presets → Task 1; error policy, cancellation, partial results → Task 2 and `map_ordered`; HDF5 dataset with provenance, cache (complete maps only) → Task 3; persistent worker pool, crash retry, BLAS/OMP pinned to 1 thread → Task 4; speed budget check → Task 4 Step 5. Left for M4c: L_inc, ∂ψ/∂θ and F_pole in the dataset, inverse tables, overlap map and coupling check, standard results and key numbers, exports, §7.3 checks, fidelity check, structured JSON logs.
- **Placeholders:** none. Task 4 Step 3 says how to reconcile the Task 2 tests with the pool refactor without loosening assertions.
- **Types:** `MapResult` fields are defined in Task 2 and used unchanged by `dataset.py` (Task 3), `run_map` (Task 4) and `build_map`; `map_ordered`'s `progress(done, total)` matches `run_map`'s; `make_solver(name, threads=None)` extends the Task 2 signature compatibly.
