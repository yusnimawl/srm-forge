"""Winding as data (spec §6): the connection matrix from coil sides to circuits."""
from dataclasses import dataclass

import numpy as np

from ..mesh.machine import MachineMesh
from ..model.errors import InputError, ValidationIssue
from .fem import triangle_areas


@dataclass(frozen=True, eq=False)
class Winding:
    """matrix[s, k] = sign × turns / (parallel_paths × area of coil side s), in 1/m², so that the
    current density in side s is Σ_k matrix[s, k]·i_k and ψ_k = L·Σ_s matrix[s, k]·∫_s A dA."""
    coil_sides: tuple[str, ...]
    circuits: tuple[str, ...]
    matrix: np.ndarray
    parallel_paths: int
    # Spec §6: with more than one parallel path the circuit current is assumed to split equally.
    equal_path_split_assumed: bool


def phase_winding(mesh: MachineMesh, turns_per_pole: int, parallel_paths: int = 1) -> Winding:
    """Conventional SRM: one circuit per phase, every coil side of that phase in it."""
    phases = sorted({info.phase for info in mesh.coils.values()})
    for phase in phases:
        poles = {info.pole for info in mesh.coils.values() if info.phase == phase}
        if parallel_paths < 1 or len(poles) % parallel_paths:
            raise InputError([ValidationIssue(
                "parallel_paths", "winding",
                f"phase {phase} has {len(poles)} poles, which {parallel_paths} parallel paths cannot divide")])
    sides = tuple(sorted(mesh.coils))
    areas = triangle_areas(mesh.nodes, mesh.triangles)
    matrix = np.zeros((len(sides), len(phases)))
    for s, name in enumerate(sides):
        info = mesh.coils[name]
        area = areas[mesh.region_ids == mesh.region_names.index(name)].sum()
        matrix[s, phases.index(info.phase)] = info.sign * turns_per_pole / (parallel_paths * area)
    return Winding(sides, tuple(phases), matrix, parallel_paths, parallel_paths > 1)
