import math
import re

import pytest
from conftest import make_8_6

from srmcore.model.errors import InputError
from srmcore.model.iron import IronArc, IronLine
from srmcore.topology.imported import check_iron, from_segments, iron_from_loops, parametric_iron, to_segments
from srmcore.topology.primitives import Arc, Line, map_segment, rotate
from srmcore.topology.radial import _coil_sides, build_outline

MM = 1e-3


def _loops(p):
    iron = parametric_iron(p)
    return [to_segments(l) for l in (iron.stator_outer, iron.stator_bore, iron.rotor_outer, iron.rotor_bore)]


def _with(p, **kw):
    return p.model_copy(update={"iron": parametric_iron(p).model_copy(update=kw)})


def _rules(issues):
    return sorted({i.rule for i in issues if i.severity == "error"})


def _loc(message):
    m = re.search(r"\((-?\d+\.\d), (-?\d+\.\d)\) mm", message)
    return float(m.group(1)), float(m.group(2))


def _circle(cx, cy, r, tag=""):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    return tuple(Arc(pts[i], pts[(i + 1) % 4], (cx, cy), tag) for i in range(4))


def _grooved_outer(radius, n, depth=1 * MM, half_width=1 * MM):
    d = math.asin(half_width / radius)

    def at(r, a):
        return (r * math.cos(a), r * math.sin(a))

    segs = []
    for k in range(n):
        a, a_next = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        left, apex, right = at(radius, a - d), at(radius - depth, a), at(radius, a + d)
        segs += [IronLine(start=left, end=apex), IronLine(start=apex, end=right),
                 IronArc(start=right, end=at(radius, a_next - d), center=(0.0, 0.0))]
    return tuple(segs)


def _radial(loop, bound, new, p_tol=1e-9):
    """Scale every vertex whose radius equals `bound` to radius `new`."""
    def mv(q):
        r = math.hypot(*q)
        return q if abs(r - bound) > p_tol else (q[0] * new / r, q[1] * new / r)

    return tuple(Line(mv(s.start), mv(s.end)) if isinstance(s, Line) else Arc(mv(s.start), mv(s.end), s.center)
                 for s in loop)


def test_parametric_iron_passes(reference_design):
    p = reference_design
    assert check_iron(_with(p)) == []


def test_snaps_near_circle_vertices():
    p = make_8_6()
    so, sb, ro, rb = _loops(p)

    def bump(q):
        r = math.hypot(*q)
        return q if abs(r - p.bore_radius) > 1e-9 else (q[0] * (r + 0.3e-6) / r, q[1] * (r + 0.3e-6) / r)

    sb_off = tuple(Line(bump(s.start), bump(s.end)) if isinstance(s, Line) else Arc(bump(s.start), bump(s.end), s.center)
                   for s in sb)
    iron, issues = iron_from_loops([so, sb_off, ro, rb], p)
    assert iron is not None and _rules(issues) == []
    on_bore = [s.start for s in iron.stator_bore if abs(math.hypot(*s.start) - p.bore_radius) < 1e-7]
    assert len(on_bore) >= 2 * p.n_stator_poles
    for q in on_bore:
        assert math.hypot(*q) == pytest.approx(p.bore_radius, abs=1e-15)


def test_coil_loops_dropped():
    p = make_8_6()
    plain, _ = iron_from_loops(_loops(p), p)
    assert plain is not None
    with_coils, issues = iron_from_loops(_loops(p) + [side.boundary for side in _coil_sides(p)], p)
    assert _rules(issues) == [] and with_coils == plain


def test_canonical_form():
    p = make_8_6()
    so, sb, ro, rb = _loops(p)
    flipped = tuple(Line(s.end, s.start) if isinstance(s, Line) else Arc(s.end, s.start, s.center)
                    for s in reversed(sb))
    a, _ = iron_from_loops([so, sb, ro, rb], p)
    b, _ = iron_from_loops([so, flipped[3:] + flipped[:3], ro, rb], p)
    assert a is not None and a == b
    ang = [math.atan2(q.start[1], q.start[0]) % (2 * math.pi) for q in a.stator_bore]
    assert ang[0] == min(ang)


def test_shifted_centre():
    p = make_8_6()
    shift = lambda q: (q[0] + 1 * MM, q[1])  # noqa: E731
    iron, issues = iron_from_loops([tuple(map_segment(s, shift) for s in l) for l in _loops(p)], p)
    assert iron is None and _rules(issues) == ["centre"]
    assert "1.00" in issues[0].message


def test_rotated_rotor():
    p = make_8_6()
    so, sb, ro, rb = _loops(p)
    turn = tuple(map_segment(s, lambda q: rotate(q, math.radians(2.0))) for s in ro)
    iron, issues = iron_from_loops([so, sb, turn, rb], p)
    assert iron is None and _rules(issues) == ["rotor_angle"]
    assert "2.00°" in issues[0].message


