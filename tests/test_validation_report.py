import json
import sys
from email.message import Message
from importlib.metadata import version
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validation_report as vr  # noqa: E402

KEYS = ["la", "lu", "peak_torque", "psi_max"]


def _write_inputs(d: Path, m5a: Path, *, ci="success", femm_ratio=0.5, team_err=-13.1, drop=None):
    d.mkdir(parents=True, exist_ok=True)
    m5a.mkdir(parents=True, exist_ok=True)
    one = {k: 0.01 for k in KEYS}
    v = version("srmcore")
    files = {
        "em_validate_8_6.json": {"engine_version": v, "label": None, "material_grades": {"stator": "C", "rotor": "C"},
                                 "map_s": 1.0, "validate_s": 1.0,
                                 "checks": [{"name": "engine_version", "status": "fail", "value": None, "limit": None, "detail": ""},
                                            {"name": "preset", "status": "pass", "value": None, "limit": None, "detail": ""}],
                                 "budget": {"keys": KEYS, "values_2d": one, "values": one,
                                            "rows": [{"source": "mesh", "rel": one, "note": ""}], "total": one}},
        "team24.json": {"srmcore": v, "static_torque": {"model": 2.8, "measured": 3.22, "error_pct": team_err},
                        "rotor_flux": {"model": 1.0, "measured": 1.0, "error_pct": 0.0},
                        "current_rise_max_dev_pct": {"before": 18.6, "after": 17.3}},
        "femm.json": {"srmcore": v, "krishnan_8_6": {"worst_psi": 0.004, "worst_t_rel": 0.01, "worst_t_peak": 0.003, "ratio": femm_ratio}},
        "krishnan_6_4.json": {"srmcore": v, "rows": [{"quantity": "La", "unit": "mH", "current": 20.0, "measured": 1.0, "model_2d": 0.8,
                                        "model_after": 0.85, "error_before_pct": -20.0, "unc_before_pct": 5.0,
                                        "error_after_pct": -15.0, "unc_after_pct": 6.0, "measurement_stated": False}]},
        "speed.json": {"srmcore": v, "cpu": "x", "logical_cpus": 16, "workers": 8, "date": "2026-10-06",
                       "runs": [{"design": "8_6", "item": it, "seconds": 50.0} for it in vr.SPEED_ITEMS]},
        "speed_budgets.json": {"screening": 90.0, "full": 3600.0, "full_extras": 1800.0},
        "ci.json": {"tag": "v0.4.0", "run_url": "https://example.invalid/run", "result": ci},
    }
    for name, data in files.items():
        if name != drop:
            (d / name).write_text(json.dumps(data))
    (m5a / "heldout.jsonl").write_text(json.dumps({"design": "8_6", "n_samples": 64, "held_out_psi": 0.001,
                                                   "held_out_torque": 0.005, "band_radius": 0.002}) + "\n")


def test_all_gated_rows_passing_is_pass(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "PASS"
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    for heading in ("## Engine", "## Material library", "## M5a", "## M5b", "## M5c", "## M5d",
                    "## EM validation", "## Speed", "## CI"):
        assert heading in text


def test_failing_gated_row_fails_the_report(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m", femm_ratio=1.2)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"


def test_report_only_rows_never_fail_it(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m", team_err=-60.0)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "PASS"


def test_pending_ci_gives_pending(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m", ci="pending")
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "PENDING"


@pytest.mark.parametrize("drop", ["ci.json", "speed.json", "femm.json", "em_validate_8_6.json"])
def test_missing_gated_input_fails_without_crashing(tmp_path, drop):
    _write_inputs(tmp_path / "v", tmp_path / "m", drop=drop)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"
    assert "missing" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_unset_speed_budget_is_missing(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    (tmp_path / "v" / "speed_budgets.json").write_text(json.dumps({"screening": None, "full": None, "full_extras": None}))
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"


def _rewrite(tmp_path, name, change):
    p = tmp_path / "v" / name
    data = json.loads(p.read_text())
    change(data)
    p.write_text(json.dumps(data))


@pytest.mark.parametrize("name, change", [
    ("em_validate_8_6.json", lambda d: d.update(engine_version="0.0.1")),
    ("speed.json", lambda d: d.update(srmcore="0.0.1")),
    ("femm.json", lambda d: d.update(srmcore="0.0.1")),
])
def test_stale_gated_input_fails(tmp_path, name, change):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    _rewrite(tmp_path, name, change)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"
    assert "stale" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_report_only_version_never_gates(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    _rewrite(tmp_path, "team24.json", lambda d: d.update(srmcore="0.0.1"))
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "PASS"


@pytest.mark.parametrize("name, change", [
    ("femm.json", lambda d: d.clear() or d.update(srmcore=version("srmcore"))),
    ("speed.json", lambda d: d.update(runs=[])),
    ("speed.json", lambda d: d.update(runs=[r for r in d["runs"] if r["item"] != "full_extras"])),
    ("em_validate_8_6.json", lambda d: d.update(checks=[])),
])
def test_empty_gated_evidence_fails(tmp_path, name, change):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    _rewrite(tmp_path, name, change)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"


def test_licence_helper_fallbacks():
    def md(**fields):
        m = Message()
        for k, v in fields.items():
            for x in (v if isinstance(v, list) else [v]):
                m[k.replace("_", "-")] = x
        return m
    assert vr.licence(md(License_Expression="MIT")) == "MIT"
    assert vr.licence(md(Classifier=["Programming Language :: Python", "License :: OSI Approved :: BSD License",
                                     "License :: OSI Approved :: MIT License"])) == "BSD License / MIT License"
    assert vr.licence(md(License="Apache 2.0")) == "Apache 2.0"
    assert vr.licence(md(License="Copyright (c) 2020\nLong licence text " * 20)) == "not stated"
    assert vr.licence(md()) == "not stated"


def test_m5a_plots_are_linked_when_present(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    (tmp_path / "m" / "convergence_8_6.png").write_bytes(b"")
    vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "out" / "report.md")
    assert "../m/convergence_8_6.png" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")


def test_null_budget_values_fail_without_crashing(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    p = tmp_path / "v" / "em_validate_8_6.json"
    data = json.loads(p.read_text())
    none = {k: None for k in KEYS}
    data["budget"].update(values_2d=none, total=none, rows=[{"source": "mesh", "rel": none, "note": ""}])
    data["checks"].append({"name": "budget_finite", "status": "fail", "value": None, "limit": None, "detail": ""})
    p.write_text(json.dumps(data))
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"
    assert (tmp_path / "report.md").is_file()
