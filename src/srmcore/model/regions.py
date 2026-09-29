"""Region-kind vocabulary shared across layers: the validator, the mesh-size defaults and geometry's
region tagging all draw from the constants here instead of keeping their own copies.
"""
from dataclasses import dataclass

# Size-class keys used by mesh/settings.py's region_sizes table and geometry/build.py's _size_key.
REGION_SIZE_KEYS = frozenset({"stator_iron", "rotor_iron", "shaft", "coil", "slot_air", "airgap"})

# Material-role kinds used by StaticMesh.region_kind / MachineMesh.region_kind (spec §6's
# per-region material assignment: stator iron, rotor iron, shaft, coil, or air).
REGION_KINDS = frozenset({"stator_iron", "rotor_iron", "shaft", "coil", "air"})


@dataclass(frozen=True)
class CoilInfo:
    """One coil-side region's electrical identity, for the M2 connection matrix (spec §6)."""
    pole: int
    phase: str
    sign: int
