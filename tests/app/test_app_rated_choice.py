import math
import time

import pytest
from conftest import make_8_6

from srmapp.case import CaseInputs, map_request
from srmapp.requirements import Requirements
from srmapp.thermal import check_requirement, thermal_context
from srmapp.evaluate import END_IMAGE_FACTOR, evaluate_stage2
from srmapp.sizing.generator import Candidate
from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.model.design import Design, MeshSettings, RegionMaterials

WIRE = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)
IRON = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
DESIGN = Design(machine=make_8_6(materials=IRON, lamination_thickness=1.0e-4), mesh=MeshSettings(preset="screening"))


@pytest.mark.slow
def test_rated_choice_8_6(tmp_path):
    req = Requirements(peak_power_w=628.0, peak_torque_nm=3.0, base_speed_rpm=2000.0, max_speed_rpm=6000.0,
                        wires=[WIRE], phase_current_a=20.0, continuous_power_w=100.0)
    ref, i_map, stage = map_request(CaseInputs(requirements=req, design=DESIGN))
    t = time.time()
    e = evaluate_stage2(Candidate("rated", ref), req, stage, i_map=i_map, cache_dir=tmp_path, n_speeds=1,
                        j_peak_max=stage.j_peak_max)
    print(f"evaluate wall {time.time() - t:.0f} s; {e.error}")
    assert e.status == "ok" and e.rating is not None
    assert math.isfinite(e.rated_continuous_kw_per_kg) and e.rated_continuous_kw_per_kg > 0
    result = with_end_winding(build_map(ref, i_map, cache_dir=tmp_path), end_winding_inductance(ref.machine, image_factor=END_IMAGE_FACTOR))
    ctx = thermal_context(req, ref, result, e.winding, cache_dir=tmp_path)
    assert check_requirement(ctx, 1).holds
