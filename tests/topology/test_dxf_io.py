import io
import math
from pathlib import Path

import ezdxf
import pytest
from conftest import make_8_6

from srmcore.maps.identity import design_hash
from srmcore.model.design import Design, MeshSettings
from srmcore.topology.dxf_io import import_dxf, read_loops, write_dxf
from srmcore.topology.imported import from_segments, iron_areas, iron_from_loops, parametric_iron, to_segments
from srmcore.topology.primitives import Arc, Line
from srmcore.topology.radial import _full_circle

MM = 1e-3


def _doc(units=4):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = units
    return doc


def _bytes(doc) -> bytes:
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode()


def _errs(issues):
    return {i.rule for i in issues if i.severity == "error"}


def _square(msp, x0, y0, s, z=0.0):
    pts = [(x0, y0, z), (x0 + s, y0, z), (x0 + s, y0 + s, z), (x0, y0 + s, z)]
    for k in range(4):
        msp.add_line(pts[k], pts[(k + 1) % 4])


def _canonical(p):
    iron = parametric_iron(p)
    loops = [to_segments(l) for l in (iron.stator_outer, iron.stator_bore, iron.rotor_outer, iron.rotor_bore)]
    return iron_from_loops(loops, p)[0]


def test_round_trip_parametric(reference_design):
    p = reference_design
    iron, issues = import_dxf(write_dxf(p), p)
    assert issues == []
    assert iron == _canonical(p)


def test_reimport_is_canonical():
    p = make_8_6()
    iron, _ = import_dxf(write_dxf(p), p)
    q = p.model_copy(update={"iron": iron})
    iron2, issues = import_dxf(write_dxf(q), q)
    assert issues == [] and iron2 == iron
    assert design_hash(Design(machine=q, mesh=MeshSettings())) == design_hash(
        Design(machine=p.model_copy(update={"iron": iron2}), mesh=MeshSettings()))


def test_circle_and_major_arc_split():
    doc = _doc()
    msp = doc.modelspace()
    msp.add_circle((0, 0), 10)
    msp.add_arc((50, 0), 5, 0, 300)
    msp.add_line((55, 0), (50 + 5 * math.cos(math.radians(300)), 5 * math.sin(math.radians(300))))
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 2
    circle = [l for l in loops if all(isinstance(s, Arc) for s in l)]
    assert len(circle) == 1 and len(circle[0]) == 4
    other = next(l for l in loops if l is not circle[0])
    segs = list(circle[0]) + [s for s in other if isinstance(s, Arc)]
    assert len(segs) == 4 + 4  # the 300 degree arc is split in four minor arcs
    for s in segs:
        a = math.atan2(s.start[1] - s.center[1], s.start[0] - s.center[0])
        b = math.atan2(s.end[1] - s.center[1], s.end[0] - s.center[0])
        assert abs((b - a + math.pi) % (2 * math.pi) - math.pi) < math.pi - 1e-6


def test_inch_converted():
    doc = _doc(units=1)
    _square(doc.modelspace(), 0, 0, 1.0)
    loops, issues = read_loops(_bytes(doc))
    assert issues == []
    assert max(c for s in loops[0] for c in s.end) == pytest.approx(0.0254)


def test_metres_and_none_units():
    doc = _doc(units=6)
    _square(doc.modelspace(), 0, 0, 0.01)
    assert max(c for s in read_loops(_bytes(doc))[0][0] for c in s.end) == pytest.approx(0.01)
    doc = _doc(units=0)
    _square(doc.modelspace(), 0, 0, 10)
    assert max(c for s in read_loops(_bytes(doc))[0][0] for c in s.end) == pytest.approx(0.01)


def test_unknown_units_refused():
    doc = _doc(units=5)
    _square(doc.modelspace(), 0, 0, 10)
    loops, issues = read_loops(_bytes(doc))
    assert loops == [] and _errs(issues) == {"dxf_units"}


def test_non_flat_refused():
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 10)
    msp.add_line((0, 0, 3), (5, 5, 3))
    _, issues = read_loops(_bytes(doc))
    assert _errs(issues) == {"dxf_flat"}


