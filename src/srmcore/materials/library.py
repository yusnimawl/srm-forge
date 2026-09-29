"""The built-in material library: one JSON file per material variant in materials/data/."""
from importlib import resources

from pydantic import TypeAdapter

from .schema import ConductorMaterial, Material, SoftMagneticMaterial

_ADAPTER: TypeAdapter[Material] = TypeAdapter(Material)


def _data_dir():
    return resources.files(__package__) / "data"


def available_materials() -> tuple[str, ...]:
    return tuple(sorted(p.name[:-5] for p in _data_dir().iterdir() if p.name.endswith(".json")))


def load_material(name: str) -> SoftMagneticMaterial | ConductorMaterial:
    path = _data_dir() / f"{name}.json"
    if not path.is_file():
        raise KeyError(f"unknown material {name!r}; available: {', '.join(available_materials())}")
    material = _ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    if material.name != name:
        raise ValueError(f"{name}.json declares name {material.name!r}")
    return material
