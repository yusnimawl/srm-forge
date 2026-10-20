"""What identifies the design a map was solved for: the design JSON, its resolved mesh settings and the bytes of
its material files. The map provenance adds the grids, excitation, solver and versions on top."""
import dataclasses
import hashlib
import json

from ..materials import library
from ..mesh.settings import resolve_mesh_settings
from ..model.design import Design


def material_digest(raw: bytes) -> str:
    """Digest of a material record's content; line endings and key order do not matter. The `loss` block is
    left out: iron-loss data cannot change a magnetostatic map, so editing it never changes a design hash or a
    cache key, and a material without a loss block hashes as it always did."""
    record = json.loads(raw)
    if isinstance(record, dict):
        record.pop("loss", None)
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def design_parts(design: Design) -> dict:
    mesh_resolved = json.loads(json.dumps(dataclasses.asdict(resolve_mesh_settings(design.machine, design.mesh))))
    names = sorted(set(design.machine.materials.model_dump().values()))
    materials = {n: material_digest((library._data_dir() / f"{n}.json").read_bytes()) for n in names}
    return {"design": json.loads(design.to_json()), "mesh_resolved": mesh_resolved, "materials": materials}


def design_hash(design: Design) -> str:
    return hashlib.sha256(json.dumps(design_parts(design), sort_keys=True).encode()).hexdigest()[:16]
