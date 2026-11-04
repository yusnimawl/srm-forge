import json

import pytest

pytest.importorskip("ngsolve")

import end3d.g1_team24 as g1  # noqa: E402

T, F = g1.MEASURED["torque"], g1.MEASURED["flux"]


def run(torque, flux, converged=True):
    return {"converged": converged, "skipped": False, "torque": torque, "flux": flux, "psi": 0.5, "ndof": 1}


def runs(scale=1.0, **over):
    """Nominal 3 N.m and 4e-4 Wb; every other run is the nominal times `scale` unless given in `over`."""
    out = {k: run(3.0 * scale, 4e-4 * scale) for k in g1.RUN_KEYS}
    out["nominal"] = run(3.0, 4e-4)
    out.update(over)
    return out


def test_budget_sums_rows():
    r = runs(1.0,
             mesh_coarse=run(3.03, 4.04e-4), mesh_fine=run(3.0, 4e-4),
             air_radius=run(3.03, 4e-4), air_end=run(3.0, 4.04e-4),
             js_hi=run(3.06, 4.0e-4),
             fillet=run(2.97, 4e-4), search_plus=run(3.0, 4.04e-4), search_minus=run(3.0, 3.96e-4),
             end_1mm=run(3.0, 4.0e-4), end_5mm=run(3.0, 4.0e-4))
    rows = g1.budget(r["nominal"], r)
    assert rows["air_box"]["torque"] == pytest.approx(0.01)
    assert rows["air_box"]["flux"] == pytest.approx(0.01)
    assert rows["material"]["torque"] == pytest.approx(0.02)
    assert rows["fillets"]["torque"] == pytest.approx(0.01)
    assert rows["search_coil"]["torque"] == 0.0 and rows["search_coil"]["flux"] == pytest.approx(0.01)
    assert rows["table_rounding"]["torque"] == pytest.approx(0.005 / T)
    assert rows["table_rounding"]["flux"] == pytest.approx(0.005e-4 / F)
    assert set(rows) == set(g1.ROWS)
    total = sum(v["torque"] for v in rows.values())
    assert g1.verdict(r["nominal"], {"torque": 3.0, "flux": 4e-4}, rows)["torque"]["budget_rel"] == pytest.approx(total)


def test_mesh_row_monotone_and_not():
    h = (g1.COARSE[0], g1.NOMINAL[0], g1.FINE[0])
    c, n, f = (3.0 + 0.01 * x ** 2 for x in h)      # error proportional to h^2, limit 3.0
    r = runs(mesh_coarse=run(c, 4e-4), nominal=run(n, 4e-4), mesh_fine=run(f, 4e-4))
    assert g1.budget(r["nominal"], r)["mesh"]["torque"] == pytest.approx((n - 3.0) / n, rel=1e-6)
    # not monotone: the distance to the next finer level
    r = runs(mesh_coarse=run(3.00, 4e-4), nominal=run(3.03, 4e-4), mesh_fine=run(3.02, 4e-4))
    assert g1.budget(r["nominal"], r)["mesh"]["torque"] == pytest.approx(0.01 / 3.03)


def test_verdict_pass_and_fail():
    r = runs()
    rows = g1.budget(r["nominal"], r)
    b_t = sum(v["torque"] for v in rows.values())
    b_f = sum(v["flux"] for v in rows.values())
    nom = {"converged": True, "torque": T * (1 - 0.999 * b_t), "flux": F * (1 - 0.999 * b_f)}
    v = g1.verdict(nom, {"torque": T, "flux": F}, rows)
    assert v["pass"] and v["torque"]["pass"] and v["flux"]["pass"]
    nom = {"converged": True, "torque": T * (1 - 1.001 * b_t), "flux": F * (1 - 0.999 * b_f)}
    v = g1.verdict(nom, {"torque": T, "flux": F}, rows)
    assert not v["pass"] and not v["torque"]["pass"] and v["flux"]["pass"]


def test_nonconverged_run_refused():
    r = runs(fillet=run(None, None, converged=False))
    rows = g1.budget(r["nominal"], r)
    with pytest.raises(ValueError, match="fillets"):
        g1.verdict(r["nominal"], {"torque": T, "flux": F}, rows)


def test_skipped_run_fails_gate():
    r = runs(js_hi={"converged": False, "skipped": True, "ndof": 9})
    rows = g1.budget(r["nominal"], r)
    with pytest.raises(ValueError, match="material"):
        g1.verdict(r["nominal"], {"torque": T, "flux": F}, rows)


def test_resume_does_not_rerun_converged(tmp_path, monkeypatch):
    path = tmp_path / "g1.json"
    calls = []

    def fake(spec, max_dofs, dry_run=False):
        calls.append(spec["key"])
        return run(3.0, 4e-4) if spec["key"] != "fillet" else run(None, None, converged=False)

    monkeypatch.setattr(g1, "_in_child", fake)
    assert g1.main(["--json", str(path)]) == 2      # a run failed: incomplete, not a verdict
    assert sorted(calls) == sorted(g1.RUN_KEYS)
    assert not json.loads(path.read_text())["verdict"]["pass"]
    calls.clear()
    g1.main(["--json", str(path)])
    assert calls == ["fillet"]


def test_resume_reruns_a_changed_run(tmp_path, monkeypatch):
    path = tmp_path / "g1.json"
    calls = []

    def fake(spec, max_dofs, dry_run=False):
        calls.append(spec["key"])
        return run(3.0, 4e-4)

    monkeypatch.setattr(g1, "_in_child", fake)
    g1.main(["--json", str(path)])
    calls.clear()
    monkeypatch.setitem(g1.RUNS, "fillet", ({"fillet": 1e-3}, g1.NOMINAL))
    monkeypatch.setitem(g1.RUNS, "hub_plus", (g1.RUNS["hub_plus"][0], (2.0, 10.0, 2.0, 8.0)))
    g1.main(["--json", str(path)])
    assert sorted(calls) == ["fillet", "hub_plus"]


def test_mesh_row_order_floor():
    """A fitted order below 1 is noise between levels: the row stays at the order-1 extrapolation, 5 x |f2 - f3| here."""
    f1, f2, f3 = 2.8440, 2.8425, 2.8410
    assert g1._richardson_distance(f1, f2, f3, (1.9, 1.5, 1.2)) == pytest.approx(5 * abs(f2 - f3) / f2)
    assert g1._richardson_distance(2.84251, f2, f3, (1.9, 1.5, 1.2)) == pytest.approx(5 * abs(f2 - f3) / f2)
