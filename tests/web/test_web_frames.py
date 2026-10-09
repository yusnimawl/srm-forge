import json
import struct

import numpy as np
import pytest

from srmweb.frames import pack


def unpack(blob: bytes):
    (h,) = struct.unpack_from("<I", blob)
    header = json.loads(blob[4:4 + h])
    data = blob[4 + h:]
    out = {}
    for a in header["arrays"]:
        n = int(np.prod(a["shape"]))
        out[a["name"]] = np.frombuffer(data, dtype=np.dtype(a["dtype"]).newbyteorder("<"), count=n,
                                       offset=a["offset"]).reshape(a["shape"])
    return header, h, out


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
