import pytest

ngsolve = pytest.importorskip("ngsolve")

from end3d.team24 import Team24Params, ampere_turns, team24_model  # noqa: E402
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


@pytest.mark.parametrize("slab", [False, True])
def test_boundary_faces_complete(slab):
    p = Team24Params(slab=slab, **COARSE)
    model = team24_model(p)
    mesh, h = model.mesh, p.depth / 2
    names = mesh.GetBoundaries()
    coil_faces = {f"{c}_{e}" for c in model.coils for e in ("in", "out")}
    for el in mesh.Elements(ngsolve.BND):
        zs = [mesh[v].point[2] for v in el.vertices]
        name = names[el.index]
        if max(zs) < 1e-9:
            assert name == "sym_z" or name in coil_faces, name
        if slab and min(zs) > h - 1e-9:
            assert name == "end_z" or name in coil_faces, name
    if slab:
        assert max(max(mesh[v].point[0] ** 2 + mesh[v].point[1] ** 2 for v in el.vertices)
                   for el in mesh.Elements(ngsolve.VOL)) ** 0.5 < p.r_stator_out + 1e-6


def test_ampere_turns():
    n = 350 * 2.0
    assert ampere_turns(Team24Params(), 2.0) == {"coil_0": n, "coil_1": n}
    assert ampere_turns(Team24Params(slab=True), 2.0) == {"coil_0a": n, "coil_0b": -n, "coil_1a": n, "coil_1b": -n}


def test_gap_shell_overlap_rejected():
    with pytest.raises(ValueError, match="gap_shell"):
        team24_model(Team24Params(r_rotor_tip=52e-3, **COARSE))