def test_z_offset_ignored():
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 10, z=5)
    msp.add_circle((50, 0, 5), 3)
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 2


def test_open_loop_reported():
    doc = _doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))
    msp.add_line((10, 10), (0, 10))
    msp.add_line((0, 10), (0, 0.5))
    loops, issues = read_loops(_bytes(doc))
    assert loops == [] and _errs(issues) == {"open_loop"}
    assert "(0.0, 0.5) mm" in issues[0].message


def test_overlap_reported():
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 10)
    msp.add_line((2, 0), (6, 0))
    _, issues = read_loops(_bytes(doc))
    assert "overlap" in _errs(issues)
    assert "(4.0, 0.0) mm" in next(i for i in issues if i.rule == "overlap").message


def test_duplicate_arc_reported():
    doc = _doc()
    msp = doc.modelspace()
    msp.add_arc((0, 0), 10, 0, 60)
    msp.add_arc((0, 0), 10, 30, 90)
    _, issues = read_loops(_bytes(doc))
    assert "overlap" in _errs(issues)


def test_unsupported_entity():
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 10)
    msp.add_solid([(30, 0), (35, 0), (30, 5), (35, 5)])
    _, issues = read_loops(_bytes(doc))
    assert _errs(issues) == {"dxf_entity"}
    assert "SOLID" in issues[0].message


def _seg_dist(q, a, b):
    d = (b[0] - a[0], b[1] - a[1])
    t = max(0.0, min(1.0, ((q[0] - a[0]) * d[0] + (q[1] - a[1]) * d[1]) / (d[0] ** 2 + d[1] ** 2)))
    return math.dist(q, (a[0] + t * d[0], a[1] + t * d[1]))


def test_spline_flattened():
    doc = _doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 5))
    msp.add_line((0, 5), (0, 0))
    sp = msp.add_spline(fit_points=[(10, 5), (5, 8), (0, 5)])
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1
    assert len(loops[0]) > 10
    curve = [(t.x, t.y) for t in sp.flattening(1e-5)]
    chords = [s for s in loops[0] if isinstance(s, Line) and s.start[1] > 5.5 * MM]
    assert len(chords) > 10
    for s in chords:  # the chord midpoint is within 1 um (1e-3 mm) of the true curve
        mid = ((s.start[0] + s.end[0]) / 2 / MM, (s.start[1] + s.end[1]) / 2 / MM)
        assert min(_seg_dist(mid, a, b) for a, b in zip(curve, curve[1:])) <= 1e-3 + 1e-5


def test_fit_point_spline_z_checked():
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 10)
    msp.add_spline(fit_points=[(20, 0, 4), (25, 5, 4), (30, 0, 4)])
    _, issues = read_loops(_bytes(doc))
    assert _errs(issues) == {"dxf_flat"}


def test_flipped_extrusion_keeps_wcs_coordinates():
    doc = _doc()
    msp = doc.modelspace()
    flip = {"extrusion": (0, 0, -1)}
    # the square (10..20, 5..15) in WCS: OCS x is -WCS x
    pts = [(-10, 5), (-20, 5), (-20, 15), (-10, 15)]
    msp.add_lwpolyline(pts, close=True, dxfattribs=flip)
    msp.add_arc((-50, 0), 5, 0, 90, dxfattribs=flip)   # WCS: centre (50, 0), from (45, 0) to (50, 5)
    msp.add_line((45, 0), (50, 5))
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 2
    sq = next(l for l in loops if all(isinstance(s, Line) for s in l))
    assert sorted({round(c * 1e3, 6) for s in sq for c in (s.start[0], s.end[0])}) == [10.0, 20.0]
    arc = next(s for l in loops for s in l if isinstance(s, Arc))
    assert arc.center == pytest.approx((0.05, 0.0), abs=1e-12)
    assert {tuple(round(c * 1e3, 6) for c in q) for q in (arc.start, arc.end)} == {(45.0, 0.0), (50.0, 5.0)}


