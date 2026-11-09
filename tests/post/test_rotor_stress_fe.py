"""Gate V6: the analytic rotor stress against a test-only 2D elastic FE (spec R5 section 8)."""
import json
import math
import multiprocessing
import os
from pathlib import Path

import numpy as np
import pytest

import rotor_elastic_fe as fe
from conftest import make_12_8, make_8_6
from rotor_elastic_fe import elastic_fe_mesh, rotor_elastic_fe, rotor_sector_fe, sector_fe
from srmcore.materials.library import load_material
from srmcore.mesh.static import build_static_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.post.rotor_stress import OVERSPEED, _disc_rim_displacement, gap_closure, rotor_stress

RHO, E, NU = 7490.0, 200e9, 0.33
OMEGA = 2 * math.pi * 12000 / 60
MECH = load_material("10JNEX900").mechanical
VALIDATION = Path(__file__).parents[2] / "docs" / "validation"
SWEEP = VALIDATION / "rotor_sweep.json"
HELD_OUT = VALIDATION / "rotor_heldout_designs.json"
HELD_OUT_FE = VALIDATION / "rotor_heldout_results.json"


def test_fe_annulus_against_closed_form():
    a, b, nr, nt = 0.02, 0.05, 60, 240
    r = np.linspace(a, b, nr + 1)
    th = np.linspace(0, 2 * math.pi, nt, endpoint=False)
    nodes = np.array([(ri * math.cos(t), ri * math.sin(t)) for ri in r for t in th])
    idx = lambda i, j: i * nt + j % nt
    tris = []
    for i in range(nr):
        for j in range(nt):
            tris += [(idx(i, j), idx(i, j + 1), idx(i + 1, j + 1)), (idx(i, j), idx(i + 1, j + 1), idx(i + 1, j))]
    result = elastic_fe_mesh(nodes, np.array(tris), RHO, E, NU, OMEGA, a, b)
    hoop = RHO * OMEGA**2 / 4 * ((3 + NU) * b**2 + (1 - NU) * a**2)
    assert result.bore_peak == pytest.approx(hoop, rel=0.01)
    assert result.tip_displacement == pytest.approx(_disc_rim_displacement(a, b, RHO, OMEGA, NU, E, 0.0), rel=0.01)


def test_sector_fe_annulus_against_closed_form():
    a, b, half = 0.02, 0.05, math.pi / 6
    c, s = math.cos(half), math.sin(half)
    origin = (0.0, 0.0)
    curves = [("line", (a, 0.0), (b, 0.0), "cut"), ("arc", (b, 0.0), (b * c, b * s), origin, "rim"),
              ("line", (b * c, b * s), (a * c, a * s), "cut"), ("arc", (a * c, a * s), (a, 0.0), origin, "bore")]
    sizes = {name: (5e-4, 0.25) for name in ("cut", "rim", "bore")}
    result = sector_fe(curves, sizes, half, a, b, RHO, E, NU, OMEGA)
    hoop = RHO * OMEGA**2 / 4 * ((3 + NU) * b**2 + (1 - NU) * a**2)
    assert result.bore_peak == pytest.approx(hoop, rel=1e-4)
    assert result.tip_displacement == pytest.approx(_disc_rim_displacement(a, b, RHO, OMEGA, NU, E, 0.0), rel=1e-4)


def test_sector_fe_matches_the_whole_rotor():
    machine = make_8_6()
    static = build_static_mesh(Design(machine=machine, mesh=MeshSettings(preset="screening")))
    whole = rotor_elastic_fe(static, RHO, E, NU, OMEGA, machine)
    sector = rotor_sector_fe(machine, RHO, E, NU, OMEGA)
    assert sector.bore_peak == pytest.approx(whole.bore_peak, rel=0.03)
    assert sector.tip_displacement == pytest.approx(whole.tip_displacement, rel=0.01)


def _analytic(row):
    """The model at the sweep speed; check speed equal to the FE speed, as rotor_stress applies 1.2 x its argument."""
    machine = make_8_6(**row["params"])
    rpm = fe.OMEGA * 60 / (2 * math.pi)
    mech = MECH.model_copy(update={"poisson_ratio": fe.NU, "youngs_modulus": fe.E})
    return (rotor_stress(machine, fe.RHO, mech, rpm / OVERSPEED),
            gap_closure(machine, fe.RHO, mech, None, None, rpm, 20.0, 20.0).centrifugal)


def _assert_pass_rule(row, bore, root, tip, peak, label):
    st, growth = _analytic(row)
    assert st.status == "ok", label
    assert st.bore_stress == pytest.approx(bore, rel=0.15), label
    assert st.root_stress == pytest.approx(root, rel=0.15), label
    assert growth == pytest.approx(tip, rel=0.15), label
    assert max(st.bore_stress, st.root_stress) >= 0.95 * peak, label


def _held_out():
    designs = json.loads(HELD_OUT.read_text())
    results = json.loads(HELD_OUT_FE.read_text())
    assert [d["params"] for d in designs] == [r["params"] for r in results]
    return designs, results


def test_model_against_the_recorded_held_out_fe():
    designs, results = _held_out()
    assert {d["kind"] for d in designs} == {"corner", "corner_taper0", "boundary", "face", "interior"}
    for d, r in zip(designs, results):
        _assert_pass_rule(r, r["bore"][-1], r["root"][-1], r["tip"][-1], r["peak"], d["kind"])


def test_model_against_the_first_sweep_inside_the_box():
    # the LHS rounds of the first box; the designs inside the present box
    rows = [row for row in json.loads(SWEEP.read_text()) if _analytic(row)[0].status == "ok"]
    assert len(rows) > 100
    for row in rows:
        _assert_pass_rule(row, row["bore"][-1], row["root"][-1], row["tip"][-1], row["peak"], row["set"])


@pytest.mark.slow
def test_fe_convergence_and_pass_rule_on_the_held_out_designs():
    designs, _ = _held_out()
    with multiprocessing.get_context("spawn").Pool(os.cpu_count()) as pool:
        solved = pool.map(fe.sweep_point, [d["params"] for d in designs], chunksize=4)
    for d, new in zip(designs, solved):
        for key in ("bore", "root"):
            assert abs(new[key][-1] / new[key][-2] - 1) < 0.02
        assert new["peak"] <= 1.001 * max(new["bore"][-1], new["root"][-1])   # the peak is on the fillet or the bore
        _assert_pass_rule(new, new["bore"][-1], new["root"][-1], new["tip"][-1], new["peak"], d["kind"])


@pytest.mark.slow
@pytest.mark.parametrize("make", [make_8_6, make_12_8])
def test_sector_against_the_whole_rotor_at_reference(make):
    machine = make()
    static = build_static_mesh(Design(machine=machine, mesh=MeshSettings(preset="reference")))
    whole = rotor_elastic_fe(static, RHO, E, NU, OMEGA, machine)
    sector = rotor_sector_fe(machine, RHO, E, NU, OMEGA, 80)
    assert sector.bore_peak == pytest.approx(whole.bore_peak, rel=0.02)
    assert sector.tip_displacement == pytest.approx(whole.tip_displacement, rel=0.002)
