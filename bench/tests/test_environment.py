"""Checks on the bench environment definition and the bootstrap files."""

import re
import tomllib
from pathlib import Path

import srmbench

BENCH = Path(__file__).resolve().parents[1]
REPO = BENCH.parent


def _requirement_lines() -> list[str]:
    lines = (BENCH / "requirements.in").read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def test_requirements_in_covers_pyproject_dependencies():
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    wanted = pyproject["project"]["dependencies"]
    assert wanted
    present = set(_requirement_lines())
    missing = [dep for dep in wanted if dep not in present]
    assert not missing, f"requirements.in lacks pyproject dependencies: {missing}"


def test_requirements_in_has_ngsolve_and_bench_extras():
    lines = _requirement_lines()
    for name in ("ngsolve", "psutil", "py-cpuinfo", "pytest"):
        assert any(re.match(rf"{re.escape(name)}(?![\w-])", ln) for ln in lines), name


def test_paths():
    assert srmbench.BENCH_DIR.name == "bench"
    assert (srmbench.REPO_DIR / "pyproject.toml").exists()
    assert srmbench.RUNTIME_DIR == srmbench.BENCH_DIR / ".runtime"
    assert srmbench.BENCH_VERSION == "1.0"


def test_srmcore_is_the_checkout():
    import srmcore

    src = (srmbench.REPO_DIR / "src").resolve()
    assert src in Path(srmcore.__file__).resolve().parents


def test_scripts_line_endings():
    assert b"\r\n" not in (BENCH / "run.sh").read_bytes()
    attributes = (REPO / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "*.sh text eol=lf" in attributes
    assert "*.bat text eol=crlf" in attributes
