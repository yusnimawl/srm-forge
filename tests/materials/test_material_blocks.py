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


def test_10jnex900_strength_from_ou_2021():
    m = load_material("10JNEX900").mechanical
    assert m.strength == 570e6 and not m.brittle
    assert m.strength_confidence == "B" and m.confidence == "C"
    assert m.youngs_modulus >= 200e9 and m.poisson_ratio == 0.33


def test_10jnex900_conductivity_grade_c():
    t = load_material("10JNEX900").thermal
    assert t.conductivity == 18.6 and t.confidence == "C"
    assert t.specific_heat is None and t.expansion is None and t.conductivity_through_stack is None


def test_copper_and_steel_1010_blocks():
    cu = load_material("copper").thermal
    assert cu.conductivity == pytest.approx(391.1, abs=0.1) and cu.specific_heat == pytest.approx(385.2, abs=0.1)
    assert cu.expansion == pytest.approx(16.92e-6, rel=1e-3)
    st = load_material("steel_1010")
    assert st.thermal.conductivity == 49.8 and st.mechanical.strength == 305e6
    assert st.mechanical.confidence == "C" and st.mechanical.strength_confidence == "C"


def test_blocks_without_a_stated_temperature_carry_none():
    assert load_material("10JNEX900").mechanical.temperature_c is None
    assert load_material("10JNEX900").thermal.temperature_c is None
    assert load_material("steel_1010").thermal.temperature_c is None
    assert load_material("copper").thermal.temperature_c == 20.0
