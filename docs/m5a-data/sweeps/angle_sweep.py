"""THROWAWAY: dense angle sweep (every band pitch over one rotor pole pitch) on the new full mesh
(screening x scale 2^-0.5), currents 0, i_La, I_max/2, I_max. Saves sweep_<design>.npz."""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\y\srm-designer\tests")
from conftest import make_8_6, make_12_8, make_24_16  # noqa: E402

from srmcore.maps.grids import LA_CURRENT_FRACTION  # noqa: E402
from srmcore.maps.run import run_map  # noqa: E402
from srmcore.mesh import build_machine_mesh  # noqa: E402
from srmcore.mesh.settings import resolve_mesh_settings  # noqa: E402
from srmcore.model.design import Design, MeshSettings  # noqa: E402

DESIGNS = {"8_6": make_8_6(), "8_6_sharp": make_8_6(stator_fillet_radius=0, rotor_fillet_radius=0),
           "12_8": make_12_8(), "24_16": make_24_16()}
I_MAX = json.loads(Path(r"D:\y\srm-designer\docs\m5a-data\i_max.json").read_text())
OUT = Path(__file__).parent

if __name__ == "__main__":
    name = sys.argv[1]
    m = DESIGNS[name]
    i_max = I_MAX.get(name, 20.0)
    design = Design(machine=m, mesh=MeshSettings(preset="screening", scale=2 ** -0.5))
    d = resolve_mesh_settings(m, design.mesh).band_divisions
    tau = 2 * math.pi / m.n_rotor_poles
    n = round(tau / (2 * math.pi / d))
    angles = np.arange(n) * 2 * math.pi / d
    currents = np.array([0.0, LA_CURRENT_FRACTION * i_max, i_max / 2, i_max])
    print(name, "divisions", d, "angles", n, flush=True)
    r = run_map(build_machine_mesh(design), design, angles, currents, workers=8,
                progress=lambda k, t: print(f"{k}/{t}", flush=True) if k % 100 == 0 else None)
    np.savez(OUT / f"sweep_{name}.npz", angles=r.angles, currents=r.currents, psi=r.psi[..., 0],
             torque=r.torque_arkkio, divisions=d, tau=tau)
    print("saved", name, flush=True)
