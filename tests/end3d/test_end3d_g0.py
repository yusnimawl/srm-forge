import json
from types import SimpleNamespace

import pytest

pytest.importorskip("ngsolve")
from netgen.meshing import NgException  # noqa: E402

import end3d.g0_timing as g0  # noqa: E402


def _stub(monkeypatch, build, ndof=10):
    monkeypatch.setattr(g0, "_build", build)
    monkeypatch.setattr(g0, "_ndof", lambda model: ndof)
    monkeypatch.setattr(g0, "_nelements", lambda model: 5)

    def no_solve(*a, **k):
        raise AssertionError("solver must not run")
    monkeypatch.setattr(g0, "solve3d", no_solve)


def test_skips_level_over_max_dofs(monkeypatch, tmp_path):
    _stub(monkeypatch, lambda maxh: SimpleNamespace(params=None, model=None))
    out = tmp_path / "g0.json"
    assert g0.main(["--max-dofs", "1", "--json", str(out)]) == 0
    data = json.loads(out.read_text())
    assert [lv["skipped"] for lv in data["levels"]] == [True] * 3
    assert all(lv["ndof"] == 10 for lv in data["levels"])


def test_meshing_failure_is_recorded_and_next_level_runs(monkeypatch, tmp_path):
    def build(maxh):
        if maxh == 2.8e-3:
            raise NgException("too many attempts in domain")
        return SimpleNamespace(params=None, model=None)
    _stub(monkeypatch, build)
    out = tmp_path / "g0.json"
    assert g0.main(["--max-dofs", "1", "--json", str(out)]) == 0
    lv = json.loads(out.read_text())["levels"]
    assert len(lv) == 3
    assert "too many attempts" in lv[1]["failed"]
    assert lv[2]["skipped"] is True
