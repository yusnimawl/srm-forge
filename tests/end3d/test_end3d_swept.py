import dataclasses
import math

import pytest

ng = pytest.importorskip("ngsolve")

import team24_fixture as fx  # noqa: E402
from end3d import post  # noqa: E402
from end3d.coil import coil_current_density, face_current  # noqa: E402
from end3d.solve import solve3d  # noqa: E402
from end3d.swept import graded_layers  # noqa: E402
from end3d.team24 import (Team24Params, ampere_turns, rotor_pole_flux, team24_model,  # noqa: E402
                          team24_swept_model)
from srmcore.materials.laws import LinearLaw  # noqa: E402

SWEPT = dict(h_gap=3e-3, h_iron=3.5e-3, h_end=3e-3, h_mid=6e-3)
TET = dict(maxh=10e-3, gap_maxh=3e-3)


def test_graded_layers():
    z_end, z_top, h_end, h_mid, ratio = 0.0127, 0.1362, 1e-3, 3e-3, 1.3
    breaks = (0.0147, 0.0317)
    z = graded_layers(z_end, z_top, h_end, h_mid, ratio, breaks).z
    steps = [b - a for a, b in zip(z, z[1:])]
    assert z[0] == 0.0 and z[-1] == pytest.approx(z_top)
    assert all(s > 0 for s in steps)
    for v in (z_end, *breaks):
        assert min(abs(q - v) for q in z) < 1e-12
    i = min(range(len(z)), key=lambda j: abs(z[j] - z_end))
    assert steps[i - 1] == pytest.approx(h_end, rel=0.01) and steps[i] == pytest.approx(h_end, rel=0.01)
    below = [b - a for a, b in zip(z, z[1:]) if b <= breaks[-1] + 1e-12]
    assert max(below) <= h_mid * (1 + 1e-9)
    assert max(steps) <= 4 * h_mid * (1 + 1e-9) and max(steps) > 1.5 * h_mid     # far field keeps growing
    assert min(steps) >= 0.5 * h_end
    # growth away from the stack end is at most `ratio` per layer
    assert all(steps[j] <= ratio * steps[j + 1] * (1 + 1e-9) for j in range(i - 1))
    assert all(steps[j + 1] <= ratio * steps[j] * (1 + 1e-9) for j in range(i, len(steps) - 1))


def test_graded_layers_rejects_bad_breaks():
    for bad in (0.01, 0.0127, 0.2):
        with pytest.raises(ValueError, match="breaks"):
            graded_layers(0.0127, 0.1362, 1e-3, 3e-3, breaks=(bad,))


def _volume(mesh, name):
    return ng.Integrate(mesh.MaterialCF({name: 1.0}, default=0.0), mesh)


@pytest.mark.parametrize("slab", [False, True])
def test_swept_volumes_match_tet_model(slab):
    swept = team24_swept_model(Team24Params(slab=slab), **SWEPT)
    tet = team24_model(Team24Params(slab=slab, **TET))
    assert set(swept.mesh.GetMaterials()) == set(tet.mesh.GetMaterials())
    assert swept.coils == tuple(sorted(tet.coils)) or set(swept.coils) == set(tet.coils)
    assert swept.dirichlet == tet.dirichlet
    for name in dict.fromkeys(tet.mesh.GetMaterials()):
        assert _volume(swept.mesh, name) == pytest.approx(_volume(tet.mesh, name), rel=5e-3), name


@pytest.mark.parametrize("slab", [False, True])
def test_swept_faces_complete(slab):
    p = Team24Params(slab=slab)
    model = team24_swept_model(p, **SWEPT)
    mesh, h = model.mesh, p.depth / 2
    names = mesh.GetBoundaries()
    coil_faces = {f"{c}_{e}" for c in model.coils for e in ("in", "out")}
    assert coil_faces <= set(names)
    for el in mesh.Elements(ng.BND):
        zs = [mesh[v].point[2] for v in el.vertices]
        name = names[el.index]
        assert name != "default", "a boundary element without a name"
        if max(zs) < 1e-9:
            assert name == "sym_z" or name in coil_faces, name
        if slab and min(zs) > h - 1e-9:
            assert name == "end_z" or name in coil_faces, name
    area = ng.Integrate(1, mesh, ng.BND, definedon=mesh.Boundaries("search"))
    assert area == pytest.approx(fx.POLE_WIDTH_ROTOR * h, rel=5e-3)
    if not slab:
        at = ampere_turns(p, 1.0)
        for c in model.coils:
            j = coil_current_density(mesh, c, at[c], model.order)
            assert face_current(mesh, j, f"{c}_in") == pytest.approx(-at[c], rel=1e-6)
            assert face_current(mesh, j, f"{c}_out") == pytest.approx(at[c], rel=1e-6)


@pytest.mark.slow
@pytest.mark.parametrize("slab", [True, False])
def test_swept_matches_tet_linear(slab):
    """Slab: within 1 % of the tetrahedral model. Full model: the tetrahedral mesh is under-resolved (its
    coil_0 and coil_1 stack energies differ by 1.8 % though the problem is symmetric, the swept ones by 0.01 %),
    and with fixed J a conforming solve's co-energy rises with refinement, so the swept psi and torque lie at or
    above the tetrahedral ones and within +2 % (docs/r4-end-effect-results.md, "Swept mesh cross-check")."""
    if slab:
        p, swept_kw, tet_kw = Team24Params(slab=True), SWEPT, TET
    else:
        p = Team24Params(air_end_factor=0.5, air_radius_factor=1.25)
        swept_kw, tet_kw = dict(h_gap=3e-3, h_iron=9e-3, h_end=3e-3, h_mid=10e-3), TET
    results = []
    for model in (team24_swept_model(p, **swept_kw), team24_model(dataclasses.replace(p, **tet_kw))):
        model = dataclasses.replace(model, laws={k: (LinearLaw(1000.0) if k == "steel" else v)
                                                 for k, v in model.laws.items()})
        at = ampere_turns(p, 5.0)
        sol = solve3d(model, at)
        assert sol.converged
        results.append((post.flux_linkage(model, sol, model.coils, 5.0, at),
                        post.arkkio_torque(model, sol, fx.BAND_INNER, fx.BAND_OUTER),
                        rotor_pole_flux(model, sol)))
    if slab:
        for swept, tet in zip(*results):
            assert swept == pytest.approx(tet, rel=1e-2)
    else:
        for swept, tet in list(zip(*results))[:2]:
            assert tet <= swept <= 1.02 * tet


def test_swept_fillet_changes_volume():
    kw = dict(SWEPT, h_iron=1.5e-3)
    plain = team24_swept_model(Team24Params(slab=True), **kw)
    rounded = team24_swept_model(Team24Params(slab=True, fillet=3e-3), **kw)
    v0, v1 = _volume(plain.mesh, "steel"), _volume(rounded.mesh, "steel")
    tet0 = team24_model(Team24Params(slab=True, **TET))
    tet1 = team24_model(Team24Params(slab=True, fillet=3e-3, **TET))
    dv_tet = _volume(tet1.mesh, "steel") - _volume(tet0.mesh, "steel")
    # eight concave corners, each adding (1 - pi/4) r^2 over the half depth; the polygonal circles of the
    # swept mesh make a volume difference of this size (1e-4 of the steel) noisy at the 15 % level
    exact = 8 * (1 - math.pi / 4) * 3e-3 ** 2 * Team24Params().depth / 2
    assert 0 < abs(v1 - v0) < 0.02 * v0
    assert (v1 - v0) == pytest.approx(exact, rel=0.2)
    assert (v1 - v0) == pytest.approx(dv_tet, rel=0.2)
