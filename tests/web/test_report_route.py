import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import srmapp
import srmcore
from srmapp import field as fieldmod
from srmapp.sizing.generator import REFERENCE_TURNS
from test_web_animate import _animate, _frame, _wait, client, fake  # noqa: F401
from test_web_field_routes import _case
from web_support import REQ

K = 40 / (2 * REFERENCE_TURNS)


def _report(client, cid):
    return client.get(f"/api/cases/{cid}/report")


def test_report_unknown_case_404(client):
    assert _report(client, "nope").status_code == 404


def test_report_draft_without_evaluation_409(client):
    r = client.post("/api/cases", json={"origin": "reference", "name": "8/6", "requirements": REQ})
    assert r.status_code == 201, r.text
    r = _report(client, r.json()["id"])
    assert r.status_code == 409 and r.json()["detail"] == "the case has no evaluation"


def test_report_findings_and_versions(client):
    r = _report(client, _case(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["versions"] == {"srmcore": srmcore.__version__, "srmapp": srmapp.__version__, "srmweb": "0.7.0"}
    by_id = {f["id"]: f for f in body["findings"]}
    assert {"losses_missing", "validation_missing", "animation_missing"} <= set(by_id)
    assert "no animation run" in by_id["animation_missing"]["text"]
    assert body["animation_job_id"] is None and body["generated"].endswith("Z")


def test_report_picks_newest_cached_animation(client, fake, monkeypatch):
    cid = _case(client)
    old = _wait(client, _animate(client, cid, current=3.0))["id"]
    new = _wait(client, _animate(client, cid, current=4.0))["id"]
    monkeypatch.setattr(fieldmod, "cached_frame",
                        lambda design, angle, coil, **kw: _frame(angle, coil) if coil == pytest.approx(3.0 * K) else None)
    body = _report(client, cid).json()
    assert body["animation_job_id"] == old != new
    assert body["animation_current_a"] == 3.0
    assert "animation_missing" not in {f["id"] for f in body["findings"]}


def test_report_frames_cleared_reason(client, fake, monkeypatch):
    cid = _case(client)
    _wait(client, _animate(client, cid))
    monkeypatch.setattr(fieldmod, "cached_frame", lambda *a, **k: None)
    body = _report(client, cid).json()
    assert body["animation_job_id"] is None
    texts = [f["text"] for f in body["findings"] if f["id"] == "animation_missing"]
    assert texts and "cleared" in texts[0]
