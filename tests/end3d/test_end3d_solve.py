import dataclasses
import math

import pytest

ngsolve = pytest.importorskip("ngsolve")
from netgen.occ import Box, Cylinder, Glue, OCCGeometry, Pnt, X, Z  # noqa: E402

from end3d.solve import Model3D, solve3d  # noqa: E402
from srmcore.materials.laws import LinearLaw  # noqa: E402
from srmcore.model.constants import MU0  # noqa: E402
from team24_fixture import steel_law  # noqa: E402

MM = 1e-3


def _shell(r0, r1, h, name):
    s = Cylinder(Pnt(0, 0, 0), Z, r1, h) - Cylinder(Pnt(0, 0, 0), Z, r0, h)
    s.mat(name)
    s.faces.Min(Z).name = f"{name}_in"
    s.faces.Max(Z).name = f"{name}_out"
    return s


def _sheet_pair_mesh():
    """Two coaxial thin shells (r 10-12 mm, 20-22 mm), 4 mm tall, in an air cylinder; z faces are slab faces."""
    h = 4 * MM
    inner, outer = _shell(10 * MM, 12 * MM, h, "coil_a"), _shell(20 * MM, 22 * MM, h, "coil_b")
    air = Cylinder(Pnt(0, 0, 0), Z, 40 * MM, h)
    air.mat("air")
    air.faces.name = "outer"
    air.faces.Min(Z).name = "sym_z"
    air.faces.Max(Z).name = "end_z"
    geo = OCCGeometry(Glue([air - inner - outer, inner, outer]))
    mesh = ngsolve.Mesh(geo.GenerateMesh(maxh=2 * MM))
    mesh.Curve(2)
    return mesh


def test_current_sheet_field():
    """Opposite currents on coaxial shells: B in the gap is mu0 I / (2 pi r) (Ampere), the 2D-equivalent slab field."""
    mesh = _sheet_pair_mesh()
    model = Model3D(mesh, {"air": LinearLaw(), "coil_a": LinearLaw(), "coil_b": LinearLaw()},
                    coils=("coil_a", "coil_b"), dirichlet="sym_z|end_z|outer")
    at = 100.0
    sol = solve3d(model, {"coil_a": at, "coil_b": -at})
    assert sol.converged
    r = 16 * MM
    b = ngsolve.curl(sol.a)(mesh(r, 0, 2 * MM))
    assert b[1] > 0     # current enters at coil_a_in (z = 0): +z on the inner shell, counter-clockwise B
    assert math.hypot(b[0], b[1]) == pytest.approx(MU0 * at / (2 * math.pi * r), rel=0.01)


def _iron_in_u_coil_mesh():
    """U coil (two 10 x 20 mm sides, 50 mm long, 10 mm bridge) around an iron block, half model in an air box."""
    def box(x0, x1, z0, z1):
        return Box(Pnt(x0 * MM, 0, z0 * MM), Pnt(x1 * MM, 20 * MM, z1 * MM))

    pieces = [box(0, 10, 0, 25), box(0, 10, 25, 50), box(10, 30, 50, 60),
              box(0, 10, 50, 60), box(30, 40, 50, 60), box(30, 40, 25, 50), box(30, 40, 0, 25)]
    for p in pieces:
        p.mat("coil_0")
    pieces[0].faces.Min(Z).name = "coil_0_in"
    pieces[6].faces.Min(Z).name = "coil_0_out"
    coil = Glue(pieces)
    iron = Box(Pnt(12 * MM, -10 * MM, 0), Pnt(28 * MM, 30 * MM, 45 * MM))
    iron.mat("iron")
    air = Box(Pnt(-20 * MM, -20 * MM, 0), Pnt(60 * MM, 40 * MM, 90 * MM))
    air.mat("air")
    air.faces.name = "outer"
    air.faces.Min(Z).name = "sym_z"
    geo = OCCGeometry(Glue([air - coil - iron, coil, iron]))
    return ngsolve.Mesh(geo.GenerateMesh(maxh=10 * MM))


@pytest.fixture(scope="module")
def iron_model():
    mesh = _iron_in_u_coil_mesh()
    laws = {"air": LinearLaw(), "coil_0": LinearLaw(), "iron": steel_law()}
    return Model3D(mesh, laws, coils=("coil_0",))


AT_SAT = 40000.0


def test_nonlinear_converges_and_reports(iron_model):
    sol = solve3d(iron_model, {"coil_0": AT_SAT})
    mesh = iron_model.mesh
    assert sol.converged
    assert sol.residuals[-1] < 1e-8 * sol.residuals[0]
    assert sol.ndof > 0 and sol.peak_rss_bytes > 0 and sol.seconds > 0
    bmag = ngsolve.sqrt(ngsolve.InnerProduct(ngsolve.curl(sol.a), ngsolve.curl(sol.a)))
    b_mean = ngsolve.Integrate(bmag, mesh, definedon=mesh.Materials("iron")) / \
        ngsolve.Integrate(ngsolve.CoefficientFunction(1.0), mesh, definedon=mesh.Materials("iron"))
    assert b_mean > 1.9


def test_nonconvergence_is_reported(iron_model):
    sol = solve3d(iron_model, {"coil_0": AT_SAT}, max_iter=1)
    assert not sol.converged
    assert sol.iterations == 1


def test_missing_law_raises(iron_model):
    model = dataclasses.replace(iron_model, laws={"air": LinearLaw(), "coil_0": LinearLaw()})
    with pytest.raises(ValueError, match="iron"):
        solve3d(model, {"coil_0": 1.0})


def test_warm_start_converges(iron_model):
    first = solve3d(iron_model, {"coil_0": AT_SAT})
    again = solve3d(iron_model, {"coil_0": AT_SAT}, initial=first.a)
    assert again.converged and again.iterations <= 2
