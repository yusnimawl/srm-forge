"""`b_waveform` returns the element of the stroke fields that contains the point, as lamination B."""
import math

import numpy as np
import pytest
pytest.importorskip("ngsolve")

from conftest import make_8_6
from srmapp import field, losses
from srmcore.maps.stroke import phase_currents, stroke_angles, stroke_fields, stroke_key
from srmcore.materials.library import load_material
from srmcore.model.design import Design, MeshSettings

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
TAU = 2 * math.pi / DESIGN.machine.n_rotor_poles
N_T = 8
RPM = 1500.0


def test_b_waveform_matches_stroke_fields(tmp_path):
    static = field.static_mesh(DESIGN.to_json())
    angles = stroke_angles(static, TAU, N_T)
    currents = phase_currents(np.array([0.0, 6.0, 12.0, 12.0, 6.0, 0.0, 0.0, 0.0]), 4)
    kind = np.array([static.region_kind[n] for n in static.region_names])
    n_s = int((kind[static.stator.region_ids] == "stator_iron").sum())
    n_r = int((kind[static.rotor.region_ids] == "rotor_iron").sum())
    rng = np.random.default_rng(1)
    key = stroke_key(DESIGN, angles, currents)
    (tmp_path / "strokes").mkdir()
    np.savez(tmp_path / "strokes" / f"{key}.npz", stator=rng.normal(size=(len(angles), n_s, 2)),
             coil=np.zeros((len(angles), 1, 2)), rotor=rng.normal(size=(len(angles), n_r, 2)))
    fields = stroke_fields(static, DESIGN, angles, currents, cache_dir=tmp_path)   # loads, does not solve
    omega = RPM * 2 * math.pi / 60
    sf = load_material(DESIGN.machine.materials.stator).stacking_factor
    for side, w in (("stator", fields.stator), ("rotor", fields.rotor)):
        e = 5
        x, y = w.centroids[e]
        out = losses.b_waveform(DESIGN, key, N_T, RPM, x, y, cache_dir=tmp_path)
        assert out["side"] == side
        radial = np.array([x, y]) / math.hypot(x, y)
        b = w.b[:, e] / sf
        assert np.allclose(out["b_r"], b @ radial) and np.allclose(out["b_t"], b @ [-radial[1], radial[0]])
        n = len(out["t"])
        assert n == w.b.shape[0] and out["t"][0] == 0.0
        assert out["t"][-1] == pytest.approx(w.period_s(omega) * (n - 1) / n)
        assert out["region"] == w.region[e]
