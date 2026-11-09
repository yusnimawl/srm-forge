"""Thermal problem: the solid domain with its material arrays, lumps and the links between them."""
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from .domain import ThermalDomain


@dataclass(frozen=True)
class Lump:
    name: str
    capacity: float = 0.0            # J/K
    fixed_c: float | None = None     # a set temperature: coolant inlet, ambient
    hot_spot: bool = False           # counts in the hot spot (end windings)


@dataclass(frozen=True)
class LumpLink:
    a: str
    b: str
    conductance: float               # W/K


@dataclass(frozen=True)
class EdgeLink:
    edges: np.ndarray                # (e, 2) node indices
    lump: str
    h: float                         # W/(m²·K), area = edge length x depth


@dataclass(frozen=True)
class AreaLink:
    elements: np.ndarray
    lump: str
    g: float                         # W/(m²·K), area = element area


@dataclass(frozen=True)
class ThermalProblem:
    domain: ThermalDomain
    conductivity: np.ndarray         # (m,) W/(m·K), in-plane
    capacity: np.ndarray             # (m,) J/(m³·K)
    depth: float                     # m
    lumps: tuple[Lump, ...]
    links: tuple[LumpLink | EdgeLink | AreaLink, ...]


@dataclass(frozen=True)
class ThermalLoad:
    element_w_per_m3: np.ndarray
    lump_w: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Temperatures:
    field: np.ndarray                # (n,) degC
    lumps: dict[str, float]          # degC


class ThermalModelError(ValueError):
    pass


class ThermalRunaway(ThermalModelError):
    pass
