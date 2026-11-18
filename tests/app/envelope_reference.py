"""The drive simulation as it was before the winding scan was sped up (srmapp 0.7.0, every stroke advanced at every
step, torque interpolated twice per step). Tests compare the current `srmapp.drive.envelope._simulate` and the
scan built on it with this copy, bit for bit; do not edit it."""
import numpy as np


def _simulate(t, omega: float, volts: float, r: float, on: np.ndarray, off: np.ndarray,
              trace: bool = False):
    """One stroke for every (on, off) index pair, each simulated from its turn-on over exactly one period on the
    periodic table (the flux tail runs past alignment into the start of the next period). `off` may exceed the table
    end. Returns (work_torque, work_loop, ∫i² dθ, valid), and with `trace` also ψ and i at every step from turn-on,
    shape (n_theta, n_pairs). A stroke is valid when its flux is back to 1 % of its peak before the same phase turns
    on again."""
    n = t.theta.size - 1
    psi, i = np.zeros(on.size), np.zeros(on.size)
    w_t, w_l, i2, peak = np.zeros(on.size), np.zeros(on.size), np.zeros(on.size), np.zeros(on.size)
    dth = t.theta[1] - t.theta[0]
    psi_t, i_t = np.zeros((n + 1, on.size)), np.zeros((n + 1, on.size))
    for a in range(int(on.max()) + n):
        k = a % n
        active = (a >= on) & (a < on + n)
        pulse = a < off
        v = np.where(pulse, volts, -volts)
        new = psi + (v - r * i) / omega * dth
        new = np.where(pulse, np.minimum(new, t.psi[k + 1, -1]), new)     # current limit while the pulse is on
        new = np.maximum(new, 0.0)
        # zero flux is zero current even when the map row has tied leading zeros
        i_new = np.where(new > 0, np.interp(new, t.psi[k + 1], t.current), 0.0)
        tq_old = np.interp(i, t.current, t.torque[k])
        tq_new = np.interp(i_new, t.current, t.torque[k + 1])
        new, i_new = np.where(active, new, psi), np.where(active, i_new, i)
        w_t += 0.5 * (tq_old + tq_new) * dth * active
        w_l += 0.5 * (i + i_new) * (new - psi)
        i2 += 0.5 * (i**2 + i_new**2) * dth * active
        psi, i = new, i_new
        peak = np.maximum(peak, psi)
        if trace:
            j = a + 1 - on
            hit = np.flatnonzero(active)
            psi_t[j[hit], hit] = psi[hit]
            i_t[j[hit], hit] = i[hit]
    valid = psi <= 0.01 * np.maximum(peak, 1e-12)       # the flux must be gone before the next turn-on
    if trace:
        return w_t, w_l, i2, valid, psi_t, i_t
    return w_t, w_l, i2, valid
