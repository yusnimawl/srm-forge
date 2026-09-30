r"""Golden key numbers and check statuses for the example 8/6 screening map (I_max = 20 A).

Regenerate goldens_8_6.json after an intended change to the engine:

    $env:SRM_REGEN_GOLDENS = "1"; .venv\Scripts\python -m pytest tests/maps/test_goldens.py -m slow
"""
import dataclasses
import json
import math
import os
from pathlib import Path

import pytest

pytest.importorskip("ngsolve")

from srmcore.maps import analyse_map, build_map
from srmcore.model.design import Design, MeshSettings, RadialSRMParams

GOLDEN = Path(__file__).with_name("goldens_8_6.json")


def _design() -> Design:
    machine = RadialSRMParams(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=0.160, rotor_outer_diameter=0.080, air_gap=0.0004,
        stack_length=0.100, shaft_diameter=0.020,
        stator_pole_arc=math.radians(20.0), rotor_pole_arc=math.radians(22.0),
        stator_yoke_thickness=0.012, rotor_yoke_thickness=0.012,
        stator_fillet_radius=0.001, rotor_fillet_radius=0.001,
        turns_per_pole=60, fill_factor=0.5,
        slot_liner_thickness=0.0005, coil_inner_clearance=0.001,
    )
    return Design(machine=machine, mesh=MeshSettings(preset="screening"))


@pytest.mark.slow
def test_8_6_screening_goldens():
    design = _design()
    report = analyse_map(build_map(design, 20.0, workers=4), design)
    got = {"key_numbers": dataclasses.asdict(report.key_numbers),
           "statuses": {c.name: c.status for c in report.checks}}
    if os.environ.get("SRM_REGEN_GOLDENS"):
        GOLDEN.write_text(json.dumps(got, indent=2) + "\n")
    want = json.loads(GOLDEN.read_text())
    for name, value in want["key_numbers"].items():
        assert got["key_numbers"][name] == pytest.approx(value, rel=1e-3), name
    assert got["statuses"] == want["statuses"]