def test_iron_in_air_gap():
    p = make_8_6()
    pushed = _radial(to_segments(parametric_iron(p).stator_bore), p.bore_radius, p.bore_radius - 0.1 * MM)
    issues = check_iron(_with(p, stator_bore=tuple(
        IronLine(start=s.start, end=s.end) if isinstance(s, Line) else IronArc(start=s.start, end=s.end, center=s.center)
        for s in pushed)))
    assert _rules(issues) == ["air_gap"]
    x, y = _loc(issues[0].message)
    assert math.hypot(x, y) == pytest.approx(p.bore_radius / MM - 0.1, abs=0.1)
    assert "inside the bore radius" in issues[0].message


def test_iron_in_coil():
    p = make_8_6()
    r = p.stator_yoke_inner_radius
    segs = []
    for s in to_segments(parametric_iron(p).stator_bore):
        if isinstance(s, Arc) and s.center == (0.0, 0.0) and abs(math.dist(s.start, s.center) - r) < 1e-9:
            k = (r - 4 * MM) / r
            a, b = (s.start[0] * k, s.start[1] * k), (s.end[0] * k, s.end[1] * k)
            segs += [Line(s.start, a), Arc(a, b, (0.0, 0.0)), Line(b, s.end)]
        else:
            segs.append(s)
    bore = tuple(IronLine(start=s.start, end=s.end) if isinstance(s, Line)
                 else IronArc(start=s.start, end=s.end, center=s.center) for s in segs)
    issues = check_iron(_with(p, stator_bore=bore))
    assert _rules(issues) == ["coil_overlap"]
    assert math.hypot(*_loc(issues[0].message)) < (r - 2 * MM) / MM


def test_two_grooves_refused():
    p = make_8_6()
    issues = check_iron(_with(p, stator_outer=_grooved_outer(p.stator_outer_radius, 2)))
    assert _rules(issues) == ["repeat"]
    msg = issues[0].message
    assert "repeats 2 times" in msg and "polar-array it 8×" in msg and "every 45°" in msg and "8/6 stator" in msg
    x, y = _loc(msg)
    assert p.stator_outer_radius / MM - 1.0 - 0.1 <= math.hypot(x, y) <= p.stator_outer_radius / MM + 0.1


def test_eight_grooves_pass():
    p = make_8_6()
    assert check_iron(_with(p, stator_outer=_grooved_outer(p.stator_outer_radius, 8))) == []


def test_thin_web():
    p = make_8_6().model_copy(update={"lamination_thickness": 0.1 * MM})
    r = p.stator_outer_radius - 0.5 * MM - 0.5 * MM  # 0.5 mm radius hole, 0.5 mm from the OD
    holes = tuple(tuple(IronArc(start=a.start, end=a.end, center=a.center) for a in _circle(
        r * math.cos(math.radians(22.5 + 45 * k)), r * math.sin(math.radians(22.5 + 45 * k)), 0.5 * MM))
        for k in range(8))
    issues = check_iron(_with(p, stator_holes=holes))
    assert _rules(issues) == ["web_width"]
    assert "0.50 mm" in issues[0].message and "1.00 mm" in issues[0].message
    x, y = _loc(issues[0].message)
    assert p.stator_outer_radius / MM - 0.55 <= math.hypot(x, y) <= p.stator_outer_radius / MM


def test_stray_loop():
    p = make_8_6()
    r = (p.bore_radius + p.stator_yoke_inner_radius) / 2
    a = math.pi / p.n_stator_poles
    extra = _circle(r * math.cos(a), r * math.sin(a), 2 * MM)
    iron, issues = iron_from_loops(_loops(p) + [extra], p)
    assert iron is None and _rules(issues) == ["stray_loop"]
    assert "mm" in issues[0].message


def test_two_rotor_pieces():
    p = make_8_6()
    so, sb, _, _ = _loops(p)
    r = p.rotor_outer_radius / 2
    pieces = [_circle(r, 0.0, r / 2), _circle(-r, 0.0, r / 2)]
    iron, issues = iron_from_loops([so, sb, *pieces], p)
    assert iron is None and _rules(issues) == ["bodies"]
    assert "one closed loop" in issues[0].message


def test_zero_length_segment_refused():
    p = make_8_6()
    sb = list(parametric_iron(p).stator_bore)
    sb.insert(1, IronLine(start=sb[0].end, end=sb[0].end))
    issues = check_iron(_with(p, stator_bore=tuple(sb)))
    assert _rules(issues) == ["bad_segment"]


def test_build_outline_raises():
    p = make_8_6()
    q = _with(p, stator_outer=_grooved_outer(p.stator_outer_radius, 2))
    with pytest.raises(InputError) as e:
        build_outline(q)
    assert [i.rule for i in e.value.issues] == ["repeat"]


def test_check_iron_is_fast(reference_design):
    import time

    q = _with(reference_design)
    t = time.perf_counter()
    check_iron(q)
    assert time.perf_counter() - t < 1.5


def test_coil_inside_solid_iron():
    p = make_8_6()
    plain_bore = from_segments(_circle(0.0, 0.0, p.bore_radius))
    issues = check_iron(_with(p, stator_bore=plain_bore))
    assert _rules(issues) == ["coil_overlap"]
    assert "inside solid iron" in issues[0].message and "mm" in issues[0].message


