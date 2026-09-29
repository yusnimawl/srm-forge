"""Solver output (spec §6), as plain numpy data."""
from dataclasses import dataclass
from enum import Enum

import numpy as np


class SolveStatus(str, Enum):
    OK = "OK"
    OK_WITH_FALLBACK = "OK_WITH_FALLBACK"
    NONCONVERGED = "NONCONVERGED"


@dataclass(frozen=True, eq=False)
class FieldSolution:
    a: np.ndarray            # A_z per node, Wb/m
    b: np.ndarray            # (n_elements, 2) flux density per element, T, stator (global) frame
    nu: np.ndarray           # reluctivity per element, m/H
    dnu_db2: np.ndarray      # differential reluctivity dν/d(B²) per element
    energy: float            # W = L·∫∫0^B H dB dS, J
    coenergy: float          # W' = L·∫∫0^H B dH dS, J
    status: SolveStatus
    iterations: int
    residual: float          # final relative residual
    delta_a: float           # final relative Newton update
    fallbacks: tuple[str, ...] = ()
    # Fraction of the requested circuit currents this field was solved for. Below 1 only when the
    # current ramp stopped early (status NONCONVERGED); never build a ψ-i table from such a field.
    load_fraction: float = 1.0
