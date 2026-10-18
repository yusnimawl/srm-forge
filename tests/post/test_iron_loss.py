import math

import numpy as np
import pytest

from srmcore.materials import loss_model
from srmcore.post.iron_loss import EXCESS_C, reversals, waveform_loss

N_T = 360
CENTROID = np.array([[0.05, 0.0]])


@pytest.fixture(scope="module")
def model():
    return loss_model("10JNEX900")


def radial(shape, n_el=1):
    """(n_t, n_el, 2) with `shape` along x; at centroid (0.05, 0) x is radial."""
    b = np.zeros((len(shape), n_el, 2))
    b[:, :, 0] = np.asarray(shape)[:, None]
    return b


def sine(bhat, f, harmonic=None):
    x = 2 * np.pi * np.arange(N_T) / N_T
    s = bhat * np.sin(x)
    if harmonic:
        s = s + harmonic[0] * np.sin(harmonic[1] * x)
    return s


def test_excess_constant():
    x = np.linspace(0, 2 * np.pi, 200000, endpoint=False)
    mean = np.mean(np.abs(np.cos(x)) ** 1.5)
    assert EXCESS_C * mean * (2 * np.pi) ** 1.5 == pytest.approx(1.0, rel=1e-6)
    assert EXCESS_C == pytest.approx(0.1141, abs=5e-5)


@pytest.mark.parametrize("bhat,f", [(0.3, 50.0), (1.0, 400.0), (1.5, 1000.0), (0.1, 200.0)])
def test_sinusoid_matches_model(model, bhat, f):
    r = waveform_loss(radial(sine(bhat, f * 0 + 1.0)), CENTROID, 1.0 / f, model)
    assert r.total[0] == pytest.approx(model.sinusoid(bhat, f), rel=0.01)


def test_minor_loop_adds_loss(model):
    base = waveform_loss(radial(sine(1.0, 1)), CENTROID, 0.02, model)
    minor = waveform_loss(radial(sine(1.0, 1, (0.1, 5))), CENTROID, 0.02, model)
    assert minor.hysteresis[0] > base.hysteresis[0]


def test_dc_bias_raises_hysteresis(model):
    ac = 0.5 * np.sin(2 * np.pi * np.arange(N_T) / N_T)
    plain = waveform_loss(radial(ac), CENTROID, 0.02, model)
    biased = waveform_loss(radial(ac + 1.0), CENTROID, 0.02, model)
    assert biased.hysteresis[0] > plain.hysteresis[0]


def test_constant_field_no_dynamic_loss(model):
    r = waveform_loss(radial(np.full(N_T, 1.2)), CENTROID, 0.02, model)
    assert r.classical[0] == 0 and r.excess[0] == 0 and r.hysteresis[0] == 0


def test_classical_scales_f_squared(model):
    s = radial(sine(1.0, 1))
    a = waveform_loss(s, CENTROID, 0.02, model)
    b = waveform_loss(s, CENTROID, 0.01, model)
    assert b.classical[0] == pytest.approx(4 * a.classical[0], rel=1e-9)
    assert b.excess[0] == pytest.approx(2**1.5 * a.excess[0], rel=1e-9)


def test_beyond_fit_range(model):
    s = radial(sine(1.0, 1))
    f_hi = model.frequency_range[1] * 2
    assert waveform_loss(s, CENTROID, 1 / f_hi, model).beyond_fit_range
    assert not waveform_loss(s, CENTROID, 1 / model.frequency_range[1] * 4, model).beyond_fit_range


def test_beyond_b_range_high(model):
    s = radial(sine(model.b_range[1] * 1.2, 1))
    assert waveform_loss(s, CENTROID, 0.02, model).beyond_fit_range


def test_below_b_range_flag(model):
    s = radial(sine(model.b_range[0] * 0.5, 1))
    assert waveform_loss(s, CENTROID, 0.02, model).beyond_fit_range
    ok = radial(sine(model.b_range[0] * 3, 1))
    assert not waveform_loss(ok, CENTROID, 0.02, model).beyond_fit_range


def test_rotation_frame(model):
    r = waveform_loss(radial(sine(1.0, 1)), CENTROID, 0.02, model)
    tang = np.zeros((N_T, 1, 2))
    tang[:, 0, 1] = sine(1.0, 1)
    t = waveform_loss(tang, CENTROID, 0.02, model)
    assert t.total[0] == pytest.approx(r.total[0], rel=1e-9)
    both = np.zeros((N_T, 1, 2))
    both[:, 0, 0] = sine(1.0, 1)
    assert waveform_loss(both, CENTROID, 0.02, model).total[0] == pytest.approx(r.total[0], rel=1e-9)


def test_reversals_sinusoid():
    rev = reversals(sine(1.0, 1))
    assert len(rev) == 2 and all(math.isclose(s, 2.0) and abs(m) < 1e-9 for s, m in rev)
