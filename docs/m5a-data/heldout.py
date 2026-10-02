"""Measure fem_checks held-out errors on the cached M5a full maps (one JSON line per design)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"D:\y\srm-designer\tests")
from conftest import make_8_6, make_12_8, make_24_16  # noqa: E402

from srmcore.maps.api import build_map  # noqa: E402
from srmcore.maps.fem_checks import fem_checks  # noqa: E402
from srmcore.model.design import Design, MeshSettings  # noqa: E402

DESIGNS = {"8_6": make_8_6(), "8_6_sharp": make_8_6(stator_fillet_radius=0, rotor_fillet_radius=0),
           "12_8": make_12_8(), "24_16": make_24_16()}
I_MAX = json.loads(Path(r"D:\y\srm-designer\docs\m5a-data\i_max.json").read_text())
if __name__ == "__main__":
    for name, m in DESIGNS.items():
        design = Design(machine=m, mesh=MeshSettings(preset="full"))
        r = build_map(design, I_MAX.get(name, 20.0), cache_dir=Path(tempfile.gettempdir()) / "m5a-map-cache")
        for n_samples in (16, 64):
            checks = fem_checks(design, r, n_samples=n_samples)
            out = {"design": name, "n_samples": n_samples, **{c.name: c.value for c in checks}}
            print(json.dumps(out), flush=True)
