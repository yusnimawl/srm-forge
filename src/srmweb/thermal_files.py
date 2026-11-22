"""Temperature fields of a rating, one npz per (job, evaluation) under `<cache_dir>/thermal/`."""
from pathlib import Path

from srmapp.thermal_fields import ThermalFields, write_fields

THERMAL_DIR = "thermal"


def fields_key(job_id: str, evaluation_id: str) -> str:
    return f"{job_id}_{evaluation_id}"


def path(cache_dir: Path, key: str) -> Path:
    return Path(cache_dir) / THERMAL_DIR / f"{key}.npz"


def write(cache_dir: Path, key: str, f: ThermalFields) -> None:
    path(cache_dir, key).parent.mkdir(parents=True, exist_ok=True)
    write_fields(path(cache_dir, key), f)
