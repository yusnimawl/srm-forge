import math

import numpy as np
import pytest
from sil_fixtures import analytic_motor
from test_sil_core import IDEAL, run

from srmsil.scenario import AdcSettings

FS = 25.0                          # default ADC full scale: 1.25 x the 20 A top current
TOP = 2**12 - 1
LSB = FS / TOP


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("sil_sensors")


def isr_steps(n_steps, isr_hz, dt):
    return np.arange(round(0.5 / isr_hz / dt), n_steps, round(1 / isr_hz / dt))


def test_adc_quantisation(cache):
    m = analytic_motor(saturating=False)
    res = run(cache, "volt_step", m, "lin", speed_rpm=0.0, duration=0.03, dt=1e-6, bus_voltage=12.0, isr_hz=1e5,
              adc={"full_scale": 5.0}, converter=IDEAL)
    tr = res.traces
    idx = isr_steps(len(tr["t"]), 1e5, 1e-6)
    true, adc = tr["i"][0][idx].astype(float), tr["adc_i"][0][idx].astype(float)
    lsb = 5.0 / TOP
    inside = true < 4.99
    assert inside.sum() > 100 and (true > 5.1).any()
    assert np.abs(adc[inside] - true[inside]).max() <= lsb / 2 + 1e-5
    assert adc[true > 5.1] == pytest.approx(5.0, abs=1e-5)


def test_adc_noise_sigma_and_seed(cache):
    m = analytic_motor()
    kw = dict(speed_rpm=0.0, duration=0.12, dt=1e-6, isr_hz=1e5, adc={"offset_counts": 2048, "noise": 3.0})
    codes = {}
    for seed in (1, 1, 2):
        tr = run(cache, "probe", m, "sat", seed=seed, **kw).traces
        idx = isr_steps(len(tr["t"]), 1e5, 1e-6)
        codes.setdefault(seed, []).append(np.rint(tr["adc_i"][0][idx] / LSB))
    a, b = codes[1]
    assert len(a) >= 10_000
    assert np.std(a) == pytest.approx(3.0, rel=0.10)
    assert abs(np.mean(a)) < 0.2
    assert np.array_equal(a, b)
    assert not np.array_equal(a, codes[2][0])


def test_adc_offset_and_gain_error(cache):
    m = analytic_motor(resistance=5.0, saturating=False)
    kw = dict(speed_rpm=0.0, duration=0.04, dt=1e-6, bus_voltage=10.0, isr_hz=1e5, converter=IDEAL)
    base = run(cache, "volt_step", m, "lin", adc={"offset_counts": 100}, **kw).traces
    err = run(cache, "volt_step", m, "lin", adc={"offset_counts": 100, "offset_error": 7.0, "gain_error": 0.05},
              **kw).traces
    i_true = base["i"][0][-1]
    assert i_true == pytest.approx(2.0, rel=1e-3)
    assert base["adc_i"][0][-1] == pytest.approx(i_true, abs=LSB / 2 + 1e-5)
    assert err["adc_i"][0][-1] == pytest.approx(i_true * 1.05 + 7.0 * LSB, abs=LSB / 2 + 1e-5)


def test_rc_filter_step(cache):
    tau, isr_hz, dt = 1e-3, 4e4, 1e-6
    m = analytic_motor(resistance=500.0, saturating=False)
    res = run(cache, "volt_step", m, "lin", speed_rpm=0.0, theta0=0.5 * m.pole_pitch, duration=4e-3, dt=dt,
              bus_voltage=1000.0, isr_hz=isr_hz, converter=IDEAL, adc={"rc_tau": tau})
    tr = res.traces
    idx = isr_steps(len(tr["t"]), isr_hz, dt)
    final = tr["i"][0][-1]
    assert final == pytest.approx(2.0, rel=1e-3)
    adc = tr["adc_i"][0][idx]
    t_cross = tr["t"][idx][np.argmax(adc >= (1 - math.exp(-1)) * final)]
    assert 0.0 <= t_cross - tau <= 1 / isr_hz + 5e-6


def test_encoder_count_and_eccentricity(cache):
    m = analytic_motor()
    cpr, rpm, dt = 4096, 3000.0, 2e-6
    rev = 60.0 / rpm
    res = run(cache, "probe", m, "sat", speed_rpm=rpm, duration=2.1 * rev, dt=dt, sensors={"encoder_cpr": cpr})
    enc, n = res.traces["encoder"], round(rev / dt)
    assert enc.min() >= 0 and enc.max() < cpr
    wraps = np.flatnonzero(np.diff(enc) < 0)
    assert len(wraps) == 2 and abs(wraps[0] - n) <= 1 and abs(wraps[1] - 2 * n) <= 1
    assert enc[wraps[0] + 1] == 0 and enc[wraps[0]] == cpr - 1

    amp, h = 0.01, 2
    res = run(cache, "probe", m, "sat", speed_rpm=rpm, duration=rev, dt=dt,
              sensors={"encoder_cpr": cpr, "encoder_ecc_amp": amp, "encoder_ecc_harmonic": h})
    th = res.traces["theta"]
    err = res.traces["encoder"] - np.floor(np.mod(th, 2 * math.pi) * cpr / (2 * math.pi))
    assert np.abs(err - amp * np.sin(h * th) * cpr / (2 * math.pi)).max() <= 1.0 + 1e-9
    assert np.abs(err).max() > 5


def test_encoder_single_turn_negative_offset(cache):
    m = analytic_motor()
    cpr, off = 4000, -0.05
    res = run(cache, "probe", m, "sat", speed_rpm=60.0, duration=0.01, dt=2e-6,
              sensors={"encoder_cpr": cpr, "encoder_offset": off})
    enc, th = res.traces["encoder"], res.traces["theta"]
    assert enc.min() >= 0 and enc.max() < cpr
    d = enc * 2 * math.pi / cpr - np.mod(th + off, 2 * math.pi)
    assert np.abs(d).max() <= 2 * math.pi / cpr + 1e-9


def test_adc_offset_counts_bound():
    with pytest.raises(ValueError):
        AdcSettings(bits=12, offset_counts=4096)


def test_resolver_mismatch(cache):
    m = analytic_motor()
    p, bits, mm, pe = 2, 12, 0.05, 0.02
    res = run(cache, "probe", m, "sat", speed_rpm=3000.0, duration=0.02, dt=2e-6,
              sensors={"resolver": True, "resolver_pole_pairs": p, "resolver_bits": bits,
                       "resolver_gain_mismatch": mm, "resolver_phase_error": pe})
    tr = res.traces
    s, c = tr["resolver_sin"], tr["resolver_cos"]
    assert np.abs(s).max() == 2**(bits - 1) - 1

    def wrap(x):
        return np.angle(np.exp(1j * x))

    x = p * tr["theta"]
    model = np.arctan2(np.sin(x), (1 + mm) * np.cos(x + pe))
    assert np.abs(wrap(np.arctan2(s, c) - model)).max() < 2e-3
    err = np.abs(wrap(np.arctan2(s, c) - x))
    bound = mm / 2 * 1.05 + pe
    assert 0.3 * bound < err.max() < bound
