"""Per-region magnetic laws the solver evaluates: a linear law, or a processed B-H curve."""
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import numpy as np

from ..model.constants import MU0
from .bh import process_bh
from .library import load_material
from .schema import ConductorMaterial, SoftMagneticMaterial


class ReluctivityLaw(Protocol):
    """ν(|B|) for one material. BHCurve and LinearLaw implement it."""

    def nu_dnu(self, b2: np.ndarray) -> tuple[np.ndarray, np.ndarray]: ...

    def energy_density(self, b: np.ndarray) -> np.ndarray: ...

    def coenergy_density(self, b: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class LinearLaw:
    relative_permeability: float = 1.0

    @property
    def nu(self) -> float:
        return 1.0 / (MU0 * self.relative_permeability)

    def nu_dnu(self, b2):
        b2 = np.asarray(b2, float)
        return np.full_like(b2, self.nu), np.zeros_like(b2)

    def energy_density(self, b):
        return 0.5 * self.nu * np.asarray(b, float) ** 2

    def coenergy_density(self, b):
        return self.energy_density(b)


VACUUM = LinearLaw(1.0)


def law_for_material(material: SoftMagneticMaterial | ConductorMaterial) -> ReluctivityLaw:
    if isinstance(material, ConductorMaterial):
        return VACUUM
    curve, _ = process_bh(material.bh, material.stacking_factor, material.saturation_polarisation)
    return curve


@lru_cache(maxsize=None)
def library_law(name: str) -> ReluctivityLaw:
    """The law for a library material, processed once per process."""
    return law_for_material(load_material(name))
