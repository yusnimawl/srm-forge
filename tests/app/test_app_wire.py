import math

import pytest
from pydantic import TypeAdapter, ValidationError

from srmapp.wire import LitzWire, RectangularWire, RoundWire, Wire


def test_round_areas():
    w = RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3)
    assert w.kind == "round"
    assert w.copper_area == pytest.approx(math.pi * 1.0e-6 / 4)
    assert w.outer_area == pytest.approx(math.pi * 1.08e-3**2 / 4)


def test_round_insulation_cannot_be_thinner_than_the_copper():
    with pytest.raises(ValidationError, match="outer_diameter"):
        RoundWire(diameter=1.0e-3, outer_diameter=0.9e-3)


def test_rectangular_areas():
    w = RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.05e-3)
    assert w.copper_area == pytest.approx(2.0e-6)
    assert w.outer_area == pytest.approx(2.1e-3 * 1.1e-3)
    assert RectangularWire(width=2.0e-3, height=1.0e-3, insulation=0.0).outer_area == pytest.approx(2.0e-6)


def test_litz_areas():
    w = LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1e-3)
    assert w.copper_area == pytest.approx(60 * math.pi * 0.1e-3**2 / 4)
    assert w.outer_area == pytest.approx(math.pi * 1.1e-3**2 / 4)


def test_litz_bundle_must_hold_its_strands():
    with pytest.raises(ValidationError, match="outer_diameter"):
        LitzWire(strand_diameter=0.1e-3, strands=100, outer_diameter=0.5e-3)


@pytest.mark.parametrize("make", [
    lambda: RoundWire(diameter=1.0, outer_diameter=1.08),
    lambda: RectangularWire(width=2.0, height=1.0, insulation=0.05),
    lambda: LitzWire(strand_diameter=0.1e-3, strands=60, outer_diameter=1.1),
])
def test_millimetre_looking_sizes_are_rejected(make):
    with pytest.raises(ValidationError, match="millimetres"):
        make()


def test_positive_sizes_and_strands():
    with pytest.raises(ValidationError):
        RoundWire(diameter=0.0, outer_diameter=1e-3)
    with pytest.raises(ValidationError):
        LitzWire(strand_diameter=0.1e-3, strands=0, outer_diameter=1.1e-3)
    with pytest.raises(ValidationError):
        RectangularWire(width=2e-3, height=1e-3, insulation=-1e-5)


def test_union_parses_by_kind():
    w = TypeAdapter(Wire).validate_python({"kind": "litz", "strand_diameter": 1e-4, "strands": 60,
                                           "outer_diameter": 1.1e-3})
    assert isinstance(w, LitzWire)
    with pytest.raises(ValidationError):
        TypeAdapter(Wire).validate_python({"kind": "hexagonal", "diameter": 1e-3})
