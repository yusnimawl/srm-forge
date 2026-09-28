import math

import pytest

from srmcore.topology.primitives import (
    Arc, Line, fillet_line_circle, line_circle_intersection, map_segment, mirror_y, reverse, rotate,
)


def test_rotate_quarter_turn():
    x, y = rotate((1.0, 0.0), math.pi / 2)
    assert x == pytest.approx(0.0, abs=1e-15)
    assert y == pytest.approx(1.0)


def test_mirror_and_map_and_reverse():
    arc = Arc((1.0, 0.1), (1.0, 0.2), (0.0, 0.0), "t")
    m = map_segment(arc, mirror_y)
    assert m == Arc((1.0, -0.1), (1.0, -0.2), (0.0, 0.0), "t")
    assert reverse(Line((0, 0), (1, 1), "x")) == Line((1, 1), (0, 0), "x")


def test_intersection_from_inside_and_outside():
    p, t = line_circle_intersection((0.5, 0.0), (1.0, 0.0), 1.0)
    assert p == pytest.approx((1.0, 0.0)) and t == pytest.approx(0.5)
    p, t = line_circle_intersection((2.0, 0.0), (-1.0, 0.0), 1.0)
    assert p == pytest.approx((1.0, 0.0)) and t == pytest.approx(1.0)


def test_intersection_miss_raises():
    with pytest.raises(ValueError):
        line_circle_intersection((0.0, 2.0), (1.0, 0.0), 1.0)


@pytest.mark.parametrize("inside,p0,d", [
    (True, (0.5, 0.1), (1.0, 0.0)),    # stator-like: fillet inside the yoke circle
    (False, (1.5, 0.1), (-1.0, 0.0)),  # rotor-like: fillet outside the rotor-yoke circle
])
def test_fillet_is_tangent_to_line_and_circle(inside, p0, d):
    r, R, n = 0.05, 1.0, (0.0, 1.0)
    f = fillet_line_circle(p0, d, n, R, r, inside=inside)
    cx, cy = f.center
    assert cy == pytest.approx(0.1 + r)                      # centre is r from the line
    assert math.hypot(cx, cy) == pytest.approx(R - r if inside else R + r)
    assert f.on_line[1] == pytest.approx(0.1)                 # tangent point lies on the line
    assert math.hypot(*f.on_circle) == pytest.approx(R)       # tangent point lies on the circle
    assert math.hypot(cx - f.on_circle[0], cy - f.on_circle[1]) == pytest.approx(r)
    assert f.t_line > 0


def test_fillet_too_large_raises():
    with pytest.raises(ValueError):
        fillet_line_circle((0.9, 0.1), (1.0, 0.0), (0.0, 1.0), 1.0, 0.5, inside=True)
