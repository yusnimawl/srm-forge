"""The winding scan (`turns.choose_turns`) and the drive simulation under it give the same numbers as the unoptimised
code kept in `envelope_reference.py`: bit for bit, not within a tolerance."""
import math

import numpy as np
import pytest
from conftest import make_8_6
from envelope_reference import _simulate as reference_simulate
from map_fixtures import synthetic_map

from srmapp import turns
from srmapp.drive import envelope as drive
from srmapp.requirements import Requirements
from srmapp.sizing.winding import max_mmf
from srmapp.turns import ScanCancelled, choose_turns, requirement_ratios

MACHINE = make_8_6()
ROUND = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)
ROUND_THIN = dict(kind="round", diameter=3.0e-3, outer_diameter=3.2e-3)


def _req(**kw):
    values = dict(peak_power_w=10.47, peak_torque_nm=0.1, base_speed_rpm=1000.0, max_speed_rpm=2000.0)
    values.update(kw)
    return Requirements(**values)


WIRE = _req(wires=[ROUND, ROUND_THIN], phase_current_a=100.0)
DENSITY = _req()


def _map(req):
    top = max_mmf(MACHINE, req, 20e6, 40e6) / MACHINE.turns_per_pole
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, top, 9))


def _tables(i_top=30.0):
    result = synthetic_map(n_angles=24, currents=np.linspace(0.0, i_top, 9))
    return drive._tables(result, 2 * math.pi / MACHINE.n_rotor_poles, i_top, drive.N_THETA)


def _same(a, b):
    assert len(a) == len(b)
    for x, y in zip(a, b):
        np.testing.assert_array_equal(x, y)


@pytest.mark.parametrize("rpm", [30.0, 1500.0, 9000.0])
def test_simulation_matches_the_reference_for_the_search_grid(rpm):
    t = _tables()
    on, off = drive._stroke_pairs(drive.N_THETA, drive.N_ON, drive.N_OFF)
    omega = rpm * 2 * math.pi / 60
    _same(drive._simulate(t, omega, 300.0, 0.3, on, off), reference_simulate(t, omega, 300.0, 0.3, on, off))


def test_simulation_matches_the_reference_for_unsorted_pairs_with_trace():
    t = _tables()
    on, off = drive._stroke_pairs(drive.N_THETA, drive.N_ON, drive.N_OFF)
    pick = np.random.default_rng(1).permutation(on.size)[:400]
    _same(drive._simulate(t, 150.0, 300.0, 0.3, on[pick], off[pick], trace=True),
          reference_simulate(t, 150.0, 300.0, 0.3, on[pick], off[pick], trace=True))


@pytest.mark.parametrize("on,off", [(40, 90), (140, 175), (0, 181), (179, 200)])
def test_simulation_matches_the_reference_for_one_stroke(on, off):
    t = _tables()
    args = (np.array([on]), np.array([off]))
    _same(drive._simulate(t, 200.0, 300.0, 0.3, *args, trace=True),
          reference_simulate(t, 200.0, 300.0, 0.3, *args, trace=True))


def test_envelope_without_waveforms_has_the_same_numbers():
    result = _map(DENSITY)
    speeds = np.array([300.0, 1000.0, 2000.0])
    full = drive.envelope(result, MACHINE, 300.0, 0.2, speeds, rms_limit=5.0)
    light = drive.envelope(result, MACHINE, 300.0, 0.2, speeds, rms_limit=5.0, waveforms=False)
    assert light.waveforms is None and np.isnan(light.line_rms).all() and np.isnan(light.power_factor).all()
    for name in ("speeds_rpm", "torque", "power", "copper_loss", "theta_on", "theta_off", "work_torque", "work_loop",
                 "i_rms"):
        np.testing.assert_array_equal(getattr(light, name), getattr(full, name))


def _reference_scan(result, req, every, **kw):
    """Every `every`-th winding through the full `envelope` on the reference simulation, as choose_turns used to."""
    choice = choose_turns(result, MACHINE, req, **kw)
    grid = turns.speed_grid(req)
    band = grid[grid >= req.base_speed_rpm]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(drive, "_simulate", reference_simulate)
        out = []
        for s in choice.scan[::every]:
            env = turns._envelope(result, MACHINE, req, s.winding, band, kw.get("j_limit", turns.J_LIMIT))
            out.append((*requirement_ratios(env, req), float(np.max(env.i_rms))))
    return choice, out


@pytest.mark.parametrize("req", [WIRE, DENSITY], ids=["wire", "density"])
def test_scan_matches_the_reference_winding_by_winding(req):
    kw = dict(j_peak_max=40e6, max_turns=24)
    choice, reference = _reference_scan(_map(req), req, 5, **kw)
    assert len(choice.scan) > 20
    got = [(s.torque_ratio, s.power_ratio, s.i_rms) for s in choice.scan[::5]]
    assert got == reference


def test_density_scan_runs_each_distinct_drive_once():
    result = _map(DENSITY)
    calls = []
    real = turns._drive_summary

    def counting(*args):
        calls.append(args[-1])
        return real(*args)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(turns, "_drive_summary", counting)
        choice = choose_turns(result, MACHINE, DENSITY, max_turns=8)
    # N turns on one path and 2N on two paths carry the same drive
    assert len(calls) == len(set(calls)) < len(choice.scan)
    twins = {}
    for s in choice.scan:
        twins.setdefault(turns._drive_key(MACHINE, s.winding, turns.J_LIMIT), []).append(s)
    assert any(len(v) > 1 for v in twins.values())
    for v in twins.values():
        assert len({(s.torque_ratio, s.power_ratio, s.i_rms) for s in v}) == 1


def test_scan_in_a_process_pool_matches_the_serial_scan(monkeypatch):
    result = _map(DENSITY)
    serial = choose_turns(result, MACHINE, DENSITY, max_turns=4)
    monkeypatch.setattr(turns, "MIN_PARALLEL_JOBS", 2)
    pooled = choose_turns(result, MACHINE, DENSITY, max_turns=4, workers=2)
    assert pooled.scan == serial.scan and pooled.point == serial.point
    _same((pooled.envelope.torque, pooled.envelope.i_rms), (serial.envelope.torque, serial.envelope.i_rms))


def test_scan_reports_progress_over_the_distinct_drives():
    seen = []
    choose_turns(_map(DENSITY), MACHINE, DENSITY, max_turns=6, progress=lambda d, n: seen.append((d, n)))
    total = seen[0][1]
    assert [d for d, _ in seen] == list(range(1, total + 1)) and {n for _, n in seen} == {total}


def test_scan_stops_when_cancelled():
    seen = []

    def cancel():
        return len(seen) >= 3
    with pytest.raises(ScanCancelled):
        choose_turns(_map(DENSITY), MACHINE, DENSITY, max_turns=6, progress=lambda d, n: seen.append(d),
                     cancel=cancel)
    assert seen == [1, 2, 3]
