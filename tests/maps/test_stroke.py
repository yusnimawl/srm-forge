"""Stroke fields on the 8/6 screening mesh: phase symmetry, cache, failure, rotor waveform, region labels."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.fields.solution import SolveStatus
from srmcore.maps import stroke
from srmcore.maps.point import PointResult
from srmcore.maps.stroke import phase_currents, rotor_pitches, stroke_angles, stroke_fields
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MapFailed

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
TAU = 2 * math.pi / DESIGN.machine.n_rotor_poles
N_T = 8
I_A = np.array([0.0, 6.0, 12.0, 12.0, 6.0, 0.0, 0.0, 0.0])
CURRENTS = phase_currents(I_A, 4)


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


@pytest.fixture(scope="module")
def angles(static):
    return stroke_angles(static, TAU, N_T)


@pytest.fixture(scope="module")
def fields(static, angles):
    return stroke_fields(static, DESIGN, angles, CURRENTS, workers=1)


def test_phase_currents_shift():
    assert np.array_equal(CURRENTS[:, 1], np.roll(I_A, 2))
    assert np.array_equal(CURRENTS[:, 0], I_A)


def test_stroke_angles_snapped_unique(static, angles):
    assert len(angles) == N_T and np.all(np.diff(angles) > 0) and angles[-1] < TAU
    assert np.allclose(np.diff(angles), TAU / N_T, atol=2 * math.pi / static.settings.band_divisions)


def test_rotor_pitches_8_6(static):
    # Opposite poles of a phase carry opposite polarity, so the rotor element returns after a full turn.
    assert rotor_pitches(static, DESIGN) == 6


def test_regions_cover_iron(static, fields):
    assert set(fields.region) <= {"stator_pole", "stator_yoke", "rotor_pole", "rotor_yoke"}
    assert {"stator_pole", "stator_yoke", "rotor_pole", "rotor_yoke"} == set(fields.region)
    kind = np.array([static.region_kind[n] for n in static.region_names])[static.stator.region_ids]
    t = static.stator.nodes[static.stator.triangles[kind == "stator_iron"]]
    area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1])).sum()
    stator = np.char.startswith(fields.region, "stator")
    assert fields.areas[stator].sum() == pytest.approx(area, rel=1e-9)
    assert fields.b_iron.shape == (N_T * 6, len(fields.areas), 2)
    assert np.all(fields.material[stator] == DESIGN.machine.materials.stator)


def _pole_b(fields, pole):
    """Mean B over the stator pole elements of one pole, per sample of the first pitch."""
    stator = np.flatnonzero(fields.region == "stator_pole")
    c = fields.centroids[stator]
    index = np.round((np.arctan2(c[:, 1], c[:, 0]) % (2 * math.pi)) / (math.pi / 4)).astype(int) % 8
    return fields.b_iron[:N_T, stator[index == pole]].mean(axis=1)


def test_phase_shift_symmetry(fields):
    # Pole 3 carries phase B, pole 0 phase A (lettering runs against the pole order); the other poles of the
    # stroke differ by coupling, so compare the mean pole B of the two phases a quarter stroke apart.
    peak = np.abs(fields.b_iron).max()
    a, b = _pole_b(fields, 0), _pole_b(fields, 3)
    rot = np.array([[math.cos(3 * math.pi / 4), math.sin(3 * math.pi / 4)],
                    [-math.sin(3 * math.pi / 4), math.cos(3 * math.pi / 4)]])
    assert np.abs(b - np.roll(a, N_T // 4, axis=0) @ rot).max() < 0.02 * peak


def test_opposite_pole_has_inverted_polarity(fields):
    # Poles 0 and 4 are the two poles of phase A, wound with opposite polarity: the field at the opposite pole
    # is minus the rotated field, which for a half-turn rotation is the same vector.
    peak = np.abs(fields.b_iron).max()
    assert np.abs(_pole_b(fields, 0) - _pole_b(fields, 4)).max() < 0.02 * peak


def test_rotor_waveform_periodic(fields):
    rotor = np.flatnonzero(np.char.startswith(fields.region, "rotor"))
    hot = rotor[np.argsort(np.abs(fields.b_iron[:, rotor]).max(axis=(0, 2)))[-20:]]
    w = fields.b_iron[:, hot]                                    # (n_t, 20, 2)
    seam = np.abs(w[0] - w[-1]).max()
    step = np.abs(np.diff(w, axis=0)).max()
    assert seam <= 3 * step


def test_cache_hit(static, angles, tmp_path):
    calls = []
    first = stroke_fields(static, DESIGN, angles, CURRENTS, workers=1, cache_dir=tmp_path,
                          progress=lambda d, n: calls.append(d))
    n_first = len(calls)
    second = stroke_fields(static, DESIGN, angles, CURRENTS, workers=1, cache_dir=tmp_path,
                           progress=lambda d, n: calls.append(d))
    assert n_first == N_T and len(calls) == n_first
    assert np.array_equal(first.b_iron, second.b_iron) and np.array_equal(first.b_coil, second.b_coil)
    assert len(list((tmp_path / "strokes").glob("*.npz"))) == 1


def test_failed_point_writes_no_cache(static, angles, tmp_path, monkeypatch):
    def fake(static, design, angle, currents, solver, **kw):
        return PointResult(angle=angle, circuits=(), currents=np.zeros(4), psi=np.zeros(4), torque_arkkio=0.0,
                           torque_virtual_work=0.0, energy=0.0, coenergy=0.0, pole_force=np.zeros((8, 2)),
                           status=SolveStatus.NONCONVERGED, iterations=1, fallbacks=(), load_fraction=0.5)

    monkeypatch.setattr(stroke, "solve_point", fake)
    with pytest.raises(MapFailed, match="rotor angle"):
        stroke_fields(static, DESIGN, angles, CURRENTS, workers=1, cache_dir=tmp_path)
    assert not list((tmp_path / "strokes").glob("*")) if (tmp_path / "strokes").exists() else True
