import numpy as np

from srmapp.thermal_fields import KINDS, ThermalFields, read_fields, write_fields


def test_round_trip(tmp_path):
    nan = np.full((2, 4), np.nan, np.float32)
    f = ThermalFields(np.zeros((4, 2), np.float32), np.array([[0, 1, 2], [1, 2, 3]], np.int32),
                      np.array([0, len(KINDS) - 1], np.uint8), np.array([1000.0, 2000.0]),
                      np.arange(8, dtype=np.float32).reshape(2, 4) + 40, nan, np.array([90.0, 95.0]),
                      np.array([np.nan, np.nan]))
    p = tmp_path / "f.npz"
    write_fields(p, f)
    g = read_fields(p)
    for k in f.__dataclass_fields__:
        np.testing.assert_array_equal(getattr(g, k), getattr(f, k))
        assert getattr(g, k).dtype == getattr(f, k).dtype
    assert list(tmp_path.glob("*.tmp.npz")) == []