def test_refusal_locations_are_wcs_millimetres():
    flip = {"extrusion": (0, 0, -1)}
    doc = _doc()
    doc.modelspace().add_line((0, 0), (1, 1))
    doc.modelspace().add_arc((-50, 0, 7), 5, 0, 90, dxfattribs=flip)
    _, issues = read_loops(_bytes(doc))
    assert [i.rule for i in issues] == ["dxf_flat"] and "near (50.0, 0.0) mm" in issues[0].message
    doc = _doc()
    doc.modelspace().add_line((0, 0), (1, 1))
    doc.modelspace().add_lwpolyline([(-10, 5), (-20, 5), (-20, 15)], dxfattribs={**flip, "elevation": 3})
    _, issues = read_loops(_bytes(doc))
    assert [i.rule for i in issues] == ["dxf_flat"] and "near (10.0, 5.0) mm" in issues[0].message


def test_tilted_extrusion_refused():
    doc = _doc()
    doc.modelspace().add_circle((0, 0), 5, dxfattribs={"extrusion": (1, 0, 0)})
    _, issues = read_loops(_bytes(doc))
    assert _errs(issues) == {"dxf_flat"}


def test_bulge_polyline():
    doc = _doc()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0, 0, 0, 0), (10, 0, 0, 0, 1.0), (10, 10, 0, 0, 0), (0, 10, 0, 0, 0)], format="xyseb", close=True)
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1
    arcs = [s for s in loops[0] if isinstance(s, Arc)]
    assert len(arcs) == 2  # bulge 1 is a half circle, split in two
    assert all(abs(math.dist(a.start, a.center) - 5 * MM) < 1e-9 for a in arcs)


def test_text_ignored():
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 10)
    msp.add_text("hello")
    msp.add_point((1, 1))
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1


def test_insert_exploded():
    doc = _doc()
    blk = doc.blocks.new("SQ")
    _square(blk, 0, 0, 10)
    doc.modelspace().add_blockref("SQ", (100, 0))
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1
    assert max(s.end[0] for s in loops[0]) == pytest.approx(0.11)


def test_layers_and_units_written():
    doc = ezdxf.read(io.StringIO(write_dxf(make_8_6()).decode()))
    assert doc.header["$INSUNITS"] == 4
    assert {e.dxf.layer for e in doc.modelspace()} == {"STATOR", "ROTOR", "COILS"}
    assert {e.dxftype() for e in doc.modelspace() if e.dxf.layer == "STATOR"} >= {"CIRCLE", "ARC", "LINE"}


def test_iron_area_warning(monkeypatch):
    p = make_8_6()
    doc = ezdxf.read(io.StringIO(write_dxf(p).decode()))
    for k in range(8):  # eight holes in the stator yoke
        a = math.radians(45 * k + 22.5)
        doc.modelspace().add_circle((74 * math.cos(a), 74 * math.sin(a)), 4.5, dxfattribs={"layer": "STATOR"})
    iron, issues = import_dxf(_bytes(doc), p)
    assert iron is not None and not any(i.rule == "iron_area" for i in issues)  # 4 % change: under the limit
    monkeypatch.setattr("srmcore.topology.dxf_io._AREA_CHANGE", 0.02)
    _, issues = import_dxf(_bytes(doc), p)
    assert any(i.rule == "iron_area" and i.severity == "warning" for i in issues)


def test_iron_areas_ring_and_parametric():
    r_o, r_i = 0.05, 0.02
    ring = parametric_iron(make_8_6()).model_copy(update={
        "stator_outer": from_segments(_full_circle(r_o, "")), "stator_bore": from_segments(_full_circle(r_i, ""))})
    assert iron_areas(ring)[0] == pytest.approx(math.pi * (r_o**2 - r_i**2), rel=1e-12)
    p = make_8_6()
    s, r = iron_areas(parametric_iron(p))
    # salient poles and teeth remove or add material relative to the plain rings
    assert 0 < s < math.pi * (p.stator_outer_radius**2 - p.bore_radius**2)
    assert 0 < r < math.pi * (p.rotor_outer_radius**2 - p.shaft_radius**2)
    assert s > 0.5 * math.pi * (p.stator_outer_radius**2 - p.bore_radius**2)


