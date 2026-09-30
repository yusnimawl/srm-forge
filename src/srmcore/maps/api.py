"""Public entry: a map of a design, from cache or by solving (spec §7.2)."""
import math
import os
from collections.abc import Callable

from ..mesh import build_machine_mesh
from ..mesh.settings import resolve_mesh_settings
from ..model.design import Design
from ..solvers.factory import make_solver
from .dataset import cached_map, provenance, store_map
from .grids import GRID_SIZES, aligned_angle, angle_grid, current_grid
from .run import MapResult, run_map


def build_map(design: Design, i_max: float, *, solver: str = "ngsolve", excited: str = "A",
              workers: int | None = None, n_angles: int | None = None, n_currents: int | None = None,
              cache_dir=None, progress: Callable[[int, int], None] | None = None,
              cancel: Callable[[], bool] | None = None) -> MapResult:
    """ψ and torque of `design` over an angle × current grid with `excited` carrying the current. Grid sizes
    default to the design's fidelity preset. A complete map is stored in and served from `cache_dir`."""
    if not math.isfinite(i_max) or i_max <= 0:
        raise ValueError(f"i_max must be finite and positive, got {i_max}")
    if n_angles is not None and n_angles < 1:
        raise ValueError(f"n_angles must be at least 1, got {n_angles}")
    if n_currents is not None and n_currents < 2:
        raise ValueError(f"n_currents must be at least 2, got {n_currents}")
    aligned = aligned_angle(design.machine, excited)          # rejects a letter that is not a phase
    adapter = make_solver(solver)
    default_a, default_i = GRID_SIZES[design.mesh.preset]
    divisions = resolve_mesh_settings(design.machine, design.mesh).band_divisions
    angles = angle_grid(design.machine, divisions, default_a if n_angles is None else n_angles,
                        aligned=aligned)
    currents = current_grid(i_max, default_i if n_currents is None else n_currents)
    prov = provenance(design, angles, currents, excited, adapter)
    if cache_dir is not None and (hit := cached_map(cache_dir, prov)) is not None:
        return hit
    # ponytail: half the logical CPUs stands in for the physical core count; psutil is not a dependency.
    workers = workers if workers is not None else max(1, (os.cpu_count() or 2) // 2)
    workers = max(1, min(workers, len(angles) * len(currents), 61))          # 61: the Windows pool limit
    result = run_map(build_machine_mesh(design), design, angles, currents, solver_name=solver, excited=excited,
                     workers=workers, progress=progress, cancel=cancel)
    if cache_dir is not None:
        store_map(cache_dir, result, prov)
    return result
