import pytest

import kiyota_18_12 as k18
from srmcore.maps.end_winding import coil_geometry
from srmcore.mesh import build_machine_mesh


def test_coil_holds_the_cited_copper():
    p = k18.machine()
    assert coil_geometry(p).area * p.fill_factor == pytest.approx(k18.COPPER_AREA, rel=1e-4)
    assert k18.COPPER_AREA == pytest.approx(114.5e-6, rel=1e-3)


def test_design_validates_and_meshes_at_screening():
    d = k18.design(preset="screening")
    with k18.waivers():
        static = build_machine_mesh(d)
    assert static is not None