# --- Onshape export, binary DXF, ELLIPSE ----------------------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "onshape_8_6_edit.dxf"


def _reference_8_6():
    from srmapp.references import REFERENCES
    from srmcore.materials.library import load_material
    from srmcore.model.design import RegionMaterials

    material = load_material("10JNEX900")
    return REFERENCES["8/6"](materials=RegionMaterials(stator=material.name, rotor=material.name),
                             lamination_thickness=material.thickness)


def test_onshape_file_reads_closed_loops():
    loops, issues = read_loops(FIXTURE.read_bytes())
    assert not {i.rule for i in issues} & {"dxf_file", "dxf_entity"}
    assert len(loops) == 34   # 18 iron loops (4 outer/bore, 8 yoke holes, 6 rotor holes) and 16 coil sides


def test_onshape_file_reports_untrimmed_arc():
    # the stator OD arc 316.34..43.66 deg runs straight over the V notch at 0 deg, so the notch lines dangle
    iron, issues = import_dxf(FIXTURE.read_bytes(), _reference_8_6())
    assert iron is None
    assert [(i.rule, i.severity) for i in issues] == [("open_loop", "error")] * 2
    assert "(80.0, 1.9) mm" in issues[0].message and "(78.1, -0.0) mm" in issues[1].message


def test_onshape_file_with_arc_trimmed_imports_holes():
    doc = ezdxf.read(io.StringIO(FIXTURE.read_text()))
    msp = doc.modelspace()
    arc = next(e for e in msp if e.dxftype() == "ARC" and abs(e.dxf.start_angle - 316.3411) < 1e-3)
    lo, hi = arc.dxf.start_angle, arc.dxf.end_angle
    msp.delete_entity(arc)
    msp.add_arc((0, 0), 80, lo, 360 - 1.3411021047207)
    msp.add_arc((0, 0), 80, 1.3411021047207, hi)
    iron, issues = import_dxf(_bytes(doc), _reference_8_6())
    assert issues == []
    assert len(iron.rotor_holes) == 6 and len(iron.stator_holes) == 8


def test_binary_dxf_is_read(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 10)
    msp.add_arc((30, 0), 5, 0, 90)
    msp.add_line((35, 0), (30, 5))
    msp.add_ellipse((60, 0), (10, 0), 0.5)
    path = tmp_path / "b.dxf"
    doc.saveas(path, fmt="bin")
    assert path.read_bytes().startswith(b"AutoCAD Binary DXF")
    loops, issues = read_loops(path.read_bytes())
    assert issues == [] and len(loops) == 3
    assert sorted(len(l) > 4 for l in loops) == [False, False, True]
    assert sum(isinstance(s, Arc) for l in loops for s in l) == 1


def test_garbage_is_dxf_file():
    _, issues = read_loops(b"not a dxf at all")
    assert _errs(issues) == {"dxf_file"}


def _true_ellipse_dist(q, a, b):
    """Distance estimate of mm point q to the ellipse with semi-axes a, b (axis aligned at the origin)."""
    import numpy as np
    t = np.linspace(0, 2 * math.pi, 200001)
    return float(np.min(np.hypot(a * np.cos(t) - q[0], b * np.sin(t) - q[1])))


def test_full_ellipse_flattened():
    doc = _doc()
    doc.modelspace().add_ellipse((0, 0), (10, 0), 0.5)
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1
    assert all(isinstance(s, Line) for s in loops[0]) and len(loops[0]) > 20
    for s in loops[0]:
        mid = ((s.start[0] + s.end[0]) / 2 / MM, (s.start[1] + s.end[1]) / 2 / MM)
        assert _true_ellipse_dist(mid, 10, 5) <= 1e-3 + 1e-4


