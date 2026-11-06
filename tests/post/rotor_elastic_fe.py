"""Test-only 2D plane-stress elastic FE of a spinning rotor lamination (P2 triangles, body force rho w^2 r)."""
import math
from dataclasses import dataclass

import numpy as np
from scipy.sparse.linalg import spsolve
from skfem import Basis, BilinearForm, ElementTriP2, ElementVector, LinearForm, MeshTri, asm
from skfem.helpers import ddot, sym_grad, trace
from srmcore.post.rotor_stress import pole_half_width


@dataclass(frozen=True)
class FeStress:
    bore_peak: float          # Pa, peak von Mises within 1 mm of the bore
    root_peak: float | None   # Pa, peak von Mises within 2 fillet radii of a pole root; None without root points
    tip_displacement: float   # m, mean radial displacement over the nodes on the tip radius


def _von_mises(s):
    sx, sy, t = s[0, 0], s[1, 1], s[0, 1]
    return np.sqrt(sx**2 - sx * sy + sy**2 + 3 * t**2)   # plane stress


def elastic_fe_mesh(nodes, triangles, density, youngs_modulus, poisson_ratio, omega, bore_radius, tip_radius,
                    root_points=(), fillet_radius=0.0) -> FeStress:
    """Free bore, centrifugal body force, three rigid-body DOFs pinned. The load is self-equilibrated, so the pin
    only removes a rigid-body offset: stresses are unaffected and the tip displacement is the radial mean."""
    mesh = MeshTri(np.ascontiguousarray(nodes.T, dtype=float), np.ascontiguousarray(triangles.T, dtype=np.int64))
    basis = Basis(mesh, ElementVector(ElementTriP2()))
    e, nu = youngs_modulus, poisson_ratio
    mu, lam = e / (2 * (1 + nu)), e * nu / (1 - nu**2)

    @BilinearForm
    def stiffness(u, v, _):
        return 2 * mu * ddot(sym_grad(u), sym_grad(v)) + lam * trace(sym_grad(u)) * trace(sym_grad(v))

    @LinearForm
    def load(v, w):
        return density * omega**2 * (w.x[0] * v.value[0] + w.x[1] * v.value[1])

    k, f = asm(stiffness, basis), asm(load, basis)
    nd = basis.nodal_dofs                      # (2, n_nodes)
    far = int(np.argmax(np.hypot(*(nodes - nodes[0]).T)))
    d = nodes[far] - nodes[0]
    pinned = [nd[0, 0], nd[1, 0], nd[0 if abs(d[1]) > abs(d[0]) else 1, far]]
    u = np.zeros(basis.N)
    free = np.setdiff1d(np.arange(basis.N), pinned)
    u[free] = spsolve(k[free][:, free].tocsc(), f[free])

    grad = basis.interpolate(u).grad           # (2, 2, n_el, n_qp)
    eps = 0.5 * (grad + grad.transpose(1, 0, 2, 3))
    tr = eps[0, 0] + eps[1, 1]
    sig = 2 * mu * eps
    sig[0, 0] += lam * tr
    sig[1, 1] += lam * tr
    vm = _von_mises(sig)
    xy = basis.global_coordinates()      # (2, n_el, n_qp)
    r = np.hypot(xy[0], xy[1])
    bore = float(vm[r <= bore_radius + 1e-3].max())
    root = None
    if len(root_points):
        near = np.zeros_like(vm, dtype=bool)
        for px, py in root_points:
            near |= np.hypot(xy[0] - px, xy[1] - py) <= 2 * fillet_radius
        root = float(vm[near].max())
    rn = np.hypot(*nodes.T)
    tip = rn >= tip_radius * (1 - 1e-6)
    ux, uy = u[nd[0]], u[nd[1]]
    radial = (ux * nodes[:, 0] + uy * nodes[:, 1]) / rn
    return FeStress(bore, root, float(radial[tip].mean()))


def rotor_elastic_fe(static, density, youngs_modulus, poisson_ratio, omega, machine) -> FeStress:
    """FE of the `rotor_iron` elements of a static mesh (the shaft is not part of the lamination)."""
    part = static.rotor
    iron = [i for i, n in enumerate(static.region_names) if static.region_kind[n] == "rotor_iron"]
    tris = part.triangles[np.isin(part.region_ids, iron)]
    used, inverse = np.unique(tris, return_inverse=True)
    nodes, tris = part.nodes[used], inverse.reshape(tris.shape)
    b, rf = machine.rotor_yoke_outer_radius, machine.rotor_fillet_radius
    y = pole_half_width(machine, b)
    x = math.sqrt(b**2 - y**2)
    pts = []
    for k in range(machine.n_rotor_poles):
        c, s = math.cos(2 * math.pi * k / machine.n_rotor_poles), math.sin(2 * math.pi * k / machine.n_rotor_poles)
        for sy in (y, -y):
            pts.append((c * x - s * sy, s * x + c * sy))
    return elastic_fe_mesh(nodes, tris, density, youngs_modulus, poisson_ratio, omega, machine.shaft_radius,
                           machine.rotor_outer_radius, pts, rf)
