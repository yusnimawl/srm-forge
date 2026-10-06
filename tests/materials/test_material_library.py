import numpy as np
import pytest
from pydantic import ValidationError

from srmcore.materials.bh import process_bh
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


NEW = ("10JNEX900", "Hiperco50A", "Hiperco50HS_720C", "Hiperco50HS_740C", "Hiperco50HS_760C", "M43")


def test_m5e2_materials_are_in_the_library():
    assert set(NEW) <= set(available_materials())


@pytest.mark.parametrize("name", [n for n in available_materials() if n != "copper"])
def test_soft_magnetic_record_processes_and_reproduces_its_points(name):
    """Every soft-magnetic record passes the B-H pipeline and its fit goes through every data point."""
    m = load_material(name)
    curve, report = process_bh(m.bh, m.stacking_factor, m.saturation_polarisation)
    assert report.knot_max_relative_error < 1e-9
    b_eff = m.stacking_factor * np.asarray(m.bh.b) + (1 - m.stacking_factor) * 4e-7 * np.pi * np.asarray(m.bh.h)
    np.testing.assert_allclose(curve.h_of_b(b_eff), m.bh.h, rtol=1e-9)


@pytest.mark.parametrize("name", [n for n in available_materials() if n != "copper"])
def test_digitised_grade_b_records_state_their_digitisation_error(name):
    m = load_material(name)
    if m.confidence == "B":
        assert m.digitisation_error is not None and m.digitisation_error > 0


def test_m5e2_record_values():
    jnex = load_material("10JNEX900")
    assert (jnex.confidence, jnex.saturation_polarisation, jnex.stacking_factor, jnex.density) == ("B", 1.80, 0.90, 7490.0)
    assert jnex.digitisation_error == 0.025 and len(jnex.bh.h) == 32 and jnex.thickness == 0.0001
    a = load_material("Hiperco50A")
    assert (a.confidence, a.saturation_polarisation, a.digitisation_error) == ("B", 2.40, 0.015)
    assert a.bh.b[-6:] == (2.12, 2.19, 2.23, 2.27, 2.28, 2.30)
    assert "stacking_factor" in a.provisional_fields
    rows = {"720C": (1.82, 1.99, 2.15, 2.23, 2.29), "740C": (1.90, 2.03, 2.18, 2.23, 2.29),
            "760C": (1.93, 2.07, 2.19, 2.23, 2.30)}
    for suffix, b in rows.items():
        hs = load_material(f"Hiperco50HS_{suffix}")
        assert hs.confidence == "C" and hs.bh.h == (800.0, 1600.0, 4000.0, 8000.0, 16000.0) and hs.bh.b == b
        assert "no data below 800 A/m" in hs.provenance.source
    m43 = load_material("M43")
    assert m43.confidence == "C" and len(m43.bh.h) == 45 and m43.stacking_factor == 0.98


def test_digitisation_error_is_optional_and_bounded():
    m = load_material("M19")
    assert m.digitisation_error is None
    data = m.model_dump()
    assert SoftMagneticMaterial.model_validate({**data, "digitisation_error": 0.02}).digitisation_error == 0.02
    for bad in (-0.01, 0.5):
        with pytest.raises(ValidationError):
            SoftMagneticMaterial.model_validate({**data, "digitisation_error": bad})


def test_no20_and_vacoflux_records():
    no20 = load_material("NO20")
    assert (no20.confidence, no20.thickness, len(no20.bh.h)) == ("B", 0.0002, 18)
    assert no20.bh.h[-1] == 13000.0 and no20.bh.b[-1] == pytest.approx(1.8 + 4e-7 * np.pi * 13000.0, abs=1e-5)
    v48, v50 = load_material("Vacoflux48"), load_material("Vacoflux50")
    assert (v48.confidence, v48.digitisation_error, v48.bh.h[-1]) == ("B", 0.01, 8000.0)
    assert (v50.confidence, v50.bh.h) == ("C", (300.0, 800.0, 1600.0, 4000.0, 8000.0, 16000.0))
    assert v48.saturation_polarisation == v50.saturation_polarisation == 2.30
