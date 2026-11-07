"""Test-only 2D plane-stress elastic FE of a spinning rotor lamination (body force rho w^2 r): the whole rotor on
the static mesh (straight-sided P2), and a half-pole sector on its own curved mesh, the reference for the fillet."""
import math
from dataclasses import dataclass

import gmsh
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu, spsolve
from skfem import Basis, BilinearForm, ElementTriP2, ElementVector, LinearForm, MeshTri, MeshTri2, asm
from skfem.helpers import ddot, dot, sym_grad, trace
from srmapp.references import make_8_6
from srmcore.geometry.session import gmsh_model
from srmcore.post.rotor_stress import pole_half_width
from srmcore.topology.radial import _pole_side

RHO, E, NU, OMEGA = 7490.0, 200e9, 0.33, 2 * math.pi * 200   # the sweep conditions
LEVELS = (20, 40, 80)   # fillet radius / element size


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


@dataclass(frozen=True)
class SectorStress:
    bore_peak: float           # Pa, peak von Mises on the bore arc
    root_peak: float | None    # Pa, peak von Mises on the fillet arc
    peak: float                # Pa, peak von Mises anywhere in the sector
    peak_xy: tuple[float, float]
    tip_displacement: float    # m, length-weighted mean radial displacement on the tip arc
    fillet_position: np.ndarray | None   # 0 at the flank end of the fillet, 1 at the rim end
    fillet_stress: np.ndarray | None     # Pa, signed tangential stress at those positions
    rim_stress: np.ndarray               # Pa, signed tangential stress on the rim, from the fillet to the cut
    bore_stress: np.ndarray              # Pa, signed tangential stress on the bore, from theta 0 to the cut
    n_dofs: int


def _curved_mesh(curves, sizes) -> MeshTri2:
    """Quadratic mesh of the closed loop `curves`: ("line", p, q, tag) or ("arc", p, q, centre, tag), boundary nodes on
    the true arcs. `sizes` maps a tag to (size on the curve, growth per metre); the size is the minimum over tags."""
    options = {f"Mesh.{name}": value for name, value in (
        ("MeshSizeExtendFromBoundary", 0), ("MeshSizeFromPoints", 0), ("MeshSizeFromCurvature", 0), ("Algorithm", 6),
        ("MeshSizeMax", 1e3))}
    with gmsh_model():
        saved = {name: gmsh.option.getNumber(name) for name in options}   # the session's options are process-wide
        geo = gmsh.model.geo
        ids: dict[tuple[float, float], int] = {}

        def point(q):
            key = (round(q[0], 12), round(q[1], 12))
            if key not in ids:
                ids[key] = geo.addPoint(q[0], q[1], 0.0)
            return ids[key]

        loop, by_tag = [], {}
        for c in curves:
            tag = geo.addLine(point(c[1]), point(c[2])) if c[0] == "line" else \
                geo.addCircleArc(point(c[1]), point(c[3]), point(c[2]))
            loop.append(tag)
            by_tag.setdefault(c[-1], []).append(tag)
        geo.addPlaneSurface([geo.addCurveLoop(loop)])
        geo.synchronize()
        field = gmsh.model.mesh.field
        parts = []
        for tag, (size, growth) in sizes.items():
            dist = field.add("Distance")
            field.setNumbers(dist, "CurvesList", by_tag[tag])
            field.setNumber(dist, "Sampling", 400)
            parts.append(field.add("MathEval"))
            field.setString(parts[-1], "F", f"{size!r} + {growth!r} * F{dist}")
        low = field.add("Min")
        field.setNumbers(low, "FieldsList", parts)
        field.setAsBackgroundMesh(low)
        try:
            for name, value in options.items():
                gmsh.option.setNumber(name, value)
            gmsh.model.mesh.generate(2)
        finally:
            for name, value in saved.items():
                gmsh.option.setNumber(name, value)
        gmsh.model.mesh.setOrder(2)
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        _, _, nodes = gmsh.model.mesh.getElements(2)
    order = np.zeros(int(tags.max()) + 1, dtype=np.int64)
    order[tags.astype(np.int64)] = np.arange(len(tags))
    tri = order[nodes[0].astype(np.int64)].reshape(-1, 6)
    xy = xyz.reshape(-1, 3)[:, :2]
    corners, inverse = np.unique(tri[:, :3], return_inverse=True)
    t = inverse.reshape(-1, 3)
    linear = MeshTri(np.ascontiguousarray(xy[corners].T), np.ascontiguousarray(t.T))
    mesh = MeshTri2.from_mesh(linear)
    # gmsh mid-edge nodes replace the straight midpoints that from_mesh placed
    n = len(corners)
    keys = linear.facets[0].astype(np.int64) * n + linear.facets[1]
    rank = np.argsort(keys)
    locs = mesh.doflocs.copy()
    for (i, j), mid in (((0, 1), 3), ((1, 2), 4), ((2, 0), 5)):
        lo, hi = np.minimum(t[:, i], t[:, j]), np.maximum(t[:, i], t[:, j])
        facet = rank[np.searchsorted(keys[rank], lo.astype(np.int64) * n + hi)]
        locs[:, n + facet] = xy[tri[:, mid]].T
    return MeshTri2(doflocs=locs, t=mesh.t)


