"""Binary frame format: a JSON header plus little-endian arrays, every array 8-byte aligned.

Layout: uint32 header length H, the UTF-8 JSON header `{"meta", "arrays": [{name, dtype, shape, offset}]}` padded
with spaces so that 4 + H is a multiple of 8, then the data section; `offset` counts bytes from its start."""
import json
import struct
from dataclasses import dataclass

import numpy as np

from srmapp.case import CaseInputs
from srmcore.model.design import Design

DTYPES = ("float32", "uint32", "uint8")


@dataclass(frozen=True)
class FieldContext:
    design: Design          # the reference-turns design the field is solved on
    inputs: CaseInputs
    k: float                # coil current / phase current, and the factor on the reported flux linkage
    i_max: float            # the map's top current, A
    winding_current: float  # peak phase current of the chosen winding, A


def pack(meta: dict, arrays: dict[str, np.ndarray]) -> bytes:
    entries, chunks, offset = [], [], 0
    for name, array in arrays.items():
        if array.dtype.name not in DTYPES:
            raise ValueError(f"array {name!r} has unsupported dtype {array.dtype.name}")
        data = np.ascontiguousarray(array).astype(array.dtype.newbyteorder("<"), copy=False).tobytes()
        entries.append({"name": name, "dtype": array.dtype.name, "shape": list(array.shape), "offset": offset})
        chunks.append(data + b"\0" * (-len(data) % 8))
        offset += len(chunks[-1])
    header = json.dumps({"meta": meta, "arrays": entries}, allow_nan=False).encode()
    header += b" " * (-(4 + len(header)) % 8)
    return struct.pack("<I", len(header)) + header + b"".join(chunks)


# The lane pickles its callable, so these are module-level; `field` is looked up at call time.
def mesh_task(design: Design, cache_dir):
    from srmapp import field
    return field.field_mesh(design, cache_dir=cache_dir)


def frame_task(design: Design, angle: float, coil_current: float, cache_dir):
    from srmapp import field
    return field.field_frame(design, angle, coil_current, cache_dir=cache_dir)
