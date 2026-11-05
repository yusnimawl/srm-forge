import cmath
import math

import pytest

ngsolve = pytest.importorskip("ngsolve")

from end3d.coil import coil_current_density  # noqa: E402
from end3d.radial import _face, _phase_poles, ampere_turns, radial_model  # noqa: E402
from srmapp.references import make_8_6  # noqa: E402
from srmcore.maps.end_winding import coil_geometry  # noqa: E402
from srmcore.model.design import Design  # noqa: E402
from srmcore.topology.imported import iron_areas, parametric_iron  # noqa: E402
from srmcore.topology.radial import parametric_outline  # noqa: E402

SIZES = dict(h_gap=1e-3, h_iron=2e-3, h_end=6e-3, h_mid=12e-3)


def _design(**overrides):
    return Design(machine=make_8_6(**overrides))


def _vol(mesh, material, f=1.0):
    return ngsolve.Integrate(mesh.MaterialCF({material: f}, default=0.0), mesh)


@pytest.fixture(scope="module")
def full():
    return radial_model(_design(), 0.0, **SIZES)


@pytest.fixture(scope="module")
def slab():
    return radial_model(_design(), 0.0, slab=True, **SIZES)


def test_iron_volumes(full):
    d = _design()
    stator, rotor = iron_areas(parametric_iron(d.machine))
    h = d.machine.stack_length / 2
    assert _vol(full.mesh, "stator") == pytest.approx(stator * h, rel=5e-3)
    assert _vol(full.mesh, "rotor") == pytest.approx(rotor * h, rel=5e-3)


def test_rotor_rotation(full):
    d = _design()
    nr, phi = d.machine.n_rotor_poles, 0.1
    turned = radial_model(d, phi, **SIZES)

    def cmoment(mesh):
        r, a = ngsolve.sqrt(ngsolve.x ** 2 + ngsolve.y ** 2), ngsolve.atan2(ngsolve.y, ngsolve.x)
        return complex(_vol(mesh, "rotor", r ** nr * ngsolve.cos(nr * a)), _vol(mesh, "rotor", r ** nr * ngsolve.sin(nr * a)))

    m0, m1 = cmoment(full.mesh), cmoment(turned.mesh)
    assert _vol(turned.mesh, "rotor") == pytest.approx(_vol(full.mesh, "rotor"), rel=2e-3)
    assert abs(m1 - m0 * cmath.exp(1j * nr * phi)) < 5e-3 * abs(m0)
    assert abs(m1 - m0) > 0.1 * abs(m0)


def test_only_excited_phase_coils(full, slab):
    assert full.coils == ("coil_0", "coil_1")
    assert radial_model(_design(), 0.0, phase="B", **SIZES).coils == ("coil_0", "coil_1")
    assert slab.coils == ("coil_0a", "coil_0b", "coil_1a", "coil_1b")


def test_imported_iron_refused():
    m = make_8_6()
    d = Design(machine=m.model_copy(update={"iron": parametric_iron(m)}))
    with pytest.raises(NotImplementedError):
        radial_model(d, 0.0, **SIZES)


@pytest.mark.parametrize("slab", [False, True])
def test_radial_faces_complete(slab):
    d = _design()
    model = radial_model(d, 0.0, slab=slab, **SIZES)
    mesh, names = model.mesh, model.mesh.GetBoundaries()
    coil_faces = {f"{c}_{e}" for c in model.coils for e in ("in", "out")}
    z_top = max(mesh[v].point[2] for el in mesh.Elements(ngsolve.BND) for v in el.vertices)
    for el in mesh.Elements(ngsolve.BND):
        zs = [mesh[v].point[2] for v in el.vertices]
        name = names[el.index]
        if max(zs) < 1e-9:
            assert name == "sym_z" or name in coil_faces, name
        if slab and min(zs) > z_top - 1e-9:
            assert name == "end_z" or name in coil_faces, name
    assert ("end_z" in set(names)) == slab
    assert model.dirichlet == ("sym_z|end_z|outer" if slab else "sym_z|outer")
    assert {"sym_z", "outer", *coil_faces} <= set(names)
    if slab:
        assert z_top == pytest.approx(d.machine.stack_length / 2)
        r = max(math.hypot(mesh[v].point[0], mesh[v].point[1]) for el in mesh.Elements(ngsolve.BND) for v in el.vertices)
        assert r < d.machine.stator_outer_radius + 1e-6


