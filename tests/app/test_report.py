import copy

import numpy as np
import pytest

from conftest import make_8_6
from srmapp.case import CaseInputs
from srmapp.report import IRON_UNCERTAINTY_WARN, findings, torque_ripple
from srmapp.requirements import Requirements
from srmcore.model.design import Design, MeshSettings
from srmweb.serialize import to_json
from web_support import REQ, evaluation


def inputs(**req):
    return CaseInputs(requirements=Requirements(**{**REQ, **req}),
                      design=Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def ev(**edits):
    e = to_json(evaluation("c1"))
    e.update(edits)
    return e


def by_id(fs):
    return {f.id: f for f in fs}


def run(e=None, inp=None, validation=None, losses=None, compare=None, anim=None):
    return findings(inp or inputs(), e or ev(), validation, losses, compare, anim)


def test_torque_ratio_below_margin_warns():
    f = by_id(run(ev(torque_ratio=0.9)))["torque_ratio"]
    assert f.level == "warn" and f.value == 0.9 and "0.9" in f.text


def test_requirements_met_give_ok():
    f = by_id(run(ev(torque_ratio=1.2, power_ratio=1.2, feasible=True)))
    assert [f[k].level for k in ("torque_ratio", "power_ratio", "feasible")] == ["ok"] * 3


def test_j_rms_above_limit_warns():
    f = by_id(run(ev(j_rms=7e6, j_limit=6e6)))["j_rms"]
    assert f.level == "warn" and f.value == pytest.approx(7.0) and f.unit == "A/mm²"


def test_mass_limit():
    assert by_id(run(ev(mass_kg=12.0), inputs(max_mass_kg=10.0)))["mass"].level == "warn"
    f = by_id(run(ev(mass_kg=8.0), inputs(max_mass_kg=10.0)))["mass"]
    assert f.level == "note" and f.value == pytest.approx(80)
    assert "mass" not in by_id(run(ev(mass_kg=8.0)))


def test_torque_ripple_hand_made():
    assert torque_ripple(np.array([2.0, 0, 0, 0]), 4) == 0.0
    assert torque_ripple(np.array([2.0, 0, 0, 0, 0, 0, 0, 0]), 2) == pytest.approx(4.0)
    assert torque_ripple(np.zeros(8), 2) is None


def pt(speed, tq, reached=True, beyond=False, unc=0.1, cdc=10.0, cac=5.0, iron=None, iron_w=5.0):
    return dict(speed_rpm=speed, torque_nm=tq, reached=reached, copper_dc_w=cdc, copper_ac_w=cac,
                iron=iron or {"stator_yoke": dict(hysteresis=3.0, classical=1.0, excess=1.0)},
                iron_w=iron_w, iron_uncertainty_rel=unc, beyond_fit_range=beyond)


def test_losses_rules():
    pts = [pt(1, 1, unc=0.4, beyond=True), pt(1, 2),
           pt(2, 1, reached=False), pt(2, 2, iron_w=10.0, iron={"rotor_pole": dict(hysteresis=1.0, classical=9.0, excess=0.0)})]
    f = by_id(run(losses=dict(points=pts, speeds_rpm=[1, 2], torque_fractions=[0.5, 1.0], srmapp_version="0.6.0")))
    assert (f["losses_unreached"].level, f["losses_unreached"].value) == ("warn", 1)
    assert (f["beyond_fit"].level, f["beyond_fit"].value) == ("warn", 1)
    assert f["iron_uncertainty"].level == "warn" and f["iron_uncertainty"].value == pytest.approx(40)
    assert IRON_UNCERTAINTY_WARN == 0.30
    assert f["loss_split"].value == pytest.approx(100 * 10 / 25)   # iron 10 W of 10 + 5 + 10 at speed index 1
    assert "rotor_pole" in f["iron_region"].text and "classical" in f["iron_region"].text
    pts[3]["reached"] = False
    f = by_id(run(losses=dict(points=pts, speeds_rpm=[1, 2], torque_fractions=[0.5, 1.0], srmapp_version="0.6.0")))
    assert f["loss_split"].value == pytest.approx(100 * 5 / 20)


def check(name, status):
    return dict(name=name, status=status, value=1.5, limit=1.0, detail="why")


def val(checks, label=None, total=None):
    return dict(label=label, checks=checks, engine_version="0.6.0",
                budget=dict(total=total or {}, rows=[]))


def test_validation_rules():
    f = by_id(run(validation=val([check("held_out", "fail"), check("b", "pass")])))
    assert f["check:held_out"].level == "warn" and "1.5" in f["check:held_out"].text and "why" in f["check:held_out"].text
    assert f["label"].level == "warn" and "checks" not in f and "check:b" not in f
    f = by_id(run(validation=val([check("b", "pass")], label="2D-verified")))
    assert f["checks"].level == "ok" and "label" not in f and "1 checks" in f["checks"].text


def test_budget_largest_row():
    v = val([], "x", total={"peak_torque": 0.07})
    v["budget"]["rows"] = [dict(source="mesh", rel={"peak_torque": 0.02}), dict(source="material", rel={"peak_torque": 0.06})]
    f = by_id(run(validation=v))["budget:peak_torque"]
    assert f.level == "note" and f.value == pytest.approx(6) and "material" in f.text


def test_dxf_top_three():
    rows = [dict(name=n, unit="", before=b, after=a) for n, b, a in
            [("a", 1.0, 1.1), ("b", 1.0, 1.5), ("c", 1.0, 0.8), ("d", 1.0, 1.01), ("e", 0, 5.0), ("f", None, 1.0), ("g", 1.0, 2.0)]]
    d = [f for f in run(compare=rows) if f.id == "dxf"]
    assert len(d) == 3 and [x.text.split()[0] for x in d] == ["g", "b", "c"]


def test_missing_parts():
    f = by_id(run(anim="frames cleared"))
    assert all(f[k].level == "missing" for k in ("losses_missing", "validation_missing", "animation_missing"))
    assert "frames cleared" in f["animation_missing"].text


def test_losses_stale():
    L = dict(points=[], speeds_rpm=[], torque_fractions=[], srmapp_version="0.5.9")
    assert by_id(run(ev(srmapp_version="0.6.0"), losses=L))["losses_stale"].level == "missing"
    assert "losses_stale" not in by_id(run(ev(srmapp_version="junk"), losses=L))


def test_old_evaluation_without_optional_fields():
    e = ev()
    for k in ("srmapp_version", "j_limit", "curves"):
        e.pop(k)
    e["envelope"].pop("waveforms")
    f = by_id(run(e))
    assert not {"ripple", "saturation", "j_rms"} & set(f)


def test_degenerate_values_give_no_finding():
    e = copy.deepcopy(ev(efficiency_base=None))
    e["curves"]["la_unsat"] = 0.0
    e["envelope"]["speeds_rpm"] = [3000.0, 6000.0]
    e["envelope"]["waveforms"] = dict(torque=[[0.0] * 8, [0.0] * 8])
    fs = run(e)
    f = by_id(fs)
    assert not {"saturation", "ripple", "efficiency_base"} & set(f)
    assert not any("nan" in x.text.lower() or "inf" in x.text.lower() for x in fs)
