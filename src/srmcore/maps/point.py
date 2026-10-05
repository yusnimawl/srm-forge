"""One operating point of a machine: mesh at an angle, solve, post-process (spec §7.2)."""
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ..fields.solution import FieldSolution, SolveStatus
from ..mesh.machine import mesh_at_angle
from ..mesh.static import StaticMesh
from ..model.design import Design
from ..physics.build import machine_problem
from ..post.forces import pole_forces
from ..post.quantities import arkkio_torque, flux_linkage, incremental_inductance, virtual_work_torque
from ..solvers.settings import SolverAdapter

B_PEAK_QUANTILE = 0.999   # area fraction of iron below b_peak; the element maximum diverges at the pole corners


def area_quantile(values: np.ndarray, areas: np.ndarray, q: float = B_PEAK_QUANTILE) -> float:
    """Smallest value v such that elements with value <= v hold at least the fraction q of the total area."""
    order = np.argsort(values)
    cum = np.cumsum(areas[order])
    return float(values[order][np.searchsorted(cum, q * cum[-1])])


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
    pole_force: np.ndarray             # (n_stator_poles, 2) N: [radial outward, tangential counter-clockwise]
    status: SolveStatus
    iterations: int
    fallbacks: tuple[str, ...]
    load_fraction: float
    field: FieldSolution | None = None
    l_inc: np.ndarray | None = None    # H; only when requested and the solve converged at full load
    b_peak: float = float("nan")       # T: area-weighted B_PEAK_QUANTILE of |B| over the stator and rotor iron


def solve_point(static: StaticMesh, design: Design, angle: float, currents: Mapping[str, float],
                solver: SolverAdapter, initial: np.ndarray | None = None,
                keep_field: bool = False, with_l_inc: bool = False) -> PointResult:
    """Solve `design` with the rotor at `angle` and the given circuit currents. `initial` is a node
    vector A from a neighbouring point on the same static mesh. The field is kept only on request."""
    mesh = mesh_at_angle(static, angle)
    problem = machine_problem(mesh, design, currents)
    solution = solver.solve(problem, initial=initial)
    l_inc = None
    if with_l_inc and solution.status is not SolveStatus.NONCONVERGED and solution.load_fraction == 1.0:
        l_inc = incremental_inductance(problem, solver.sensitivity(problem, solution.a))
    kind = np.array([problem.region_kind[n] for n in problem.region_names])[problem.element_region]
    iron = (kind == "stator_iron") | (kind == "rotor_iron")
    t = problem.nodes[problem.triangles[iron]]
    area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    b_peak = area_quantile(np.hypot(solution.b[iron, 0], solution.b[iron, 1]), area)
    return PointResult(
        angle=mesh.rotor_angle, circuits=problem.winding.circuits, currents=problem.currents,
        psi=flux_linkage(problem, solution),
        torque_arkkio=arkkio_torque(problem, solution),
        torque_virtual_work=virtual_work_torque(problem, solution),
        energy=solution.energy, coenergy=solution.coenergy,
        pole_force=pole_forces(problem, solution, design.machine.n_stator_poles), status=solution.status,
        iterations=solution.iterations, fallbacks=solution.fallbacks, load_fraction=solution.load_fraction,
        field=solution if keep_field else None, l_inc=l_inc, b_peak=b_peak,
    )