def sector_fe(curves, sizes, half_pitch, bore_radius, tip_radius, density, youngs_modulus, poisson_ratio, omega,
              element=None, body=None, rim_radius=None, fillet=None) -> SectorStress:
    """Sector between theta 0 and `half_pitch`, u normal to each cut zero, free elsewhere. Stresses are L2-projected on
    the continuous scalar space and read at its boundary nodes, so a value is never one quadrature point. `body` masks
    the centrifugal load, x -> bool. `fillet` is (centre, radius, position of a point in [0, 1])."""
    mesh = _curved_mesh(curves, sizes)
    basis = Basis(mesh, ElementVector(element or ElementTriP2()), intorder=8)
    scalar = basis.with_element(element or ElementTriP2())
    e, nu = youngs_modulus, poisson_ratio
    mu, lam = e / (2 * (1 + nu)), e * nu / (1 - nu**2)

    @BilinearForm
    def stiffness(u, v, _):
        return 2 * mu * ddot(sym_grad(u), sym_grad(v)) + lam * trace(sym_grad(u)) * trace(sym_grad(v))

    @LinearForm
    def load(v, w):
        mask = 1.0 if body is None else body(w.x)
        return mask * density * omega**2 * dot(w.x, v)

    k, f = asm(stiffness, basis), asm(load, basis)

    ix, iy = basis.split_indices()
    loc = basis.doflocs[:, ix]
    x, y = loc
    tol = 1e-9 * tip_radius
    c, s = math.cos(half_pitch), math.sin(half_pitch)
    on_axis = np.abs(y) < tol
    on_cut = np.abs(x * s - y * c) < tol
    # free dofs: ux everywhere but on the cut, uy off both cuts, one along-cut dof per node on the cut
    keep_x, keep_y = ix[~on_cut], iy[~(on_axis | on_cut)]
    rows = np.concatenate([keep_x, keep_y, ix[on_cut], iy[on_cut]])
    n_plain = len(keep_x) + len(keep_y)
    along = n_plain + np.arange(on_cut.sum())
    cols = np.concatenate([np.arange(n_plain), along, along])
    vals = np.concatenate([np.ones(n_plain), np.full(on_cut.sum(), c), np.full(on_cut.sum(), s)])
    reduce = coo_matrix((vals, (rows, cols)), shape=(basis.N, n_plain + on_cut.sum())).tocsr()
    u = reduce @ spsolve((reduce.T @ k @ reduce).tocsc(), reduce.T @ f)

    grad = basis.interpolate(u).grad
    exx, eyy, exy = grad[0, 0], grad[1, 1], 0.5 * (grad[0, 1] + grad[1, 0])
    tr = exx + eyy

    @BilinearForm
    def mass(a, b, _):
        return a * b

    @LinearForm
    def project(v, w):
        return w.s * v

    factor = splu(asm(mass, scalar).tocsc())
    sx, sy, sxy = (factor.solve(asm(project, scalar, s=q))
                   for q in (2 * mu * exx + lam * tr, 2 * mu * eyy + lam * tr, 2 * mu * exy))
    vm = np.sqrt(sx**2 - sx * sy + sy**2 + 3 * sxy**2)

    theta = np.arctan2(y, x)
    r = np.hypot(x, y)
    hoop = sx * np.sin(theta)**2 + sy * np.cos(theta)**2 - 2 * sxy * np.sin(theta) * np.cos(theta)
    edge = 1e-7 * tip_radius
    on_bore = np.abs(r - bore_radius) < edge
    bore_order = np.flatnonzero(on_bore)[np.argsort(theta[on_bore])]
    on_tip = np.abs(r - tip_radius) < edge
    tip_order = np.flatnonzero(on_tip)[np.argsort(theta[on_tip])]
    ur = (u[ix] * x + u[iy] * y) / r
    tip = np.trapezoid(ur[tip_order], theta[tip_order]) / (theta[tip_order[-1]] - theta[tip_order[0]])

    position = stress = root = None
    rim_start = 0.0
    if fillet is not None:
        centre, radius, place = fillet
        on_arc = np.abs(np.hypot(x - centre[0], y - centre[1]) - radius) < edge
        p = place(x[on_arc], y[on_arc])
        pick = (p >= -1e-9) & (p <= 1 + 1e-9)
        nodes = np.flatnonzero(on_arc)[pick][np.argsort(p[pick])]
        position = np.sort(p[pick])
        # the tangent of the fillet circle at each node
        ang = np.arctan2(y[nodes] - centre[1], x[nodes] - centre[0])
        stress = (sx[nodes] * np.sin(ang)**2 + sy[nodes] * np.cos(ang)**2
                  - 2 * sxy[nodes] * np.sin(ang) * np.cos(ang))
        root = float(vm[nodes].max())
        rim_start = float(theta[nodes[-1]])
    on_rim = np.abs(r - rim_radius) < edge if rim_radius else np.zeros_like(on_bore)
    on_rim &= theta >= rim_start - 1e-12
    rim_order = np.flatnonzero(on_rim)[np.argsort(theta[on_rim])]
    top = int(np.argmax(vm))
    return SectorStress(float(vm[bore_order].max()), root, float(vm[top]), (float(x[top]), float(y[top])), float(tip),
                        position, stress, hoop[rim_order], hoop[bore_order], basis.N)