def test_ellipse_reading_is_deterministic():
    doc = _doc()
    doc.modelspace().add_ellipse((3, 4), (10, 0), 0.5)
    assert read_loops(_bytes(doc)) == read_loops(_bytes(doc))


def test_circular_ellipse_gives_arcs():
    doc = _doc()
    doc.modelspace().add_ellipse((20, 0), (0, 5), 1.0)
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1
    assert all(isinstance(s, Arc) for s in loops[0])
    assert all(s.center == pytest.approx((0.02, 0.0), abs=1e-12) for s in loops[0])
    assert all(math.dist(s.start, s.center) == pytest.approx(5 * MM, abs=1e-9) for s in loops[0])


def test_partial_ellipse_joins_lines():
    doc = _doc()
    msp = doc.modelspace()
    msp.add_ellipse((0, 0), (10, 0), 0.5, start_param=0, end_param=math.pi)
    msp.add_line((-10, 0), (10, 0))
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1
    assert sum(isinstance(s, Line) for s in loops[0]) > 10


def test_flipped_ellipse_keeps_wcs_coordinates():
    doc = _doc()
    # WCS ellipse centred at (30, 0) with semi-axes 10 and 5; ELLIPSE stores WCS data plus the extrusion
    doc.modelspace().add_ellipse((30, 0, 0), (10, 0, 0), 0.5, dxfattribs={"extrusion": (0, 0, -1)})
    loops, issues = read_loops(_bytes(doc))
    assert issues == [] and len(loops) == 1
    xs = [c[0] / MM for s in loops[0] for c in (s.start, s.end)]
    ys = [c[1] / MM for s in loops[0] for c in (s.start, s.end)]
    assert min(xs) == pytest.approx(20, abs=2e-3) and max(xs) == pytest.approx(40, abs=2e-3)
    assert min(ys) == pytest.approx(-5, abs=2e-3) and max(ys) == pytest.approx(5, abs=2e-3)


def test_tilted_ellipse_refused():
    doc = _doc()
    doc.modelspace().add_line((0, 0), (1, 1))
    doc.modelspace().add_ellipse((0, 0, 0), (10, 0, 0), 0.5, dxfattribs={"extrusion": (1, 0, 0)})
    _, issues = read_loops(_bytes(doc))
    assert _errs(issues) == {"dxf_flat"}


def test_crlf_line_endings():
    doc = _doc()
    _square(doc.modelspace(), 0, 0, 10)
    loops, issues = read_loops(_bytes(doc).replace(b"\n", b"\r\n"))
    assert issues == [] and len(loops) == 1


def _set_group(text: str, after: str, code: str, value: str) -> str:
    """Replace the value of the first group `code` that follows the first `after` line in a DXF text."""
    k = text.index(f"\n{code}\n", text.index(f"\n{after}\n"))
    e = text.index("\n", k + len(code) + 2)
    return f"{text[:k]}\n{code}\n{value}{text[e:]}"


def test_removed_entity_is_an_error():
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 100)
    msp.add_spline(fit_points=[(40, 40), (60, 40), (60, 60), (40, 60), (40, 40)])
    loops, issues = read_loops(_set_group(_bytes(doc).decode(), "SPLINE", " 71", "0").encode())
    assert loops == [] and _errs(issues) == {"dxf_file"}
    assert "1 SPLINE (#" in issues[0].message and "removed" in issues[0].message


