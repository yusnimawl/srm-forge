import math

import pytest

from conftest import make_8_6

from srmapp.sizing.estimates import active_mass
from srmcore.materials.library import load_material
from srmcore.model.iron import IronArc
from srmcore.topology.imported import parametric_iron

MM = 1e-3


def _circle(cx, cy, r):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(cx, cy)) for i in range(4))


def test_rotor_holes_lower_mass():
    p = make_8_6()
    r = (p.shaft_radius + p.rotor_yoke_outer_radius) / 2
    holes = tuple(_circle(r * math.cos(k * math.pi / 3), r * math.sin(k * math.pi / 3), 2 * MM) for k in range(6))
    base = parametric_iron(p)
    plain = active_mass(p.model_copy(update={"iron": base}))
    holed = active_mass(p.model_copy(update={"iron": base.model_copy(update={"rotor_holes": holes})}))
    m = load_material(p.materials.rotor)
    want = 6 * math.pi * (2 * MM) ** 2 * p.stack_length * m.density * m.stacking_factor
    assert plain.rotor_iron - holed.rotor_iron == pytest.approx(want, rel=1e-9)
    assert holed.stator_iron == plain.stator_iron and holed.copper == plain.copper