def test_ampere_turns():
    d = _design()
    n = d.machine.turns_per_pole * 2.0
    assert ampere_turns(d, 2.0, slab=False) == {"coil_0": n, "coil_1": n}
    assert ampere_turns(d, 2.0, slab=True) == {"coil_0a": n, "coil_0b": -n, "coil_1a": n, "coil_1b": -n}


@pytest.mark.parametrize("coil", ["coil_0", "coil_1"])
def test_radial_ampere_turns_sign(full, coil):
    """Current enters on the 2D '+' side: J_z > 0 there, J_z < 0 on the '-' side (srmcore's winding sign).
    Both phase A poles have their + side at y > 0, polarity -1 included: the coils drive series flux."""
    mesh = full.mesh
    j = coil_current_density(mesh, coil, 1.0, order=1)
    jz_plus = ngsolve.Integrate(mesh.MaterialCF({coil: j[2] * ngsolve.IfPos(ngsolve.y, 1, 0)}, default=0.0), mesh)
    jz_minus = ngsolve.Integrate(mesh.MaterialCF({coil: j[2] * ngsolve.IfPos(-ngsolve.y, 1, 0)}, default=0.0), mesh)
    assert jz_plus > 0 > jz_minus


def test_slab_current_direction(slab):
    d = _design()
    mesh = slab.mesh
    for coil, n in ampere_turns(d, 1.0, slab=True).items():
        jz = ngsolve.Integrate(mesh.MaterialCF({coil: coil_current_density(mesh, coil, n, order=1)[2]}, default=0.0), mesh)
        assert jz * n > 0


def _area(side):
    return _face(side.boundary).mass


def test_slab_region_volumes(slab):
    d = _design()
    out = parametric_outline(d.machine)
    h = d.machine.stack_length / 2
    shell = math.pi * (out.band_outer_radius ** 2 - out.band_inner_radius ** 2) * h
    assert _vol(slab.mesh, "gap_shell") == pytest.approx(shell, rel=5e-3)
    _, plus, minus = _phase_poles(d, "A")[0]
    assert _vol(slab.mesh, "coil_0a") == pytest.approx(_area(plus) * h, rel=5e-3)
    assert _vol(slab.mesh, "coil_0b") == pytest.approx(_area(minus) * h, rel=5e-3)


def test_bridge_joins_the_coil_sides(full):
    """Above the stack and clearance the coil spans the pole, so it holds more than its two sides would."""
    d = _design()
    p = d.machine
    lo = p.stack_length / 2 + p.slot_liner_thickness
    _, plus, minus = _phase_poles(d, "A")[0]
    bridge = _vol(full.mesh, "coil_0", ngsolve.IfPos(ngsolve.z - lo, 1, 0))
    assert bridge > 1.5 * (_area(plus) + _area(minus)) * coil_geometry(p).build


def test_phase_b_coils_on_phase_b_poles():
    d = _design()
    model = radial_model(d, 0.0, phase="B", slab=True, **SIZES)
    _, plus, minus = _phase_poles(d, "B")[0]
    pts = [s.start for side in (plus, minus) for s in side.boundary]
    want = math.atan2(sum(q[1] for q in pts), sum(q[0] for q in pts))
    m = model.mesh
    got = math.atan2(_vol(m, "coil_0a", ngsolve.y) + _vol(m, "coil_0b", ngsolve.y),
                     _vol(m, "coil_0a", ngsolve.x) + _vol(m, "coil_0b", ngsolve.x))
    assert got == pytest.approx(want, abs=0.02)
    assert abs(want) > 0.1


def test_slab_refuses_outer_air_ring():
    m = make_8_6()
    d = Design(machine=m, mesh=Design(machine=m).mesh.model_copy(update={"outer_air_thickness": 0.01}))
    with pytest.raises(NotImplementedError):
        radial_model(d, 0.0, slab=True, **SIZES)
