import math

from conftest import make_8_6

from srmapp.sizing.estimates import active_volume
from srmcore.maps.end_winding import coil_geometry


def test_volume_of_the_8_6():
    m = make_8_6()
    od = m.stator_outer_diameter
    expected = math.pi / 4 * od**2 * (m.stack_length + 2 * (coil_geometry(m).build + m.slot_liner_thickness))
    assert abs(active_volume(m) - expected) <= 1e-12 * expected
    assert active_volume(m) > math.pi / 4 * od**2 * m.stack_length
