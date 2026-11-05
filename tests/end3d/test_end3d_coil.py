import pytest

ngsolve = pytest.importorskip("ngsolve")
from netgen.occ import Box, Glue, OCCGeometry, Pnt, Z  # noqa: E402

from end3d.coil import coil_current_density, face_current  # noqa: E402

MM = 1e-3
AT = 120.0


def _u_coil_mesh(maxh=8 * MM):
    """U-shaped coil (two 10 x 20 mm sides, 50 mm long, 10 mm bridge) in an air box."""
    def box(x0, x1, z0, z1):
        return Box(Pnt(x0 * MM, 0, z0 * MM), Pnt(x1 * MM, 20 * MM, z1 * MM))

    pieces = [box(0, 10, 0, 25), box(0, 10, 25, 50), box(10, 30, 50, 60),
              box(0, 10, 50, 60), box(30, 40, 50, 60), box(30, 40, 25, 50), box(30, 40, 0, 25)]
    for p in pieces:
        p.mat("coil_0")
    pieces[0].faces.Min(Z).name = "coil_0_in"
    pieces[6].faces.Min(Z).name = "coil_0_out"
    pieces[0].faces.Max(Z).name = "section_a"
    pieces[6].faces.Max(Z).name = "section_b"
    coil = Glue(pieces)
    air = Box(Pnt(-20 * MM, -20 * MM, 0), Pnt(60 * MM, 40 * MM, 90 * MM))
    air.mat("air")
    air.faces.Min(Z).name = "mirror"
    air.faces.Max(Z).name = "outer"
    geo = OCCGeometry(Glue([air - coil, coil]))
    return ngsolve.Mesh(geo.GenerateMesh(maxh=maxh))


@pytest.fixture(scope="module")
def setup():
    mesh = _u_coil_mesh()
    return mesh, coil_current_density(mesh, "coil_0", AT)


def test_current_through_in_and_out(setup):
    mesh, j = setup
    assert face_current(mesh, j, "coil_0_in") == pytest.approx(-AT, rel=1e-6)
    assert face_current(mesh, j, "coil_0_out") == pytest.approx(AT, rel=1e-6)


def test_current_through_internal_section(setup):
    mesh, j = setup
    for face in ("section_a", "section_b"):
        assert abs(face_current(mesh, j, face)) == pytest.approx(AT, rel=1e-3)


def test_zero_outside_coil(setup):
    mesh, j = setup
    assert ngsolve.Integrate(ngsolve.InnerProduct(j, j), mesh, definedon=mesh.Materials("air")) == 0.0


def test_current_direction(setup):
    mesh, j = setup
    assert j(mesh(5 * MM, 10 * MM, 10 * MM))[2] > 0
    assert j(mesh(35 * MM, 10 * MM, 10 * MM))[2] < 0


def test_missing_names_raise(setup):
    mesh, _ = setup
    with pytest.raises(ValueError, match="coil_9"):
        coil_current_density(mesh, "coil_9", AT)