def test_open_loop_through_iron_from_loops():
    p = make_8_6()
    so, sb, ro, rb = _loops(p)
    cut = list(sb)
    cut[5] = Line(cut[5].start, (cut[5].end[0] + 0.5 * MM, cut[5].end[1])) if isinstance(cut[5], Line) else cut[5]
    cut[4] = Line(cut[4].start, (cut[4].end[0] + 0.5 * MM, cut[4].end[1]))
    iron, issues = iron_from_loops([so, tuple(cut), ro, rb], p)
    assert iron is None and "open_loop" in _rules(issues)
    assert "open near (" in issues[0].message and "mm" in issues[0].message


def test_classification_messages_have_locations():
    p = make_8_6()
    so, sb, _, _ = _loops(p)
    for loops in ([so, sb], [so]):
        iron, issues = iron_from_loops(loops, p)
        assert iron is None and _rules(issues) == ["bodies"]
        assert re.search(r"\(-?\d+\.\d, -?\d+\.\d\) mm", issues[0].message)


@pytest.mark.parametrize("short", [0.005, 0.001])
def test_thin_web_is_measured_exactly(short):
    p = make_8_6().model_copy(update={"lamination_thickness": 0.1 * MM})
    web = (1.0 - short) * MM
    r = p.stator_outer_radius - web - 0.5 * MM
    holes = tuple(from_segments(_circle(r * math.cos(math.radians(22.5 + 45 * k)),
                                        r * math.sin(math.radians(22.5 + 45 * k)), 0.5 * MM)) for k in range(8))
    issues = check_iron(_with(p, stator_holes=holes))
    assert _rules(issues) == ["web_width"]
    assert f"{(1.0 - short):.3f}"[:4] in issues[0].message or "0.99" in issues[0].message or "1.00" in issues[0].message


def test_web_just_wide_enough_passes():
    p = make_8_6().model_copy(update={"lamination_thickness": 0.1 * MM})
    r = p.stator_outer_radius - 1.0 * MM - 0.5 * MM
    holes = tuple(from_segments(_circle(r * math.cos(math.radians(22.5 + 45 * k)),
                                        r * math.sin(math.radians(22.5 + 45 * k)), 0.5 * MM)) for k in range(8))
    assert check_iron(_with(p, stator_holes=holes)) == []


def test_air_gap_stator_outer_beyond_od():
    p = make_8_6()
    issues = check_iron(_with(p, stator_outer=from_segments(_circle(0.0, 0.0, p.stator_outer_radius + 0.1 * MM))))
    assert _rules(issues) == ["air_gap"] and "stator outer" in issues[0].message


def test_air_gap_rotor_bore_inside_shaft():
    p = make_8_6()
    issues = check_iron(_with(p, rotor_bore=from_segments(_circle(0.0, 0.0, p.shaft_radius - 0.1 * MM))))
    assert _rules(issues) == ["air_gap"] and "rotor bore" in issues[0].message


def test_air_gap_rotor_outer_beyond_radius():
    p = make_8_6()
    pushed = _radial(to_segments(parametric_iron(p).rotor_outer), p.rotor_outer_radius, p.rotor_outer_radius + 0.1 * MM)
    issues = check_iron(_with(p, rotor_outer=from_segments(pushed)))
    assert _rules(issues) == ["air_gap"] and "rotor outer" in issues[0].message


def test_chamfered_rotor_corners_pass():
    p = make_8_6()
    segs = list(to_segments(parametric_iron(p).rotor_outer))
    out = list(segs)
    c = 0.5 * MM
    for i, s in enumerate(segs):
        if not (isinstance(s, Arc) and s.center == (0.0, 0.0) and abs(math.dist(s.start, s.center) - p.rotor_outer_radius) < 1e-9):
            continue
        prev, nxt = segs[i - 1], segs[(i + 1) % len(segs)]
        u1 = ((prev.start[0] - prev.end[0]), (prev.start[1] - prev.end[1]))
        u2 = ((nxt.end[0] - nxt.start[0]), (nxt.end[1] - nxt.start[1]))
        f1 = (prev.end[0] + c * u1[0] / math.hypot(*u1), prev.end[1] + c * u1[1] / math.hypot(*u1))
        f2 = (nxt.start[0] + c * u2[0] / math.hypot(*u2), nxt.start[1] + c * u2[1] / math.hypot(*u2))
        turn = c / p.rotor_outer_radius
        a, b = rotate(s.start, turn), rotate(s.end, -turn)
        out[i - 1] = Line(prev.start, f1)
        out[(i + 1) % len(segs)] = Line(f2, nxt.end)
        out[i] = (Line(f1, a), Arc(a, b, (0.0, 0.0)), Line(b, f2))
    flat = [x for item in out for x in (item if isinstance(item, tuple) else (item,))]
    assert check_iron(_with(p, rotor_outer=from_segments(tuple(flat)))) == []
