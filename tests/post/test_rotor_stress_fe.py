"""Gate V6: the analytic rotor stress against a test-only 2D elastic FE (spec R5 section 8)."""
import math

import numpy as np
import pytest

from conftest import make_12_8, make_8_6
from rotor_elastic_fe import elastic_fe_mesh, rotor_elastic_fe
from srmcore.materials.library import load_material
from srmcore.mesh.static import build_static_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.post.rotor_stress import _disc_rim_displacement, gap_closure, rotor_stress

RHO, E, NU = 7490.0, 200e9, 0.33
OMEGA = 2 * math.pi * 12000 / 60
MECH = load_material("10JNEX900").mechanical


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
    fe = elastic_fe_mesh(nodes, np.array(tris), RHO, E, NU, OMEGA, a, b)
    hoop = RHO * OMEGA**2 / 4 * ((3 + NU) * b**2 + (1 - NU) * a**2)
    assert fe.bore_peak == pytest.approx(hoop, rel=0.01)
    assert fe.tip_displacement == pytest.approx(_disc_rim_displacement(a, b, RHO, OMEGA, NU, E, 0.0), rel=0.01)


@pytest.mark.slow
@pytest.mark.parametrize("make", [make_8_6, make_12_8])
def test_analytic_stress_against_fe(make):
    machine = make()
    # check speed equal to the FE speed: rotor_stress applies 1.2 x its argument
    rpm = OMEGA * 60 / (2 * math.pi)
    st = rotor_stress(machine, RHO, MECH, rpm / 1.2)
    assert st.status == "ok"
    ana_tip = gap_closure(machine, RHO, MECH, None, None, rpm, 20.0, 20.0).centrifugal
    fes = []
    for preset in ("screening", "full", "reference"):
        static = build_static_mesh(Design(machine=machine, mesh=MeshSettings(preset=preset)))
        fes.append(rotor_elastic_fe(static, RHO, E, NU, OMEGA, machine))
    assert max(abs(fes[2].bore_peak / fes[1].bore_peak - 1), abs(fes[2].root_peak / fes[1].root_peak - 1)) < 0.02
    fe = fes[2]
    assert st.bore_stress == pytest.approx(fe.bore_peak, rel=0.15)
    assert st.root_stress == pytest.approx(fe.root_peak, rel=0.15)
    assert max(st.bore_stress, st.root_stress) >= 0.95 * max(fe.bore_peak, fe.root_peak)
    assert ana_tip == pytest.approx(fe.tip_displacement, rel=0.15)
