"""The temperature fields of a rating: the thermal mesh and, per rated speed, the steady and the end-of-peak node temperatures."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

KINDS = ("stator_iron", "rotor_iron", "shaft", "coil", "liner", "air")


@dataclass(frozen=True)
class ThermalFields:
    nodes: np.ndarray                  # (n, 2) float32, m
    triangles: np.ndarray              # (m, 3) int32
    kind: np.ndarray                   # (m,) uint8, index into KINDS
    rpm: np.ndarray                    # (s,) float64
    steady: np.ndarray                 # (s, n) float32, degC, at the rated continuous torque
    peak: np.ndarray                   # (s, n) float32, degC, end of the peak; NaN row without a peak state
    end_winding_steady_c: np.ndarray   # (s,) max over the end-winding lumps, NaN when unknown
    end_winding_peak_c: np.ndarray     # (s,)


def write_fields(path: Path, f: ThermalFields) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **{k: getattr(f, k) for k in f.__dataclass_fields__})
    tmp.replace(path)


def read_fields(path: Path) -> ThermalFields:
    with np.load(path) as z:
        return ThermalFields(**{k: z[k] for k in ThermalFields.__dataclass_fields__})
