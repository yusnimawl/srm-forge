import math

import pytest
from conftest import make_8_6

from srmapp.case import CaseInputs, FixedWinding, evaluate_design, map_request
from srmapp.evaluate import END_IMAGE_FACTOR
from srmapp.requirements import Requirements
import types

import numpy as np

from srmapp.thermal import rate, rating_speeds, required_torques, thermal_context, check_requirement
from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.model.design import Design, MeshSettings, RegionMaterials


def test_required_torques_follow_the_requirements():
    req = Requirements(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0,
                       continuous_power_w=15_000.0)
    w_base = 3000 * 2 * math.pi / 60
    assert required_torques(req, 1000.0) == pytest.approx((15_000 / w_base, 95.5))
    w9 = 9000 * 2 * math.pi / 60
    assert required_torques(req, 9000.0) == pytest.approx((15_000 / w9, 30_000 / w9))


def test_no_continuous_requirement_gives_none():
    req = Requirements(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    assert required_torques(req, 6000.0)[0] is None


def test_rating_speeds_hold_base_and_max():
    req = Requirements(peak_power_w=209.4, peak_torque_nm=1.0, base_speed_rpm=2000.0, max_speed_rpm=6000.0)
    s = rating_speeds(req, 6)
    assert s[0] == 1000.0 and 2000.0 in s and s[-1] == 6000.0 and s == sorted(s)


WIRE = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)
IRON = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
DESIGN = Design(machine=make_8_6(materials=IRON, lamination_thickness=1.0e-4), mesh=MeshSettings(preset="screening"))


@pytest.mark.slow
def test_check_matches_rating_8_6(tmp_path):
    req = Requirements(peak_power_w=628.0, peak_torque_nm=3.0, base_speed_rpm=2000.0, max_speed_rpm=6000.0,
                       wires=[WIRE], phase_current_a=20.0, continuous_power_w=100.0)
    inputs = CaseInputs(requirements=req, design=DESIGN, winding=FixedWinding(turns=24, strands=1, paths=1, wire=0))
    ev = evaluate_design(inputs, cache_dir=tmp_path)
    assert ev.status == "ok"
    rating = rate(inputs, ev, n_angles=12, n_speeds=1, cache_dir=tmp_path)
    base = next(r for r in rating.rated if r.rpm == req.base_speed_rpm)
    w_base = req.base_speed_rpm * 2 * math.pi / 60
    ref, i_map, _ = map_request(inputs)
    result = with_end_winding(build_map(ref, i_map, cache_dir=tmp_path),
                              end_winding_inductance(ref.machine, image_factor=END_IMAGE_FACTOR))

    def check(factor):
        # peak requirement equal to the continuous one, so the check tests the continuous torque (and the peak at it)
        t = factor * base.continuous_nm
        r = req.model_copy(update=dict(continuous_power_w=t * w_base, peak_torque_nm=t, peak_power_w=t * w_base))
        ctx = thermal_context(r, ref, result, ev.winding, n_angles=12, cache_dir=tmp_path)
        return check_requirement(ctx, n_speeds=1)

    assert check(0.9).holds
    out = check(1.1)
    assert not out.holds and out.rpm in {x.rpm for x in rating.rated}


def _fake_ctx(req, hot_c):
    hs = lambda t: types.SimpleNamespace(temperature_c=t, location="coil")  # noqa: E731
    solver = types.SimpleNamespace(
        steady=lambda load: hot_c, hot_spot=lambda t: hs(t),
        transient=lambda start, load, dur, n: types.SimpleNamespace(hot_spot_c=np.full(n, hot_c), final=hot_c))
    return types.SimpleNamespace(req=req, limit=160.0, solver_for=lambda rpm, rows: (lambda: solver),
                                 load_at=lambda rpm, rows: (lambda torque: (lambda t: None)))


def test_no_continuous_requirement_is_noted_and_skipped():
    req = Requirements(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    out = check_requirement(_fake_ctx(req, 100.0), n_speeds=2)
    assert out.holds and out.rpm is None
    assert out.notes == ("no continuous power required: continuous not checked",)
    assert all(math.isnan(x) for x in out.continuous_hot_c) and len(out.peak_hot_c) == 3
    with_cont = req.model_copy(update=dict(continuous_power_w=15_000.0))
    assert check_requirement(_fake_ctx(with_cont, 100.0), n_speeds=2).notes == ()
    assert not check_requirement(_fake_ctx(req, 170.0), n_speeds=2).holds
