"""EM-validated label (spec §8.5) and the worst-case uncertainty budget of the key numbers (§8.4)."""
import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import version

import numpy as np

from ..fields.solution import SolveStatus
from ..materials.laws import ReluctivityLaw, law_for_material, library_law
from ..materials.library import load_material
from ..mesh import build_machine_mesh
from ..mesh.machine import mesh_at_angle
from ..mesh.static import StaticMesh
from ..model.design import Design, RadialSRMParams
from ..model.errors import InputError
from ..physics.build import machine_problem
from ..post.quantities import arkkio_torque, flux_linkage
from ..solvers.factory import make_solver
from ..solvers.settings import SolverAdapter
from .checks import Check, _upper
from .end_winding import end_winding_inductance
from .fem_checks import fem_checks
from .grids import LA_CURRENT_FRACTION
from .results import key_numbers
from .run import MapResult, require_complete

KEYS = ("la", "lu", "peak_torque", "psi_max")

# srmcore versions whose results the validation campaign has covered; the label needs the running one in here.
VALIDATED_VERSIONS: tuple[str, ...] = ()
LABEL = "EM-validated"
PSI_POINT_TOLERANCE = 0.005       # full vs reference mesh, ψ at the La, Lu and ψ_max points
TORQUE_POINT_TOLERANCE = 0.01     # full vs reference mesh, torque at the peak-torque point
JS_STEP = 0.02                    # relative change of the saturation polarisation in the material row
GRADE_ALLOWANCE = {"A": 0.0, "B": 0.03, "C": 0.10}   # B-H data confidence grade -> relative allowance
END_WINDING_IMAGE = (1.0, 2.0)    # image-factor bounds of the end-winding inductance; corrected values use the midpoint


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


@dataclass(frozen=True)
class BudgetRow:
    source: str
    rel: dict[str, float]     # key -> relative half-width of this source
    note: str


@dataclass(frozen=True)
class UncertaintyBudget:
    values_2d: dict[str, float]   # key numbers of the 2D map
    values: dict[str, float]      # with the mid-range end-winding inductance added
    rows: tuple[BudgetRow, ...]
    total: dict[str, float]       # sum of the rows per key (worst case)


@dataclass(frozen=True)
class EmValidation:
    label: str | None
    checks: tuple[Check, ...]
    budget: UncertaintyBudget
    engine_version: str
    material_grades: dict[str, str]


def _rel(a: float, b: float) -> float:
    return abs(a - b) / abs(b)


def _point_check(name: str, keys: Sequence[str], vals: dict[str, dict[str, float]], rel: dict[str, float],
                 limit: float, what: str) -> Check:
    """Upper-limit check on the worst key-point error; the detail names the key (and the mesh whose solve
    did not converge)."""
    bad = [k for k in keys if not np.isfinite(rel[k])]
    if bad:
        k = bad[0]
        meshes = [m for m in ("full", "reference") if not np.isfinite(vals[m][k])]
        return _upper(name, float("nan"), limit,
                      f"{k} key-point solve non-converged on the {' and '.join(meshes)} mesh; {what}")
    k = max(keys, key=lambda key: rel[key])
    return _upper(name, rel[k], limit, f"worst at {k} ({rel[k]:.3%}); {what}")


