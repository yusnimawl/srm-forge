import io
import math

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
    msp.add_ellipse((30, 0), (5, 0), 0.5)
    _, issues = read_loops(_bytes(doc))
    assert _errs(issues) == {"dxf_entity"}
    assert "ELLIPSE" in issues[0].message


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
    # every flattened vertex lies on the curve; a chord between curve samples is within 1 um of it
    for s in loops[0]:
        if isinstance(s, Line) and s.start[1] > 5.5 * MM:
            q = (s.start[0] / MM, s.start[1] / MM)
            assert min(math.dist(q, c) for c in curve) < 5e-3


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
