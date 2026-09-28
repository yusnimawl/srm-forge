import math

import pytest

from conftest import make_8_6
from srmcore.model.errors import InputError
from srmcore.topology.primitives import Arc, Line, sample_segment
from srmcore.topology.radial import build_outline, periodicity


def _closed(segments, tol=1e-12):
    return all(math.dist(a.end, b.start) < tol for a, b in zip(segments, segments[1:] + segments[:1]))


def _area(segments):
    pts = [q for s in segments for q in sample_segment(s, 2e-4)[:-1]]
    return 0.5 * abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])))


def _signed_area(segments):
    pts = [q for s in segments for q in sample_segment(s, 2e-4)[:-1]]
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


def test_sample_segment_arc_stays_on_circle():
    arc = Arc((1.0, 0.0), (0.0, 1.0), (0.0, 0.0))
    pts = sample_segment(arc, 0.1)
    assert pts[0] == pytest.approx((1.0, 0.0)) and pts[-1] == pytest.approx((0.0, 1.0))
    assert all(math.hypot(*q) == pytest.approx(1.0) for q in pts)
    assert len(pts) >= 17  # quarter circle length 1.57 / 0.1


def test_boundaries_are_closed_and_counted(srm_8_6):
    o = build_outline(srm_8_6)
    assert _closed(list(o.stator_inner_boundary))
    assert _closed(list(o.rotor_outer_boundary))
    assert len(o.stator_inner_boundary) == 6 * 8   # face, flank, fillet, yoke, fillet, flank
    assert len(o.rotor_outer_boundary) == 6 * 6


def test_sharp_corners_have_four_segments_per_pole():
    o = build_outline(make_8_6(stator_fillet_radius=0.0, rotor_fillet_radius=0.0))
    assert len(o.stator_inner_boundary) == 4 * 8
    assert len(o.rotor_outer_boundary) == 4 * 6
    assert _closed(list(o.stator_inner_boundary)) and _closed(list(o.rotor_outer_boundary))
    roots = o.refinement_features["pole_root"]
    assert len(roots) == 2 * (8 + 6) and all(isinstance(r, tuple) for r in roots)


def test_faces_lie_on_their_circles(srm_8_6):
    o = build_outline(srm_8_6)
    for seg in o.stator_inner_boundary:
        if seg.tag == "stator_pole_tip":
            assert math.hypot(*seg.start) == pytest.approx(o.bore_radius)
    for seg in o.rotor_outer_boundary:
        if seg.tag == "rotor_pole_tip":
            assert math.hypot(*seg.end) == pytest.approx(o.rotor_outer_radius)


def test_rotor_pole_zero_is_centred_on_x_axis(srm_8_6):
    face = build_outline(srm_8_6).rotor_outer_boundary[0]
    assert face.tag == "rotor_pole_tip"
    assert face.start[1] == pytest.approx(-face.end[1])
    assert face.start[0] == pytest.approx(face.end[0])


def test_enclosed_areas_are_between_their_radii(reference_design):
    p = reference_design
    o = build_outline(p)
    assert math.pi * p.bore_radius**2 < _area(o.stator_inner_boundary) < math.pi * p.stator_yoke_inner_radius**2
    assert math.pi * p.rotor_yoke_outer_radius**2 < _area(o.rotor_outer_boundary) < math.pi * p.rotor_outer_radius**2


def test_refinement_features_with_fillets(srm_8_6):
    o = build_outline(srm_8_6)
    assert len(o.refinement_features["pole_tip"]) == 8 + 6
    roots = o.refinement_features["pole_root"]
    assert len(roots) == 2 * (8 + 6) and all(isinstance(r, Arc) for r in roots)


def test_band_radii_and_tags(srm_8_6):
    o = build_outline(srm_8_6)
    assert o.rotor_outer_radius < o.band_inner_radius < o.band_outer_radius < o.bore_radius
    tags = {s.tag for s in o.stator_inner_boundary}
    assert tags == {"stator_pole_tip", "stator_flank", "stator_pole_root", "stator_yoke"}
    assert any(isinstance(s, Line) for s in o.rotor_outer_boundary)


def test_periodicity(srm_8_6, srm_12_8, srm_24_16):
    assert (periodicity(srm_8_6), periodicity(srm_12_8), periodicity(srm_24_16)) == (2, 4, 8)


def test_oversized_fillet_is_an_input_error():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(stator_fillet_radius=0.02))
    assert any(i.parameter == "stator_fillet_radius" and i.rule == "pole_fit" for i in info.value.issues)


@pytest.mark.parametrize("taper_deg", [3, -3])
def test_tapered_outlines_are_closed_and_counter_clockwise(taper_deg):
    taper = math.radians(taper_deg)
    o = build_outline(make_8_6(stator_pole_taper=taper, rotor_pole_taper=taper))
    assert _closed(list(o.stator_inner_boundary))
    assert _closed(list(o.rotor_outer_boundary))
    assert _signed_area(o.stator_inner_boundary) > 0
    assert _signed_area(o.rotor_outer_boundary) > 0


def test_mixed_fillet_pole_root_contents():
    o = build_outline(make_8_6(stator_fillet_radius=0.0))
    roots = o.refinement_features["pole_root"]
    arcs = [r for r in roots if isinstance(r, Arc)]
    points = [r for r in roots if isinstance(r, tuple)]
    assert len(arcs) == 2 * 6    # rotor fillet arcs, still filleted
    assert len(points) == 2 * 8  # stator corners, sharp since stator_fillet_radius == 0


def test_pole_fit_error_attributes_taper_when_taper_is_the_cause():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(rotor_pole_taper=math.radians(10)))
    assert any(i.parameter == "rotor_pole_taper" and i.rule == "pole_fit" for i in info.value.issues)


def test_pole_fit_error_attributes_pole_arc_when_face_wider_than_pitch():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(stator_pole_arc=math.radians(50)))
    assert any(i.parameter == "stator_pole_arc" and i.rule == "pole_fit" for i in info.value.issues)