def em_validate(design: Design, result: MapResult, *, solver: str = "ngsolve",
                workers: int | None = None) -> EmValidation:
    """The EM-validated checks and the uncertainty budget of a complete map. `label` is LABEL only when every
    check passes. Solves the four key points on the full and reference meshes and at Js ± JS_STEP."""
    require_complete(result)
    machine = design.machine
    points = key_points(result, machine)
    adapter = make_solver(solver)
    meshes, vals = {}, {}
    for preset in ("full", "reference"):
        d = design.model_copy(update={"mesh": design.mesh.model_copy(update={"preset": preset})})
        meshes[preset] = build_machine_mesh(d)
        vals[preset] = point_values(meshes[preset], d, points, result.excited, adapter)
    own = design.mesh.preset
    static = meshes[own] if own in meshes else build_machine_mesh(design)
    nominal = vals[own] if own in vals else point_values(static, design, points, result.excited, adapter)
    plus = point_values(static, design, points, result.excited, adapter, js_factor=1 + JS_STEP)
    try:
        minus = point_values(static, design, points, result.excited, adapter, js_factor=1 - JS_STEP)
    except InputError:
        minus = None
    fem = fem_checks(design, result, solver=solver, workers=workers)

    key = key_numbers(result, machine)
    values_2d = {k: getattr(key, k) for k in KEYS}
    mats = {"stator": machine.materials.stator, "rotor": machine.materials.rotor}
    loaded = {part: load_material(name) for part, name in mats.items()}
    grades = {part: m.confidence for part, m in loaded.items()}
    worst = max(grades.values())

    mesh_row = BudgetRow("mesh", {k: _rel(vals["full"][k], vals["reference"][k]) for k in KEYS},
                         "full vs reference mesh at the key points")
    if minus is None:
        js = {k: _rel(plus[k], nominal[k]) for k in KEYS}
        js_note = "Js +2 % only (B-H data exceed Js − 2 %)"
    else:
        js = {k: abs(plus[k] - minus[k]) / 2 / abs(nominal[k]) for k in KEYS}
        js_note = "Js ±2 %"
    js_solves = [nominal, plus] + ([minus] if minus is not None else [])
    nan_keys = [k for k in KEYS if any(not np.isfinite(v[k]) for v in js_solves)]
    nan_note = f"; non-converged Js solve at {', '.join(nan_keys)}, row is NaN" if nan_keys else ""
    material_row = BudgetRow("material", {k: js[k] + GRADE_ALLOWANCE[worst] for k in KEYS},
                             f"{js_note}; B-H data grade {worst}{nan_note}")
    l1, l2 = (end_winding_inductance(machine, f) for f in END_WINDING_IMAGE)
    half, l_mid = (l2 - l1) / 2, (l1 + l2) / 2
    values = {"la": key.la + l_mid, "lu": key.lu + l_mid, "peak_torque": key.peak_torque,
              "psi_max": key.psi_max + l_mid * key.i_max}
    end_row = BudgetRow("end_effect", {"la": half / values["la"], "lu": half / values["lu"], "peak_torque": 0.0,
                                       "psi_max": half * key.i_max / values["psi_max"]},
                        "end winding, image factor 1 to 2; iron-end 3D fringing not modelled")
    digitisation = max(m.digitisation_error or 0.0 for m in loaded.values())
    digitisation_row = BudgetRow("digitisation", {k: digitisation for k in KEYS}, "digitised B-H curve")
    rows = (mesh_row, material_row, end_row, digitisation_row)
    budget = UncertaintyBudget(values_2d, values, rows, {k: sum(r.rel[k] for r in rows) for k in KEYS})

    n_filled = float(np.sum(result.filled))
    checks = (
        Check("engine_version", "pass" if version("srmcore") in VALIDATED_VERSIONS else "fail", float("nan"),
              float("nan"), f"srmcore {version('srmcore')}; validated versions: "
                            f"{', '.join(VALIDATED_VERSIONS) or 'none'}"),
        Check("preset", "pass" if own in ("full", "reference") else "fail", float("nan"), float("nan"),
              f"map preset {own}; the label needs full or reference"),
        Check("no_filled_points", "fail" if n_filled else "pass", n_filled, 0.0,
              "points replaced by interpolation after a non-converged solve"),
        _point_check("point_convergence_psi", ("la", "lu", "psi_max"), vals, mesh_row.rel, PSI_POINT_TOLERANCE,
                     "full vs reference mesh ψ at the La, Lu and ψ_max points"),
        _point_check("point_convergence_torque", ("peak_torque",), vals, mesh_row.rel, TORQUE_POINT_TOLERANCE,
                     "full vs reference mesh torque at the peak-torque point, relative to peak torque"),
        *(fem or (Check("fem_checks", "fail", float("nan"), float("nan"),
                        "held-out and band-radius checks run only on full and reference maps"),)),
        Check("material_grade", "pass" if all(grades.values()) else "fail", float("nan"), float("nan"),
              f"stator {grades['stator']}, rotor {grades['rotor']}"),
    )
    label = LABEL if all(c.status == "pass" for c in checks) else None
    return EmValidation(label, checks, budget, version("srmcore"), grades)
