"""One operating point of a machine: mesh at an angle, solve, post-process (spec §7.2)."""
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ..fields.solution import FieldSolution, SolveStatus
from ..mesh.machine import mesh_at_angle
from ..mesh.static import StaticMesh
from ..model.design import Design
from ..physics.build import machine_problem
from ..post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from ..solvers.settings import SolverAdapter


@dataclass(frozen=True, eq=False)
class PointResult:
    """Everything a map needs from one solve. With status NONCONVERGED the numbers belong to the last
    iterate at `load_fraction` of the requested currents and must not enter a map."""
    angle: float                       # wrapped rotor angle in [0, 2π), rad
    circuits: tuple[str, ...]
    currents: np.ndarray               # A, one per circuit
    psi: np.ndarray                    # flux linkage per circuit, Wb-turns
    torque_arkkio: float               # N·m, positive counter-clockwise
    torque_virtual_work: float         # N·m
    energy: float                      # W, J
    coenergy: float                    # W', J
    status: SolveStatus
    iterations: int
    fallbacks: tuple[str, ...]
    load_fraction: float
    field: FieldSolution | None = None


def solve_point(static: StaticMesh, design: Design, angle: float, currents: Mapping[str, float],
                solver: SolverAdapter, initial: np.ndarray | None = None,
                keep_field: bool = False) -> PointResult:
    """Solve `design` with the rotor at `angle` and the given circuit currents. `initial` is a node
    vector A from a neighbouring point on the same static mesh. The field is kept only on request."""
    mesh = mesh_at_angle(static, angle)
    problem = machine_problem(mesh, design, currents)
    solution = solver.solve(problem, initial=initial)
    return PointResult(
        angle=mesh.rotor_angle, circuits=problem.winding.circuits, currents=problem.currents,
        psi=flux_linkage(problem, solution),
        torque_arkkio=arkkio_torque(problem, solution),
        torque_virtual_work=virtual_work_torque(problem, solution),
        energy=solution.energy, coenergy=solution.coenergy, status=solution.status,
        iterations=solution.iterations, fallbacks=solution.fallbacks, load_fraction=solution.load_fraction,
        field=solution if keep_field else None,
    )
