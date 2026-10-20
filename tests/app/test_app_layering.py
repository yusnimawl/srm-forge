import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def _assert_no_import(package: str, forbidden: tuple[str, ...]):
    for py in (SRC / package).rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            assert not any(n == f or n.startswith(f + ".") for n in names for f in forbidden), py


def test_srmcore_never_imports_srmapp():
    _assert_no_import("srmcore", ("srmapp",))


def test_core_and_app_never_import_srmweb():
    for package in ("srmcore", "srmapp"):
        _assert_no_import(package, ("srmweb",))


def test_srmweb_imports_no_solver_or_mesher():
    _assert_no_import("srmweb", ("gmsh", "ngsolve", "netgen", "skfem"))


def test_srmsil_layering():
    _assert_no_import("srmsil", ("srmweb", "gmsh", "ngsolve", "netgen", "skfem"))
    for package in ("srmcore", "srmapp"):
        _assert_no_import(package, ("srmsil",))
