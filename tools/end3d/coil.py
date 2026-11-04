"""Coil current density for the 3D model: a conduction solve along one coil tube."""
from __future__ import annotations

import ngsolve as ng


def face_current(mesh: ng.Mesh, j: ng.CoefficientFunction, face: str) -> float:
    """Integral of J.n over the named boundary face (n is the mesh's outward normal), in A.

    On an internal face the normal orientation is arbitrary, so only the magnitude is meaningful.
    """
    return ng.Integrate(ng.BoundaryFromVolumeCF(j) * ng.specialcf.normal(3), mesh, ng.BND,
                        definedon=mesh.Boundaries(face))


def coil_current_density(mesh: ng.Mesh, coil: str, ampere_turns: float,
                         order: int = 2) -> ng.CoefficientFunction:
    """J in the coil solid `coil`, zero elsewhere, with `ampere_turns` entering through `<coil>_in`.

    Raises ValueError if the coil solid or its `_in`/`_out` faces are missing from the mesh.

    Solves the Laplace problem for phi in the coil (1 on `<coil>_in`, 0 on `<coil>_out`, zero
    normal flux elsewhere); J = -c grad(phi) with c > 0, so it is divergence-free, tangential
    to the coil walls and flows from `_in` to `_out`. face_current(`_in`) is -ampere_turns and
    face_current(`_out`) is +ampere_turns (outward normal).
    """
    face_in, face_out = f"{coil}_in", f"{coil}_out"
    if coil not in mesh.GetMaterials():
        raise ValueError(f"coil solid {coil!r} is not in the mesh")
    for face in (face_in, face_out):
        if face not in mesh.GetBoundaries():
            raise ValueError(f"coil face {face!r} is not in the mesh")
    fes = ng.H1(mesh, order=order, definedon=mesh.Materials(coil),
                dirichlet=f"{face_in}|{face_out}")
    u, v = fes.TnT()
    a = ng.BilinearForm(fes)
    a += ng.grad(u) * ng.grad(v) * ng.dx
    a.Assemble()
    phi = ng.GridFunction(fes)
    phi.Set(mesh.BoundaryCF({face_in: 1.0}, default=0.0), ng.BND)
    rhs = phi.vec.CreateVector()
    rhs.data = -a.mat * phi.vec
    phi.vec.data += a.mat.Inverse(fes.FreeDofs(), inverse="sparsecholesky") * rhs
    raw = mesh.MaterialCF({coil: -ng.grad(phi)}, default=ng.CoefficientFunction((0, 0, 0)))
    return raw * (-ampere_turns / face_current(mesh, raw, face_in))
