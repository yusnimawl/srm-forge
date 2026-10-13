"""Machine benchmark for the SRM design tool: runs the real srmcore workload and records timings."""

from pathlib import Path

BENCH_VERSION: str = "1.0"
BENCH_DIR: Path = Path(__file__).resolve().parents[1]
RUNTIME_DIR: Path = BENCH_DIR / ".runtime"
REPO_DIR: Path = BENCH_DIR.parent

__all__ = ["BENCH_VERSION", "BENCH_DIR", "RUNTIME_DIR", "REPO_DIR"]
