"""Newton settings pinned across adapters (spec §6), and the adapter protocol."""
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..fields.solution import FieldSolution
from ..physics.problem import Magnetostatic2D

# Element order and quadrature rule every adapter must use, so cross-solver comparisons (M3) compare
# the same discretisation.
ELEMENT_ORDER = 1
QUADRATURE_ORDER = 2


@dataclass(frozen=True)
class NewtonSettings:
    residual_tol: float = 1e-8       # ||r_free|| / ||f_free||
    delta_tol: float = 1e-8          # ||ΔA|| / ||A||
    max_iterations: int = 50
    max_halvings: int = 20
    damped_max_step: float = 0.5     # step cap of the "damped" fallback until the residual is below 1e-2
    ramp_steps: int = 4              # current sub-steps of the "ramp" fallback


class SolverAdapter(Protocol):
    name: str
    version: str

    def solve(self, problem: Magnetostatic2D, initial: np.ndarray | None = None) -> FieldSolution:
        """Never raises for non-convergence: returns status NONCONVERGED instead (spec §6)."""
        ...

    def sensitivity(self, problem: Magnetostatic2D, a: np.ndarray) -> np.ndarray:
        """dA/di_k = K_T(A)⁻¹·∂f/∂i_k for every circuit k at the converged field `a`: shape
        (n_nodes, n_circuits), zero on the Dirichlet nodes."""
        ...
