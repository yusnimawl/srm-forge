import math

import numpy as np
import pytest

import krishnan_6_4 as k64
from srmcore.fields.solution import SolveStatus
from srmcore.maps.end_winding import coil_geometry
from srmcore.model.validator import validate_params


def _errors(p):
    return {(i.parameter, i.rule) for i in validate_params(p) if i.severity == "error"}


@pytest.mark.parametrize("bore", ["book", "dissertation"])
def test_machine_dimensions(bore):
    p = k64.machine(bore)
    b, sy = k64.BORES[bore]
    assert p.bore_radius == pytest.approx(b / 2)
    assert p.stator_yoke_thickness == sy
    assert p.shaft_diameter == pytest.approx(0.02856)
    assert p.rotor_outer_radius - p.rotor_yoke_outer_radius == pytest.approx(0.02725)   # rotor pole height
    assert {r for _, r in _errors(p)} == {"self_starting"}      # nothing else fails


@pytest.mark.parametrize("packing", [0.35, 0.5, 0.65])
def test_coil_area_matches_packing(packing):
    p = k64.machine(packing=packing)
    assert coil_geometry(p).area == pytest.approx(268 * k64.AWG19_AREA / packing, rel=1e-4)


def test_packing_too_low_is_an_error():
    with pytest.raises(ValueError, match="packing"):
        k64.machine(packing=0.05)


def test_point_table_definitions():
    class R:  # minimal PointResult stand-in
        def __init__(self, psi, w, status=SolveStatus.OK):
            self.psi, self.coenergy, self.status = np.array([psi]), w, status
    pts = {}
    for i in k64.CURRENTS:
        pts[(0.0, i)] = R(0.5 * i, 2.0 * i)
        pts[(math.pi / 4, i)] = R(0.04 * i, 0.5 * i)
    t = k64.point_table(pts, k64.machine())
    assert np.allclose(t["La"], 0.5) and np.allclose(t["Lu"], 0.04)
    assert np.allclose(t["T_avg"], 12 * 1.5 * np.array(k64.CURRENTS) / (2 * math.pi))
    pts[(0.0, 10.0)] = R(5.0, 20.0, SolveStatus.NONCONVERGED)
    with pytest.raises(RuntimeError, match="10"):
        k64.point_table(pts, k64.machine())


def test_corrected_adds_l_end_to_inductances_only():
    t = {"La": np.array([0.8, 0.1, 0.07]), "Lu": np.array([0.04] * 3), "T_avg": np.array([1.0, 2.0, 3.0])}
    c = k64.corrected(t, 0.005)
    assert np.allclose(c["La"], t["La"] + 0.005) and np.allclose(c["Lu"], t["Lu"] + 0.005)
    assert np.array_equal(c["T_avg"], t["T_avg"])
