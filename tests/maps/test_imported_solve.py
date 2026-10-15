import math

import pytest
from conftest import make_8_6

from srmcore.maps.point import solve_point
from srmcore.mesh.api import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.iron import IronArc, IronLine
from srmcore.solvers.factory import make_solver
from srmcore.topology.dxf_io import import_dxf, write_dxf
from srmcore.topology.imported import _canonical, parametric_iron, to_segments

pytest.importorskip("ngsolve")

MM = 1e-3
I_MAX = 20.0


def _design(iron):
    p = make_8_6()
    return Design(machine=p.model_copy(update={"iron": iron}), mesh=MeshSettings(preset="screening"))


def _point(design, angle, current=I_MAX):
    static = build_machine_mesh(design)
    return solve_point(static, design, angle, {"A": current}, make_solver("ngsolve"))


def _canon(loop):
    return _canonical(list(to_segments(loop)), make_8_6())


def _circle(cx, cy, r):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(cx, cy)) for i in range(4))


def _grooved_outer(radius, n, depth, half_width):
    d = math.asin(half_width / radius)

    def at(r, a):
        return (r * math.cos(a), r * math.sin(a))

    segs = []
    for k in range(n):
        a, a_next = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        segs += [IronLine(start=at(radius, a - d), end=at(radius - depth, a)),
                 IronLine(start=at(radius - depth, a), end=at(radius, a + d)),
                 IronArc(start=at(radius, a + d), end=at(radius, a_next - d), center=(0.0, 0.0))]
    return tuple(segs)


def test_no_edit_point_matches():
    p = make_8_6()
    iron, _ = import_dxf(write_dxf(p), p)
    assert iron is not None
    plain, imported = _design(None), _design(iron)
    a0, b0 = _point(plain, 0.0), _point(imported, 0.0)
    a1, b1 = _point(plain, math.radians(7.5)), _point(imported, math.radians(7.5))
    peak = abs(a1.torque_arkkio)
    for a, b in ((a0, b0), (a1, b1)):
        # the imported path meshes the same outline with a slightly different node set
        assert b.psi[0] == pytest.approx(a.psi[0], rel=5e-5)
        assert b.torque_arkkio == pytest.approx(a.torque_arkkio, abs=5e-4 * peak)


def test_rotor_holes_leave_la_nearly_unchanged():
    p = make_8_6()
    r = (p.shaft_radius + p.rotor_yoke_outer_radius) / 2
    holes = tuple(_canon(_circle(r * math.cos(k * math.pi / 3), r * math.sin(k * math.pi / 3), 2 * MM)) for k in range(6))
    base = parametric_iron(p)
    i = 0.05 * I_MAX
    la_plain = _point(_design(base), 0.0, i).psi[0] / i
    la_holed = _point(_design(base.model_copy(update={"rotor_holes": holes})), 0.0, i).psi[0] / i
    assert abs(la_holed / la_plain - 1) < 0.02


def test_yoke_grooves_lower_psi():
    p = make_8_6()
    base = parametric_iron(p)
    outer = _canon(_grooved_outer(p.stator_outer_radius, 8, 1 * MM, 1 * MM))
    plain = _point(_design(base), 0.0).psi[0]
    grooved = _point(_design(base.model_copy(update={"stator_outer": outer})), 0.0).psi[0]
    assert grooved < plain
    assert (plain - grooved) / plain < 0.03