def test_removed_entity_in_binary_dxf_is_an_error(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    _square(msp, 0, 0, 100)
    sp = msp.add_spline(fit_points=[(40, 40), (60, 40), (60, 60), (40, 60), (40, 40)])
    sp.dxf.__dict__["degree"] = 0   # bypass the writer's range check
    path = tmp_path / "b.dxf"
    doc.saveas(path, fmt="bin")
    loops, issues = read_loops(path.read_bytes())
    assert loops == [] and _errs(issues) == {"dxf_file"}
    assert "1 SPLINE (#" in issues[0].message


def test_cosmetic_repairs_do_not_refuse():
    doc = _doc()
    _square(doc.modelspace(), 0, 0, 10)
    for e in doc.modelspace():
        e.dxf.linetype = "nosuch"
    text = _bytes(doc).decode()
    # an out-of-range colour index on every line
    head, body = text.split("\nENTITIES\n")
    text = head + "\nENTITIES\n" + body.replace("\n  8\n0\n", "\n  8\n0\n 62\n300\n")
    assert "\n 62\n300\n" in text
    loops, issues = read_loops(text.encode())
    assert issues == [] and len(loops) == 1 and len(loops[0]) == 4


def test_degenerate_ellipses_reported():
    for ratio in (0.5, 1.0):
        doc = _doc()
        _square(doc.modelspace(), 0, 0, 10)
        doc.modelspace().add_ellipse((30, 0), (5, 0), ratio, start_param=1.0, end_param=1.0)
        _, issues = read_loops(_bytes(doc))
        assert [i.rule for i in issues] == ["dxf_entity"] and "ELLIPSE near (30.0, 0.0) mm" in issues[0].message


def test_negative_ratio_circular_ellipse_gives_arcs():
    doc = _doc()
    doc.modelspace().add_ellipse((20, 0), (5, 0), 1.0)
    loops, issues = read_loops(_set_group(_bytes(doc).decode(), "ELLIPSE", " 40", "-1.0").encode())
    assert issues == [] and len(loops) == 1 and all(isinstance(s, Arc) for s in loops[0])
    # the parameter runs clockwise for ratio -1: from (25, 0) mm the first arc turns towards negative y
    assert loops[0][0].start == pytest.approx((0.025, 0.0), abs=1e-9)
    assert loops[0][0].end[1] < 0
    assert all(s.center == pytest.approx((0.02, 0.0), abs=1e-12) for s in loops[0])


def test_r12_without_entity_handles_imports():
    doc = ezdxf.new("R12")
    doc.header["$INSUNITS"] = 4
    _square(doc.modelspace(), 0, 0, 10)
    head, body = _bytes(doc).decode().split("\nENTITIES\n")
    body, tail = body.split("\nENDSEC\n", 1)
    lines = body.split("\n")
    kept, k = [], 0
    while k < len(lines):
        if lines[k].strip() == "5" and k % 2 == 0:
            k += 2
            continue
        kept.append(lines[k])
        k += 1
    text = head + "\nENTITIES\n" + "\n".join(kept) + "\nENDSEC\n" + tail
    assert text.split("\nENTITIES\n")[1].split("\nENDSEC\n")[0].count("\n  5\n") == 0
    loops, issues = read_loops(text.encode())
    assert issues == [] and len(loops) == 1


def test_duplicate_entity_handles_refused():
    # ezdxf keeps one entity per handle and drops the rest, so the drawing lost geometry
    doc = _doc()
    _square(doc.modelspace(), 0, 0, 10)
    h = [e.dxf.handle for e in doc.modelspace()]
    text = _bytes(doc).decode()
    head, body = text.split("\nENTITIES\n")
    for x in h[1:]:
        body = body.replace(f"\n  5\n{x}\n", f"\n  5\n{h[0]}\n")
    assert body.count(f"\n  5\n{h[0]}\n") == 4
    loops, issues = read_loops((head + "\nENTITIES\n" + body).encode())
    assert loops == [] and _errs(issues) == {"dxf_file"} and "3 LINE" in issues[0].message


def _with_paper_geometry():
    doc = _doc()
    _square(doc.modelspace(), 0, 0, 10)
    paper = doc.layouts.get("Layout1")
    paper.add_line((0, 0), (200, 0))
    paper.add_circle((50, 50), 20)
    return doc


def test_paper_layout_geometry_ignored():
    loops, issues = read_loops(_bytes(_with_paper_geometry()))
    assert issues == [] and len(loops) == 1


def test_paper_layout_geometry_ignored_binary(tmp_path):
    path = tmp_path / "p.dxf"
    _with_paper_geometry().saveas(path, fmt="bin")
    loops, issues = read_loops(path.read_bytes())
    assert issues == [] and len(loops) == 1
