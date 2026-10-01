import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_srmcore_never_imports_srmapp():
    for py in (SRC / "srmcore").rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            assert not any(n == "srmapp" or n.startswith("srmapp.") for n in names), py
