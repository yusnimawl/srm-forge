"""Angle convergence of the iron loss computed from stroke fields."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.stroke import DEFAULT_STROKE_ANGLES, phase_currents, stroke_angles, stroke_fields
from srmcore.materials import loss_model
from srmcore.materials.library import load_material
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.post.iron_loss import waveform_loss

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
TAU = 2 * math.pi / DESIGN.machine.n_rotor_poles
OMEGA = 2 * math.pi * 1500 / 60
MODEL = loss_model("10JNEX900")


def _total_loss(static, n: int) -> float:
    angles = stroke_angles(static, TAU, n)
    i_a = 12.0 * np.clip(np.sin(math.pi * (angles / TAU - 0.1) / 0.5), 0.0, None) ** 2
    fields = stroke_fields(static, DESIGN, angles, phase_currents(i_a, DESIGN.machine.n_phases))
    total = 0.0
    for side in (fields.stator, fields.rotor):
        # Lamination flux density: the finite-element B is averaged over steel and insulation.
        b = side.b / load_material(DESIGN.machine.materials.stator).stacking_factor
        loss = waveform_loss(b, side.centroids, side.period_s(OMEGA), MODEL, weights=side.areas)
        total += float((loss.total * MODEL.density * side.areas * DESIGN.machine.stack_length).sum())
    return total


@pytest.mark.slow
def test_angle_convergence():
    static = build_machine_mesh(DESIGN)
    coarse, fine = _total_loss(static, DEFAULT_STROKE_ANGLES), _total_loss(static, 2 * DEFAULT_STROKE_ANGLES)
    change = abs(coarse - fine) / fine
    assert change < 0.02, f"iron loss changes {100 * change:.2f} % from {DEFAULT_STROKE_ANGLES} to {2 * DEFAULT_STROKE_ANGLES} angles"
