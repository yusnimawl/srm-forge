"""EM-validated label (spec §8.5) and the worst-case uncertainty budget of the key numbers (§8.4)."""
import dataclasses
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
