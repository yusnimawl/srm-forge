"""em_validate and its parts (spec docs/superpowers/specs/2026-10-05-m5e1-label-budget-design.md)."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from map_fixtures import synthetic_map
from srmcore.maps.validation import KEYS, KeyPoint, js_laws, key_points
from srmcore.materials.laws import library_law
from srmcore.model.design import Design, MeshSettings, RegionMaterials
from srmcore.model.errors import InputError

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))


def test_key_points_follow_the_key_numbers():
    r = synthetic_map(n_angles=16)
    pts = {p.key: p for p in key_points(r, DESIGN.machine)}
    assert tuple(pts) == KEYS
    i_max = r.currents[-1]
    tau = 2 * math.pi / DESIGN.machine.n_rotor_poles
    assert pts["la"] == KeyPoint("la", 0.0, 0.05 * i_max)
    assert pts["lu"].angle == pytest.approx(tau / 2) and pts["lu"].current == pytest.approx(0.05 * i_max)
    assert pts["psi_max"] == KeyPoint("psi_max", 0.0, i_max)
    a, i = np.unravel_index(np.argmax(np.abs(r.torque_arkkio)), r.torque_arkkio.shape)
    assert pts["peak_torque"] == KeyPoint("peak_torque", float(r.angles[a]), float(r.currents[i]))


def test_js_laws_scale_both_iron_materials():
    d = DESIGN.model_copy(update={"machine": DESIGN.machine.model_copy(
        update={"materials": RegionMaterials(stator="M19", rotor="steel_1010")})})
    laws = js_laws(d, 1.02)
    for name in ("M19", "steel_1010"):
        base = library_law(name)
        assert laws[id(base)].js == pytest.approx(1.02 * base.js)
        assert laws[id(base)].bn == pytest.approx(base.bn)


def test_js_minus_two_percent_is_forbidden_by_the_m19_data():
    with pytest.raises(InputError):
        js_laws(DESIGN, 0.98)
