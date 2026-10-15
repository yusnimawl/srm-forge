import math

import numpy as np
import pytest
from conftest import make_8_6

from srmcore.mesh.api import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.iron import ImportedIron, IronArc, IronLine
from srmcore.topology.imported import from_segments, parametric_iron, to_segments
from srmcore.topology.radial import build_outline

MM = 1e-3


def _circle(cx, cy, r):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(cx, cy)) for i in range(4))


def _grooved_outer(radius, n, depth, half_width):
    """Outer circle with n V-notches, one centred on every 2*pi/n."""
    d = math.asin(half_width / radius)

    def at(r, a):
        return (r * math.cos(a), r * math.sin(a))

    segs = []
    for k in range(n):
        a, a_next = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        left, apex, right = at(radius, a - d), at(radius - depth, a), at(radius, a + d)
        segs += [IronLine(start=left, end=apex), IronLine(start=apex, end=right),
                 IronArc(start=right, end=at(radius, a_next - d), center=(0.0, 0.0))]
    return tuple(segs)


def _area(static, name):
    rid = static.region_names.index(name)
    out = 0.0
    for part in (static.stator, static.rotor):
        sel = part.region_ids == rid
        if not sel.any():
            continue
        t = part.nodes[part.triangles[sel]]
        out += 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                            - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1])).sum()
    return out


def test_parametric_outline_unchanged(reference_design):
    o = build_outline(reference_design)
    assert o.stator_outer_boundary is None and o.rotor_inner_boundary is None
    assert o.stator_holes == () and o.rotor_holes == ()
    assert "iron_detail" not in o.refinement_features


def test_parametric_iron_matches_outline(reference_design):
    p = reference_design
    o = build_outline(p)
    for got, want in ((to_segments(parametric_iron(p).stator_bore), o.stator_inner_boundary),
                      (to_segments(parametric_iron(p).rotor_outer), o.rotor_outer_boundary)):
        assert len(got) == len(want)
        for a, b in zip(got, want):
            assert type(a) is type(b)
            assert a.start == pytest.approx(b.start, abs=1e-12) and a.end == pytest.approx(b.end, abs=1e-12)
    assert from_segments(to_segments(parametric_iron(p).stator_bore)) == parametric_iron(p).stator_bore


def test_parametric_iron_reproduces_parametric_outline_regions():
    p = make_8_6()
    plain = Design(machine=p, mesh=MeshSettings(preset="screening"))
    swapped = Design(machine=p.model_copy(update={"iron": parametric_iron(p)}), mesh=plain.mesh)
    a, b = build_machine_mesh(plain), build_machine_mesh(swapped)
    assert "stator_hole_air" not in b.region_names and "rotor_hole_air" not in b.region_names
    for name in ("stator_iron", "rotor_iron", "shaft"):
        assert _area(b, name) == pytest.approx(_area(a, name), rel=1e-6)


def test_rotor_hole_meshes():
    p = make_8_6()
    r = (p.shaft_radius + p.rotor_yoke_outer_radius) / 2
    holes = tuple(_circle(r * math.cos(k * math.pi / 3), r * math.sin(k * math.pi / 3), 2 * MM) for k in range(6))
    base = parametric_iron(p)
    design = Design(machine=p.model_copy(update={"iron": base.model_copy(update={"rotor_holes": holes})}),
                    mesh=MeshSettings(preset="screening"))
    plain = build_machine_mesh(Design(machine=p, mesh=design.mesh))
    static = build_machine_mesh(design)
    want = 6 * math.pi * (2 * MM) ** 2
    assert _area(static, "rotor_hole_air") == pytest.approx(want, rel=0.01)
    assert _area(static, "rotor_iron") == pytest.approx(_area(plain, "rotor_iron") - want, rel=0.01 * want / _area(plain, "rotor_iron") + 1e-3)
    assert static.region_kind["rotor_hole_air"] == "air" and static.region_part["rotor_hole_air"] == "rotor"


def test_yoke_groove_keeps_od_dirichlet():
    p = make_8_6()
    depth, half = 1 * MM, 1 * MM
    outer = _grooved_outer(p.stator_outer_radius, 8, depth, half)
    base = parametric_iron(p)
    design = Design(machine=p.model_copy(update={"iron": base.model_copy(update={"stator_outer": outer})}),
                    mesh=MeshSettings(preset="screening"))
    static = build_machine_mesh(design)
    nodes = static.stator.nodes[np.unique(static.outer_edges)]
    assert np.hypot(nodes[:, 0], nodes[:, 1]) == pytest.approx(p.stator_outer_radius, abs=1e-9)
    # triangle between chord and apex plus the circular segment above the chord
    r = p.stator_outer_radius
    d = math.asin(half / r)
    sagitta = r * (1 - math.cos(d))
    notch = half * (depth - sagitta) + (r * r / 2) * (2 * d - math.sin(2 * d))
    assert _area(static, "stator_hole_air") == pytest.approx(8 * notch, rel=0.01)
    assert static.region_kind["stator_hole_air"] == "air"
