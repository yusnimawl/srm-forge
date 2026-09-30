"""Synthetic MapResults (no FEM): ψ = L(θ)·i, or ψ = Ψs·tanh(L(θ)·i / Ψs) when `psi_sat` is given."""
import numpy as np

from srmcore.maps.run import STATUS_OK, MapResult

NR = 6
PERIOD = 2 * np.pi / NR
L0, L1 = 2e-3, 1e-3


def inductance(theta):
    return L0 + L1 * np.cos(NR * theta)


def dinductance(theta):
    return -NR * L1 * np.sin(NR * theta)


def synthetic_map(n_angles=16, currents=None, psi_sat=None, complete=True, circuits=("A", "B", "C", "D")):
    # warped, non-uniform angle grid on [0, PERIOD)
    angles = PERIOD * np.linspace(0, 1, n_angles, endpoint=False) ** 1.3
    cur = np.linspace(0, 20, 9) if currents is None else np.asarray(currents, float)
    lam = inductance(angles)[:, None] * cur[None, :]
    psi = np.zeros((n_angles, len(cur), len(circuits)))
    psi[..., 0] = lam if psi_sat is None else psi_sat * np.tanh(lam / psi_sat)
    shape = (n_angles, len(cur))
    # torque of the linear model, -∂W'/∂θ
    torque = -0.5 * dinductance(angles)[:, None] * cur[None, :] ** 2
    zeros = np.zeros(shape)
    return MapResult(angles, cur, tuple(circuits), "A", psi, torque, torque, zeros, zeros,
                     np.zeros(psi.shape), np.zeros((*shape, 8, 2)), np.ones(shape, dtype=np.int32),
                     np.full(shape, STATUS_OK, dtype=np.int8), np.zeros(shape, dtype=bool), complete)
