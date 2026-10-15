from conftest import make_8_6
from srmcore.maps.identity import design_hash
from srmcore.model.design import Design, RadialSRMParams
from srmcore.model.iron import ImportedIron, IronArc

PARAMETRIC_HASH = "3e236049813f230f"


def _design(iron=None):
    m = make_8_6()
    return Design(machine=m.model_copy(update={"iron": iron}) if iron else m)


def _ring(r):  # a full circle as 4 quarter arcs, the stand-in for every contour
    pts = [(r, 0.0), (0.0, r), (-r, 0.0), (0.0, -r)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(0.0, 0.0)) for i in range(4))


IRON = ImportedIron(stator_outer=_ring(0.05), stator_bore=_ring(0.03), rotor_outer=_ring(0.029),
                    rotor_bore=_ring(0.008), rotor_holes=(_ring(0.001),))


def test_parametric_json_unchanged():
    d = _design()
    assert "iron" not in d.to_json()
    assert design_hash(d) == design_hash(Design.from_json(d.to_json()))
    assert design_hash(d) == PARAMETRIC_HASH


def test_iron_round_trips_json():
    p = make_8_6().model_copy(update={"iron": IRON})
    assert RadialSRMParams.model_validate_json(p.model_dump_json()) == p
    assert Design.from_json(_design(IRON).to_json()) == _design(IRON)


def test_iron_changes_hash():
    assert design_hash(_design(IRON)) != design_hash(_design())
