import pytest

ngsolve = pytest.importorskip("ngsolve")

from end3d.team24 import Team24Params, team24_model  # noqa: E402
import team24_fixture as fx  # noqa: E402

COARSE = dict(maxh=10e-3, gap_maxh=3e-3)


def _steel_volume(mesh):
    return ngsolve.Integrate(mesh.MaterialCF({"steel": 1.0}, default=0.0), mesh)


def _iron_area_2d():
    m = fx.team24_mesh()
    area = fx._triangle_area(m.nodes, m.triangles)
    return area[(m.region == 1) | (m.region == 2)].sum()


@pytest.fixture(scope="module")
def full():
    return team24_model(Team24Params(**COARSE))


def test_iron_volume(full):
    assert _steel_volume(full.mesh) == pytest.approx(_iron_area_2d() * fx.DEPTH / 2, rel=5e-3)


@pytest.mark.parametrize("slab", [False, True])
def test_regions_and_faces_present(slab):
    model = team24_model(Team24Params(slab=slab, **COARSE))
    mats, bnds = set(model.mesh.GetMaterials()), set(model.mesh.GetBoundaries())
    assert {"steel", "air", "shaft", "gap_shell", *model.coils} <= mats
    assert set(model.laws) == mats
    coils = ("coil_0a", "coil_0b", "coil_1a", "coil_1b") if slab else ("coil_0", "coil_1")
    assert model.coils == coils
    faces = {"sym_z", "outer", "search", *[f"{c}_{e}" for c in coils for e in ("in", "out")]}
    assert faces <= bnds
    assert ("end_z" in bnds) == slab
    assert model.dirichlet == ("sym_z|end_z|outer" if slab else "sym_z|outer")


def test_fillet_changes_volume(full):
    filleted = team24_model(Team24Params(fillet=3e-3, **COARSE))
    v0, v1 = _steel_volume(full.mesh), _steel_volume(filleted.mesh)
    assert 0 < abs(v1 - v0) < 0.02 * v0
