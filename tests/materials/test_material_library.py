import pytest
from pydantic import ValidationError

from srmcore.materials.library import available_materials, load_material
from srmcore.materials.schema import BHTable, ConductorMaterial, SoftMagneticMaterial
from srmcore.model.design import RegionMaterials


def test_library_covers_default_region_materials():
    defaults = RegionMaterials()
    for name in (defaults.stator, defaults.rotor, defaults.shaft, defaults.coil):
        assert name in available_materials()


def test_m19_record():
    m = load_material("M19")
    assert isinstance(m, SoftMagneticMaterial)
    assert m.confidence == "C"
    assert "FEMM" in m.provenance.source
    assert len(m.bh.h) == len(m.bh.b) == 47
    assert m.bh.b[-1] == pytest.approx(2.3) and m.bh.h[-1] == pytest.approx(234024.751347)
    assert m.stacking_factor == 0.98


def test_steel_1010_and_copper_records():
    s = load_material("steel_1010")
    assert isinstance(s, SoftMagneticMaterial) and len(s.bh.h) == 38 and s.stacking_factor == 1.0
    cu = load_material("copper")
    assert isinstance(cu, ConductorMaterial)
    assert cu.resistivity == pytest.approx(1.7241e-8)
    assert cu.resistivity_at(120.0) == pytest.approx(1.7241e-8 * (1 + 0.00393 * 100))


def test_unknown_material_lists_available():
    with pytest.raises(KeyError, match="M19"):
        load_material("M270")


def test_bh_table_rejects_unpaired_points():
    with pytest.raises(ValidationError):
        BHTable(h=(0.0, 1.0, 2.0), b=(0.0, 1.0))


@pytest.mark.parametrize("name", available_materials())
def test_provisional_fields_match_provisional_sources(name):
    """Nothing invented ships looking sourced: a *_source says PROVISIONAL exactly when its field is listed."""
    m = load_material(name)
    marked = {k[: -len("_source")] for k, v in m.model_dump().items()
              if k.endswith("_source") and isinstance(v, str) and "PROVISIONAL" in v}
    assert marked == set(m.provisional_fields)
    assert m.cost_per_kg is None                        # no supplier quotes yet


def test_provisional_field_without_provisional_source_is_rejected():
    data = load_material("copper").model_dump()
    data["provisional_fields"] = ("density",)
    with pytest.raises(ValidationError, match="PROVISIONAL"):
        ConductorMaterial.model_validate(data)


def test_stacking_factor_is_required():
    data = load_material("M19").model_dump()
    del data["stacking_factor"]
    with pytest.raises(ValidationError):
        SoftMagneticMaterial.model_validate(data)


def test_digitisation_error_is_optional_and_bounded():
    m = load_material("M19")
    assert m.digitisation_error is None
    data = m.model_dump()
    assert SoftMagneticMaterial.model_validate({**data, "digitisation_error": 0.02}).digitisation_error == 0.02
    for bad in (-0.01, 0.5):
        with pytest.raises(ValidationError):
            SoftMagneticMaterial.model_validate({**data, "digitisation_error": bad})
