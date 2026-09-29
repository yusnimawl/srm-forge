"""Build a Magnetostatic2D from a machine mesh. Materials, coils and the boundary come from the mesh's
region_kind, coils (CoilInfo) and outer_edges, never from parsing region names."""
from collections.abc import Mapping

import numpy as np

from ..materials.laws import VACUUM, ReluctivityLaw, library_law
from ..mesh.machine import MachineMesh
from ..model.design import Design
from .problem import BandInfo, Magnetostatic2D
from .winding import Winding, phase_winding

# region_kind -> the RegionMaterials field naming that region's material; "air" is always vacuum.
KIND_ROLE = {"stator_iron": "stator", "rotor_iron": "rotor", "shaft": "shaft", "coil": "coil"}


def machine_problem(mesh: MachineMesh, design: Design, currents: Mapping[str, float] | None = None,
                    winding: Winding | None = None) -> Magnetostatic2D:
    p = design.machine
    winding = winding if winding is not None else phase_winding(mesh, p.turns_per_pole)
    laws: list[ReluctivityLaw] = [VACUUM]
    law_of_region = np.zeros(len(mesh.region_names), dtype=np.int64)
    for rid, name in enumerate(mesh.region_names):
        kind = mesh.region_kind[name]
        if kind == "air":
            continue
        if kind not in KIND_ROLE:
            raise ValueError(f"region {name!r} has unknown kind {kind!r}")
        law = library_law(getattr(p.materials, KIND_ROLE[kind]))
        if law not in laws:
            laws.append(law)
        law_of_region[rid] = laws.index(law)
    coil_index = np.full(len(mesh.region_names), -1, dtype=np.int64)
    for s, name in enumerate(winding.coil_sides):
        coil_index[mesh.region_names.index(name)] = s
    i = np.zeros(len(winding.circuits))
    for circuit, value in (currents or {}).items():
        if circuit not in winding.circuits:
            raise ValueError(f"unknown circuit {circuit!r}; circuits are {winding.circuits}")
        i[winding.circuits.index(circuit)] = value
    band = BandInfo(np.arange(mesh.band_rows.start, mesh.band_rows.stop), mesh.band_inner_radius,
                    mesh.band_outer_radius)
    return Magnetostatic2D(
        nodes=mesh.nodes, triangles=mesh.triangles,
        element_law=law_of_region[mesh.region_ids], laws=tuple(laws),
        element_region=mesh.region_ids.astype(np.int64), region_names=mesh.region_names,
        region_kind=dict(mesh.region_kind), element_coil=coil_index[mesh.region_ids],
        winding=winding, currents=i,
        # outer_edges is the mesh's outermost boundary; a future stator_outer_air ring moves it
        # outward in the mesh layer and this code does not change.
        dirichlet_nodes=np.unique(mesh.outer_edges), depth=p.stack_length, band=band,
    )
