import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    db: Path
    cache_dir: Path
    workers: int | None
    token: str | None
    queue_max: int
    static_dir: Path


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    workers = env.get("SRMWEB_WORKERS")
    return Settings(
        host=env.get("SRMWEB_HOST", "127.0.0.1"),
        port=int(env.get("SRMWEB_PORT", "8000")),
        db=Path(env.get("SRMWEB_DB", "srmweb.db")),
        cache_dir=Path(env.get("SRMWEB_CACHE_DIR", "cache")),
        workers=int(workers) if workers else None,
        token=env.get("SRMWEB_TOKEN") or None,
        queue_max=int(env.get("SRMWEB_QUEUE_MAX", "10")),
        static_dir=Path(env["SRMWEB_STATIC"]) if env.get("SRMWEB_STATIC")
        else Path(__file__).resolve().parents[2] / "web" / "dist",
    )


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_exposure(s: Settings) -> None:
    if not is_loopback(s.host) and not s.token:
        raise SystemExit(
            f"SRMWEB_HOST={s.host} is not loopback; set SRMWEB_TOKEN to expose the server")
