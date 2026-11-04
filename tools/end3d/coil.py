"""Coil current density for the 3D model: a conduction solve along one coil tube."""
from __future__ import annotations

import ngsolve as ng


def face_current(mesh: ng.Mesh, j: ng.CoefficientFunction, face: str) -> float:
    """Integral of J.n over the named boundary face (n is the mesh's outward normal), in A."""
    return ng.Integrate(ng.BoundaryFromVolumeCF(j) * ng.specialcf.normal(3), mesh, ng.BND,
                        definedon=mesh.Boundaries(face))


def coil_current_density(mesh: ng.Mesh, coil: str, ampere_turns: float,
                         order: int = 2) -> ng.CoefficientFunction:
    """J in the coil solid `coil`, zero elsewhere, with flux `ampere_turns` out through `<coil>_in`.

    Solves the Laplace problem for phi in the coil (1 on `<coil>_in`, 0 on `<coil>_out`, zero
    normal flux elsewhere); J is proportional to grad(phi), so it is divergence-free and
    tangential to the coil walls.
    """
    face_in, face_out = f"{coil}_in", f"{coil}_out"
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
    raw = mesh.MaterialCF({coil: ng.grad(phi)}, default=ng.CoefficientFunction((0, 0, 0)))
    return raw * (ampere_turns / face_current(mesh, raw, face_in))
