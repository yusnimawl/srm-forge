import math

import pytest

from srmcore.post.end_winding import GMD_RECTANGLE, end_turn_inductance, parallel_filament_mutual

MU0_2PI = 2e-7


def test_parallel_filament_mutual_hand_value():
    # l = d = 1 m: μ0/2π · (ln(1 + √2) − √2 + 1)
    want = MU0_2PI * (math.log(1 + math.sqrt(2)) - math.sqrt(2) + 1)
    assert parallel_filament_mutual(1.0, 1.0) == pytest.approx(want, rel=1e-12)


def test_end_turn_inductance_hand_value():
    # span 1 m, GMD 1 m (build + depth = 1/0.2235), separation 3 m, one turn
    want = 2 * MU0_2PI * ((math.log(1 + math.sqrt(2)) - math.sqrt(2) + 1)
                          - (math.log((1 + math.sqrt(10)) / 3) - math.sqrt(10) + 3))
    build = depth = 0.5 / GMD_RECTANGLE
    assert end_turn_inductance(1, 1.0, build, depth, 3.0) == pytest.approx(want, rel=1e-12)


def test_turns_squared_and_image_factor():
    base = end_turn_inductance(1, 0.05, 0.03, 0.012, 0.09)
    assert end_turn_inductance(268, 0.05, 0.03, 0.012, 0.09) == pytest.approx(268**2 * base, rel=1e-12)
    assert end_turn_inductance(268, 0.05, 0.03, 0.012, 0.09, image_factor=2.0) == pytest.approx(
        2 * 268**2 * base, rel=1e-12)


def test_far_separation_tends_to_two_bar_self_inductances():
    g = GMD_RECTANGLE * (0.03 + 0.012)
    far = end_turn_inductance(1, 0.05, 0.03, 0.012, 1e6)
    assert far == pytest.approx(2 * parallel_filament_mutual(0.05, g), rel=1e-6)


def test_positive_and_grows_with_separation():
    a = end_turn_inductance(10, 0.05, 0.03, 0.012, 0.07)
    b = end_turn_inductance(10, 0.05, 0.03, 0.012, 0.2)
    assert 0 < a < b


@pytest.mark.parametrize("kwargs", [
    dict(turns=0), dict(span=0.0), dict(build=-0.01), dict(depth=0.0), dict(separation=0.0),
    dict(image_factor=0.9), dict(image_factor=2.1),
])
def test_rejects_bad_inputs(kwargs):
    args = dict(turns=10, span=0.05, build=0.03, depth=0.012, separation=0.09, image_factor=1.0) | kwargs
    with pytest.raises(ValueError):
        end_turn_inductance(**args)
