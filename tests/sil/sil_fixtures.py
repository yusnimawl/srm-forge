"""Shared helpers for the SIL tests: the analytic test motor and a child-process caller for compiled libraries."""

import ctypes
import math
import multiprocessing as mp
import pickle
import queue
import time

import numpy as np

from srmsil.tables import MotorData

L_U, L_A, PSI_S = 1e-3, 8e-3, 0.08


def analytic_motor(n_phases=4, n_rotor_poles=6, resistance=0.5, bus_voltage=48.0, saturating=True) -> MotorData:
    """L(θ) = L_u + (L_a − L_u)(1 + cos(N_r θ))/2, phase A aligned at θ = 0. Linear ψ = L i, or saturating
    ψ = ψ_s tanh(L i / ψ_s); torque is ∂W′/∂θ at constant i."""
    angles = np.arange(48) * (2 * math.pi / n_rotor_poles / 48)
    currents = np.linspace(0.0, 20.0, 21)
    th, i = np.meshgrid(angles, currents, indexing="ij")
    L = L_U + (L_A - L_U) * (1 + np.cos(n_rotor_poles * th)) / 2
    dL = -(L_A - L_U) / 2 * n_rotor_poles * np.sin(n_rotor_poles * th)
    if saturating:
        x = L * i / PSI_S
        psi = PSI_S * np.tanh(x)
        torque = (-PSI_S**2 / L**2 * np.log(np.cosh(x)) + PSI_S / L * np.tanh(x) * i) * dL
    else:
        psi = L * i
        torque = 0.5 * dL * i**2
    return MotorData(angles, currents, psi, torque, resistance, n_phases, n_rotor_poles, bus_voltage)


def _call(lib, name, args, q):
    f = getattr(ctypes.CDLL(str(lib)), name)
    f.restype = ctypes.c_double
    f.argtypes = [ctypes.c_double] * len(args)
    q.put(f(*args))


def call_in_child(lib, name, *float_args) -> float:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_call, args=(lib, name, float_args, q))
    p.start()
    try:
        out = q.get(timeout=60)
        p.join()
        return out
    finally:
        if p.is_alive():
            p.kill()


def _child(q, fn, args):
    try:
        q.put(("ok", pickle.dumps(fn(*args))))
    except BaseException as e:  # noqa: BLE001 - relayed to the parent
        try:
            q.put(("err", pickle.dumps(e)))
        except Exception:
            q.put(("err", pickle.dumps(RuntimeError(repr(e)))))


def run_in_child(fn, *args, timeout=300):
    """Run fn(*args) in a spawned process and return its picklable result; re-raise its exception; kill the child."""
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(q, fn, args))
    p.start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                kind, blob = q.get(timeout=0.5)
                break
            except queue.Empty:
                if not p.is_alive():
                    try:
                        kind, blob = q.get(timeout=1)
                        break
                    except queue.Empty:
                        raise RuntimeError(f"child exited with code {p.exitcode}") from None
                if time.monotonic() > deadline:
                    raise TimeoutError(f"child still running after {timeout} s") from None
        out = pickle.loads(blob)
        if kind == "err":
            raise out
        return out
    finally:
        if p.is_alive():
            p.kill()
        p.join()
