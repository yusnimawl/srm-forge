import math

from conftest import make_8_6
from srmweb.geometry import outline_svg


def test_outline_svg_8_6():
    out = outline_svg(make_8_6())
    assert len(out["coils"]) == 16
    assert {c["sign"] for c in out["coils"]} == {"+", "-"}
    assert {c["phase"] for c in out["coils"]} == {"A", "B", "C", "D"}
    for key in ("stator", "rotor", "shaft"):
        assert out[key].startswith("M")
    assert all(c["d"].startswith("M") and c["name"] for c in out["coils"])
    x, y, w, h = out["view_box"]
    assert abs(w - 160) < 1 and abs(h - 160) < 1
    assert abs(x + w / 2) < 1e-6 and abs(y + h / 2) < 1e-6


def test_arc_flags_and_flip():
    from srmcore.topology.primitives import Arc
    from srmweb.geometry import _arc

    # counter-clockwise quarter arc in maths coordinates becomes sweep 0 after the y flip
    assert _arc(Arc((1e-3, 0), (0, 1e-3), (0, 0))) == "A 1 1 0 0 0 0 -1"
    assert _arc(Arc((0, 1e-3), (1e-3, 0), (0, 0))) == "A 1 1 0 0 1 1 0"
    assert math.isclose(1, 1)
