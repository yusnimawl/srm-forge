import pytest

from conftest import make_8_6
from srmapp.cooling import (K_IRON_HI, ROWS, CoolingSetup, EndSpray, Jacket, MissingCoolingData, ShaftOil,
                            SlotOil, coefficients)
from srmapp.requirements import Requirements

M = make_8_6()
M = getattr(M, "machine", M)


def co(setup=CoolingSetup(), rpm=3000.0, u=(), em=None, **kw):
    return coefficients(setup, M, rpm, frozenset(u), em, **kw)


def _req(**kw):
    return Requirements(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0, **kw)


def test_default_is_placeholder_jacket():
    s = CoolingSetup()
    assert s.placeholder and s.jacket.inlet_c == 65.0


def test_default_jacket_in_range():
    assert co().h_jacket > 0     # Re above 1e4 at 65 degC


def test_limit_by_class():
    assert [_req(insulation_class=c).hot_spot_limit_c for c in "BFH"] == [110, 135, 160]


def test_old_requirements_load():
    r = _req()
    assert r.continuous_power_w is None and r.peak_duration_s == 30.0 and r.insulation_class == "H"
    assert r.cooling == CoolingSetup()


def test_old_setup_file_imports():
    from srmapp.case import CaseInputs
    from srmapp.references import REFERENCES
    from srmcore.model.design import Design
    from srmcore.mesh.settings import MeshSettings
    from srmweb.setup import SetupFile, case_inputs_from_setup, setup_from_case
    inputs = CaseInputs(requirements=_req(), design=Design(machine=M, mesh=MeshSettings(preset="screening")))
    d = setup_from_case(inputs, "x").model_dump(by_alias=True, mode="json")
    for k in ("continuous_power_w", "peak_duration_s", "insulation_class", "cooling"):
        del d["requirements"][k]
    got = case_inputs_from_setup(SetupFile.model_validate(d))
    assert got.requirements == _req()


@pytest.mark.parametrize("row,field,direction", [
    ("cross_wire", "k_cross_wire", -1), ("liner", "k_liner", -1), ("liner", "k_impregnation", -1),
    ("contact", "contact_gap", 1), ("lamination_k", "k_lamination", -1), ("cooling_h", "h_jacket", -1),
])
def test_each_row_moves_its_number(row, field, direction):
    a, b = getattr(co(fill=0.37), field), getattr(co(u={row}, fill=0.37), field)
    assert (b - a) * direction > 0


def test_cooling_h_spray_and_slot_oil():
    s = CoolingSetup(end_spray=EndSpray(inlet_c=65, flow_m3s=1e-5), slot_oil=SlotOil(
        channel_height=2e-3, channel_width=5e-3, inlet_c=65, flow_m3s=5e-5))
    n, w = co(s), co(s, u={"cooling_h"})
    assert n.h_end_spray == pytest.approx(550.0) and w.h_end_spray == 190.0
    assert w.h_slot_oil == pytest.approx(0.9 * n.h_slot_oil)


def test_iron_row_is_k_iron_hi():
    assert co().iron_factor == 1.0 and co(u={"iron"}).iron_factor == K_IRON_HI == 2.0


def test_em_torque_floor():
    f = lambda em: co(u={"em_torque"}, em=em).torque_factor  # noqa: E731
    assert f(None) == pytest.approx(1.10) and f(0.04) == pytest.approx(1.10) and f(0.15) == pytest.approx(1.15)
    assert co().torque_factor == 1.0


def test_uncited_option_refused():
    with pytest.raises(MissingCoolingData, match="shaft oil"):
        co(CoolingSetup(shaft_oil=ShaftOil(inlet_c=65, flow_m3s=1e-5)))
    with pytest.raises(MissingCoolingData, match="slot oil"):
        co(CoolingSetup(slot_oil=SlotOil(channel_height=2e-3, channel_width=5e-3, inlet_c=65,
                                         flow_m3s=5e-5, coolant="atf")))
    with pytest.raises(MissingCoolingData, match="jacket"):
        co(CoolingSetup(jacket=Jacket(flow_m3s=1e-5)))


def test_airgap_h_depends_on_rpm():
    assert co(rpm=6000.0).h_air_gap > co(rpm=3000.0).h_air_gap > 0


def test_placeholder_flag():
    assert CoolingSetup(jacket=Jacket(flow_m3s=1.6e-4)).placeholder     # ambient etc. still default
    s = CoolingSetup(jacket=Jacket(channel_height=5e-3, channel_width=25e-3, passes=3, flow_m3s=2e-4),
                     housing_thickness=9e-3, ambient_c=30.0)
    assert not s.placeholder
