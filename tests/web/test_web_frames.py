import numpy as np
import pytest

from srmweb.frames import pack
from web_support import unpack


def test_round_trip_and_alignment():
    arrays = {"x": np.arange(6, dtype=np.float32).reshape(3, 2), "t": np.arange(5, dtype=np.uint32),
              "r": np.arange(3, dtype=np.uint8)}
    header, h, out = unpack(pack({"a": 1, "b": [1.5, "s"]}, arrays))
    assert header["meta"] == {"a": 1, "b": [1.5, "s"]}
    assert (4 + h) % 8 == 0
    for name, array in arrays.items():
        assert out[name].dtype == array.dtype and out[name].shape == array.shape
        np.testing.assert_array_equal(out[name], array)
    assert all(a["offset"] % 8 == 0 for a in header["arrays"])


def test_unsupported_dtype_raises():
    with pytest.raises(ValueError):
        pack({}, {"x": np.zeros(2, dtype=np.float64)})
