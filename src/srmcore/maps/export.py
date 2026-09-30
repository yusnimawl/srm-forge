"""CSV and MATLAB .mat exports of a `MapReport`. Floats are written with `repr` precision, NaN as `nan`."""
import csv
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy.io import savemat

from .checks import MapReport
from .run import require_complete

_KEY_UNITS = {"la": "H", "lu": "H", "la_lu": "1", "peak_torque": "N*m", "psi_max": "Wb", "i_max": "A",
              "aligned_angle": "rad", "unaligned_angle": "rad"}


def _cell(x):
    if isinstance(x, str):
        return x
    return repr(float(x)) if isinstance(x, (float, np.floating)) else int(x)


def _write(path: Path, header, rows) -> Path:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows([_cell(x) for x in row] for row in rows)
    return path


def export_csv(report: MapReport, directory) -> list[Path]:
    """Write psi_map.csv, inverse_current.csv and key_numbers.csv into `directory`."""
    require_complete(report.result)
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    r, t = report.result, report.tables
    e = r.circuits.index(r.excited)
    na, nc = r.psi.shape[:2]
    psi_map = _write(
        d / "psi_map.csv",
        ["angle_rad", "current_A", *[f"psi_{c}" for c in r.circuits],
         "torque_Nm", "coenergy_J", "l_inc_H", "status", "filled"],
        ([r.angles[a], r.currents[c], *r.psi[a, c], r.torque_arkkio[a, c], r.coenergy[a, c],
          r.l_inc[a, c, e], r.status[a, c], r.filled[a, c]] for a in range(na) for c in range(nc)))
    inverse = _write(
        d / "inverse_current.csv", ["angle_rad", "psi_Wb", "current_A", "torque_Nm", "flat"],
        ([t.angles[a], t.psi_grid[p], t.current[a, p], t.torque[a, p], t.flat[a, p]]
         for a in range(na) for p in range(len(t.psi_grid))))
    key = _write(d / "key_numbers.csv", ["name", "value", "unit"],
                 ((k, float(v), _KEY_UNITS[k]) for k, v in asdict(report.key_numbers).items()))
    return [psi_map, inverse, key]


def export_mat(report: MapReport, path, provenance_hash: str | None = None) -> Path:
    """Write the map, ∂ψ/∂θ, the inverse tables and the key numbers to a MATLAB v5 file."""
    require_complete(report.result)
    r, t = report.result, report.tables
    data = {
        "angles": r.angles, "currents": r.currents, "psi": r.psi, "torque": r.torque_arkkio,
        "coenergy": r.coenergy, "l_inc": r.l_inc, "dpsi_dtheta": report.dpsi_dtheta,
        "psi_grid": t.psi_grid, "current_of_psi": t.current, "torque_of_psi": t.torque,
        "status": r.status, "filled": r.filled, "flat": t.flat, "circuits": np.array(r.circuits, dtype=object),
        "key_numbers": asdict(report.key_numbers),
    }
    if provenance_hash is not None:
        data["provenance_hash"] = provenance_hash
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    savemat(path, data)
    return path