def rotor_sector_fe(machine, density, youngs_modulus, poisson_ratio, omega, per_radius=30, element=None,
                    body=None) -> SectorStress:
    """Half-pole sector of `machine`. The fillet carries elements of size radius / per_radius; every other size scales
    with it, so raising per_radius refines the whole mesh."""
    a, b, big = machine.shaft_radius, machine.rotor_yoke_outer_radius, machine.rotor_outer_radius
    rf, n = machine.rotor_fillet_radius, machine.n_rotor_poles
    half = math.pi / n
    side = _pole_side(big, machine.rotor_pole_arc, machine.rotor_pole_taper, b, rf, False, 2 * half)
    cut = (math.cos(half), math.sin(half))
    origin = (0.0, 0.0)
    curves = [("line", (a, 0.0), (big, 0.0), "cut"), ("arc", (big, 0.0), side.face_end, origin, "tip"),
              ("line", side.face_end, side.flank_end, "flank"),
              ("arc", side.flank_end, side.root_end, side.fillet_center, "fillet"),
              ("arc", side.root_end, (b * cut[0], b * cut[1]), origin, "rim"),
              ("line", (b * cut[0], b * cut[1]), (a * cut[0], a * cut[1]), "cut"),
              ("arc", (a * cut[0], a * cut[1]), (a, 0.0), origin, "bore")]
    scale = 30 / per_radius
    wall = min(b - a, 2 * side.root_end[1])
    size = min(wall / 12, 3 * rf) * scale
    sizes = {"fillet": (rf / per_radius, 0.25), "bore": (size / 2, 0.25), "rim": (size / 2, 0.25),
             "flank": (size, 0.25), "tip": (size, 0.25), "cut": (size, 0.25)}
    centre = side.fillet_center
    start = math.atan2(side.flank_end[1] - centre[1], side.flank_end[0] - centre[0])
    end = math.atan2(side.root_end[1] - centre[1], side.root_end[0] - centre[0])
    span = (end - start + math.pi) % (2 * math.pi) - math.pi

    def place(x, y):
        return ((np.arctan2(y - centre[1], x - centre[0]) - start + math.pi) % (2 * math.pi) - math.pi) / span

    return sector_fe(curves, sizes, half, a, big, density, youngs_modulus, poisson_ratio, omega, element, body, b,
                     (centre, rf, place))


def sweep_point(values) -> dict:
    """FE of one sweep design at every level, and the load split at the middle level; the `values` override make_8_6.
    A shape that does not fit gives {"params", "skipped"}."""
    machine = make_8_6(**values)
    b = machine.rotor_yoke_outer_radius
    try:
        levels = [rotor_sector_fe(machine, RHO, E, NU, OMEGA, n) for n in LEVELS]
        pole = rotor_sector_fe(machine, RHO, E, NU, OMEGA, LEVELS[1], body=lambda x: 1.0 * (np.hypot(*x) > b))
        yoke = rotor_sector_fe(machine, RHO, E, NU, OMEGA, LEVELS[1], body=lambda x: 1.0 * (np.hypot(*x) <= b))
    except ValueError as exc:
        return {"params": values, "skipped": str(exc)}
    fe = levels[-1]
    return {"params": values, "bore": [s.bore_peak for s in levels], "root": [s.root_peak for s in levels],
            "tip": [s.tip_displacement for s in levels], "peak": fe.peak,
            "root_position": float(fe.fillet_position[np.argmax(np.abs(fe.fillet_stress))]),
            "pole_root": pole.root_peak, "yoke_root": yoke.root_peak}
