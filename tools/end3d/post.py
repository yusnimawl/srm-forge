"""Full-machine quantities from a half-model or slab solution; the mirror factor 2 is applied here and nowhere else."""
from __future__ import annotations

from typing import Mapping, Sequence

import ngsolve as ng

from srmcore.model.constants import MU0

from .coil import coil_current_density
from .material import energy_bspline
from .solve import Model3D, Solution3D

MIRROR = 2.0
QUAD_ORDER = 8


def _b(sol: Solution3D) -> ng.CoefficientFunction:
    return ng.curl(sol.a)


def _integral(cf, model: Model3D, region: str | None = None) -> float:
    mesh = model.mesh
    kw = {"definedon": mesh.Materials(region)} if region else {}
    return ng.Integrate(cf, mesh, order=QUAD_ORDER, **kw)


def flux_linkage(model: Model3D, sol: Solution3D, coils: Sequence[str], current: float,
                 ampere_turns: Mapping[str, float]) -> float:
    """psi = 2 int A.J dV / current (Wb-turns), J the ampere-turn density of `coils`."""
    j = sum((coil_current_density(model.mesh, c, ampere_turns[c], model.order) for c in coils),
            ng.CoefficientFunction((0, 0, 0)))
    return MIRROR * _integral(ng.InnerProduct(sol.a, j), model, "|".join(coils)) / current


def arkkio_torque(model: Model3D, sol: Solution3D, r_inner: float, r_outer: float,
                  shell: str = "gap_shell") -> float:
    """T = 2 int_shell r B_r B_theta dV / (mu0 (r_outer - r_inner)), N.m, counter-clockwise positive."""
    x, y = ng.x, ng.y
    b = _b(sol)
    r_br_bt = (b[0] * x + b[1] * y) * (-b[0] * y + b[1] * x) / ng.sqrt(x * x + y * y)
    return MIRROR * _integral(r_br_bt, model, shell) / (MU0 * (r_outer - r_inner))


def coenergy(model: Model3D, sol: Solution3D) -> float:
    """2 int (B.H - w) dV (J), per material; B.H - w = 2 s w'(s) - w(s) with s = |B|^2."""
    b = _b(sol)
    s = ng.InnerProduct(b, b)
    total = 0.0
    for name in dict.fromkeys(model.mesh.GetMaterials()):
        w = energy_bspline(model.laws[name])
        total += _integral(2 * s * w.Differentiate()(s) - w(s), model, name)
    return MIRROR * total


def face_flux(model: Model3D, sol: Solution3D, face: str) -> float:
    """2 int_face B.n dA (Wb), n the face normal flipped to point away from the z axis (a face
    that does not contain the axis, such as `search`, so the sign is the outward radial flux)."""
    n = ng.specialcf.normal(3)
    outward = ng.IfPos(n[0] * ng.x + n[1] * ng.y, 1.0, -1.0)
    cf = ng.BoundaryFromVolumeCF(_b(sol)) * n * outward
    return MIRROR * ng.Integrate(cf, model.mesh, ng.BND, order=QUAD_ORDER,
                                 definedon=model.mesh.Boundaries(face))
