"""Compare reduced stage-2 map grids with a 12 x 8 map on the example 8/6 (I_max 20 A).

    PYTHONPATH=tests python examples/v0_grid_study.py

Prints the relative error of peak torque, La and the envelope torque at 300, 3000 and 9000 rpm, and the wall time per grid."""
import time

from conftest import make_8_6

from srmapp.drive.envelope import envelope
from srmcore.maps import build_map
from srmcore.maps.results import key_numbers
from srmcore.model.design import Design, MeshSettings

# Test-drive parameters for the envelope comparison (not a design point).
V_DC = 400.0   # V
R_PHASE = 0.1  # ohm

GRIDS = [(12, 8), (8, 4), (10, 5), (10, 6), (12, 5), (12, 6)]

if __name__ == "__main__":
    machine = make_8_6()
    design = Design(machine=machine, mesh=MeshSettings(preset="screening"))
    rows = {}
    for n_a, n_i in GRIDS:
        t0 = time.perf_counter()
        r = build_map(design, 20.0, n_angles=n_a, n_currents=n_i)
        wall = time.perf_counter() - t0
        k = key_numbers(r, machine)
        env = envelope(r, machine, V_DC, R_PHASE, [300.0, 3000.0, 9000.0])
        rows[(n_a, n_i)] = (k.peak_torque, k.la, *env.torque, wall)
    ref = rows[GRIDS[0]]
    print(f"{'grid':>8}{'T_peak':>9}{'La':>9}{'T@300':>9}{'T@3000':>9}{'T@9000':>9}{'wall s':>8}   (rel. error vs 12x8)")
    for g, v in rows.items():
        err = [abs(a - b) / abs(b) for a, b in zip(v[:5], ref[:5])]
        print(f"{g[0]:>4}x{g[1]:<3}" + "".join(f"{e:9.2%}" for e in err) + f"{v[5]:8.0f}")
