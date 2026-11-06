import pytest
from pydantic import ValidationError

from srmcore.materials.library import load_material
from srmcore.materials.schema import MechanicalData, Provenance

PROV = Provenance(source="test")


def _mech(**kw):
    base = dict(youngs_modulus=200e9, poisson_ratio=0.3, yield_strength=300e6, provenance=PROV,
                confidence="B", strength_confidence="B")
    return MechanicalData(**{**base, **kw})


def test_ductile_needs_yield():
    with pytest.raises(ValidationError):
        _mech(yield_strength=None, tensile_strength=400e6)


def test_brittle_needs_tensile():
    with pytest.raises(ValidationError):
        _mech(brittle=True, yield_strength=300e6, tensile_strength=None)


def test_strength_picks_by_flag():
    assert _mech(tensile_strength=400e6).strength == 300e6
    assert _mech(brittle=True, tensile_strength=400e6).strength == 400e6


@pytest.mark.parametrize("nu", [0.0, 0.5])
def test_poisson_bounds(nu):
    with pytest.raises(ValidationError):
        _mech(poisson_ratio=nu)


def test_blocks_default_none():
    m = load_material("M19")
    assert m.mechanical is None and m.thermal is None
