import math

import numpy as np
import pytest

from srmcore.materials import loss_model
from srmcore.materials.library import load_material
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


def sine(bhat, harmonic=None):
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


def _points():
    return load_material("10JNEX900").loss.points


@pytest.mark.parametrize("point", _points(), ids=lambda p: f"{p.b}T-{p.f}Hz")
def test_sinusoid_matches_model(model, point):
    r = waveform_loss(radial(sine(point.b)), CENTROID, 1.0 / point.f, model)
    assert r.total[0] == pytest.approx(model.sinusoid(point.b, point.f), rel=0.01)


def test_minor_loop_adds_loss(model):
    base = waveform_loss(radial(sine(1.0)), CENTROID, 0.02, model)
    minor = waveform_loss(radial(sine(1.0, (0.1, 5))), CENTROID, 0.02, model)
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
    s = radial(sine(1.0))
    a = waveform_loss(s, CENTROID, 0.02, model)
    b = waveform_loss(s, CENTROID, 0.01, model)
    assert b.classical[0] == pytest.approx(4 * a.classical[0], rel=1e-9)
    assert b.excess[0] == pytest.approx(2**1.5 * a.excess[0], rel=1e-9)


def test_beyond_fit_range(model):
    s = radial(sine(1.0))
    f_hi = model.frequency_range[1] * 2
    assert waveform_loss(s, CENTROID, 1 / f_hi, model).beyond_fit_range
    assert not waveform_loss(s, CENTROID, 1 / model.frequency_range[1] * 4, model).beyond_fit_range


def test_beyond_b_range_high(model):
    s = radial(sine(model.b_range[1] * 1.2))
    assert waveform_loss(s, CENTROID, 0.02, model).beyond_fit_range


def test_below_b_range_flag(model):
    s = radial(sine(model.b_range[0] * 0.5))
    assert waveform_loss(s, CENTROID, 0.02, model).beyond_fit_range
    ok = radial(sine(model.b_range[0] * 3))
    assert not waveform_loss(ok, CENTROID, 0.02, model).beyond_fit_range


def test_rotation_frame(model):
    ref = waveform_loss(radial(sine(1.0)), CENTROID, 0.02, model)
    ang = math.radians(60)
    c = np.array([[0.05 * math.cos(ang), 0.05 * math.sin(ang)]])
    u = np.array([math.cos(ang), math.sin(ang)])
    v = np.array([-u[1], u[0]])
    s = sine(1.0)
    along = waveform_loss(s[:, None, None] * u[None, None, :], c, 0.02, model)
    across = waveform_loss(s[:, None, None] * v[None, None, :], c, 0.02, model)
    assert along.total[0] == pytest.approx(ref.total[0], rel=1e-9)
    assert across.total[0] == pytest.approx(ref.total[0], rel=1e-9)


def test_harmonic_above_range_flags(model):
    f1 = model.frequency_range[1] / 10
    s = sine(1.0, (0.5, 20))
    assert waveform_loss(radial(s), CENTROID, 1 / f1, model).beyond_fit_range
    assert not waveform_loss(radial(sine(1.0)), CENTROID, 1 / f1, model).beyond_fit_range


@pytest.mark.parametrize("period", [0.0, -1.0, float("nan"), float("inf")])
def test_bad_period(model, period):
    with pytest.raises(ValueError):
        waveform_loss(radial(sine(1.0)), CENTROID, period, model)


def test_too_few_samples(model):
    with pytest.raises(ValueError):
        waveform_loss(radial([1.0, -1.0]), CENTROID, 0.02, model)


@pytest.mark.parametrize("sig", [[1, 1, 1, -1, -1, -1], [1.0, -1], [1, 1, 0, 1, 1]])
def test_reversals_two_levels(sig):
    rev = reversals(np.array(sig, dtype=float))
    assert len(rev) == 2
    lo, hi = min(sig), max(sig)
    assert all(math.isclose(sw, hi - lo) and math.isclose(m, (hi + lo) / 2) for sw, m in rev)


def test_reversals_band_merges_ripple():
    x = 2 * np.pi * np.arange(N_T) / N_T
    s = np.sin(x) + 3e-2 * np.sin(40 * x)
    assert len(reversals(s, band=0.2)) == 2
    assert len(reversals(s, band=1e-3)) > 2


def test_reversals_sinusoid():
    rev = reversals(sine(1.0))
    assert len(rev) == 2 and all(math.isclose(s, 2.0) and abs(m) < 1e-9 for s, m in rev)
