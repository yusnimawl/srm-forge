"""Solver-neutral 2D magnetostatic problem (spec §6): ∇·(ν(|B|)∇A_z) = -J_z, A = 0 on the Dirichlet
nodes, depth = stack length."""
import dataclasses
from dataclasses import dataclass

import numpy as np

from ..materials.laws import ReluctivityLaw
from .winding import Winding


@dataclass(frozen=True, eq=False)
class BandInfo:
    elements: np.ndarray
    inner_radius: float
    outer_radius: float


@dataclass(frozen=True, eq=False)
class Magnetostatic2D:
    nodes: np.ndarray
    triangles: np.ndarray
    element_law: np.ndarray
    laws: tuple[ReluctivityLaw, ...]
    element_region: np.ndarray
    region_names: tuple[str, ...]
    region_kind: dict[str, str]
    element_coil: np.ndarray
    winding: Winding
    currents: np.ndarray
    dirichlet_nodes: np.ndarray
    depth: float
    band: BandInfo | None = None

    def current_density(self) -> np.ndarray:
        """J_z per element, A/m²."""
        j = np.zeros(len(self.triangles))
        in_coil = self.element_coil >= 0
        j[in_coil] = self.winding.matrix[self.element_coil[in_coil]] @ self.currents
        return j

    def with_currents(self, currents) -> "Magnetostatic2D":
        currents = np.asarray(currents, float)
        if currents.shape != (len(self.winding.circuits),):
            raise ValueError(f"expected {len(self.winding.circuits)} circuit currents, got shape {currents.shape}")
        return dataclasses.replace(self, currents=currents)
