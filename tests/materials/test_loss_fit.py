import math

import pytest
from m19_loss_fixture import m19_loss_data

from srmcore.materials import MissingLossData, loss_model
from srmcore.materials.library import available_materials, load_material
from srmcore.materials.loss import fit_loss


def _check_points(data, model):
    for p in data.points:
        got = model.sinusoid(p.b, p.f)
        assert abs(got - p.w_per_kg) / p.w_per_kg <= model.fit_error * (1 + 1e-9)


def test_fit_reproduces_points_10jnex900():
    model = loss_model("10JNEX900")
    _check_points(load_material("10JNEX900").loss, model)
    assert model.fit_error < 0.15
    assert 1.2 <= model.alpha <= 3.0 and model.k_h >= 0 and model.k_e >= 0


def test_fit_reproduces_points_m19():
    data = m19_loss_data()
    model = fit_loss(data, density=7650.0, thickness=0.00036)
    _check_points(data, model)
    assert model.fit_error < 0.15
    assert model.confidence == "C"


def test_kc_is_computed():
    model = loss_model("10JNEX900")
    mat = load_material("10JNEX900")
    expect = math.pi**2 * mat.loss.conductivity * mat.thickness**2 / (6 * mat.density)
    assert model.k_c == pytest.approx(expect)


def test_m19_has_no_shipped_loss():
    assert load_material("M19").loss is None
    with pytest.raises(MissingLossData, match="M19"):
        loss_model("M19")


def test_missing_loss_data():
    with pytest.raises(MissingLossData, match="Hiperco50A"):
        loss_model("Hiperco50A")


def test_existing_materials_unchanged():
    for name in available_materials():
        mat = load_material(name)
        if mat.kind != "soft_magnetic":
            continue
        if mat.loss is None:
            with pytest.raises(MissingLossData, match=name):
                loss_model(name)
        else:
            assert loss_model(name).fit_error < 0.15


def test_ranges_carried_to_model():
    data = m19_loss_data()
    model = fit_loss(data, density=7650.0, thickness=0.00036)
    assert model.b_range == data.b_range and model.frequency_range == data.frequency_range
    assert loss_model("10JNEX900").b_range == (0.2, 1.0)


def test_loss_data_validation():
    data = m19_loss_data()
    base = data.model_dump()
    cls = type(data)
    with pytest.raises(ValueError, match="at least 6"):
        cls(**{**base, "points": data.points[:5]})
    one_f = tuple(p for p in data.points if p.f == 50.0)
    with pytest.raises(ValueError, match="distinct frequencies"):
        cls(**{**base, "points": one_f})
    with pytest.raises(ValueError, match="b_range"):
        cls(**{**base, "b_range": (0.5, 1.5)})
    with pytest.raises(ValueError, match="frequency_range"):
        cls(**{**base, "frequency_range": (100.0, 1000.0)})
    with pytest.raises(ValueError, match="b_range"):
        cls(**{**base, "b_range": (1.5, 0.1)})
    with pytest.raises(ValueError, match="frequency_range"):
        cls(**{**base, "frequency_range": (1000.0, 50.0)})
