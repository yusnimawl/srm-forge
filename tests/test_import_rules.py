"""Enforces the allowed-imports table of spec §3.2."""
import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "srmcore"

ALLOWED: dict[str, set[str]] = {
    "model": set(),
    "materials": {"model"},
    "fields": {"model"},
    "topology": {"model"},
    "geometry": {"model", "topology"},
    "mesh": {"model", "geometry"},
    "physics": {"model", "materials", "mesh"},
    "solvers": {"model", "materials", "physics", "fields"},
    "post": {"model", "materials", "physics", "fields"},
    "maps": {"model", "materials", "fields", "topology", "geometry",
             "mesh", "physics", "solvers", "post"},
    "project": {"model", "maps"},
}
THIRD_PARTY_OWNERS: dict[str, set[str]] = {
    "ngsolve": {"solvers"},
    "netgen": {"solvers"},
    "gmsh": {"geometry", "mesh"},
}


def _imported_modules(py_file: Path, src_root: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    package_parts = list(py_file.relative_to(src_root.parent).parts[:-1])
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.append(node.module or "")
            else:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                suffix = node.module.split(".") if node.module else []
                found.append(".".join(base + suffix))
    return found


def find_violations(src_root: Path) -> list[str]:
    violations: list[str] = []
    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(src_root).parts
        if len(rel) < 2:
            continue  # top-level srmcore/__init__.py is unconstrained
        owner = rel[0]
        for module in _imported_modules(py_file, src_root):
            parts = module.split(".")
            if parts[0] == src_root.name and len(parts) > 1:
                target = parts[1]
                if target != owner and target not in ALLOWED.get(owner, set()):
                    violations.append(f"{py_file.name} ({owner}) imports {module}")
            elif parts[0] in THIRD_PARTY_OWNERS and owner not in THIRD_PARTY_OWNERS[parts[0]]:
                violations.append(f"{py_file.name} ({owner}) imports {module}")
    return violations


def test_source_tree_obeys_import_rules():
    assert find_violations(SRC_ROOT) == []


def test_checker_detects_forbidden_internal_and_third_party(tmp_path):
    root = tmp_path / "srmcore"
    (root / "model").mkdir(parents=True)
    (root / "model" / "bad.py").write_text("from ..mesh import thing\n", encoding="utf-8")
    (root / "physics").mkdir()
    (root / "physics" / "bad.py").write_text("import gmsh\n", encoding="utf-8")
    (root / "mesh").mkdir()
    (root / "mesh" / "ok.py").write_text("from srmcore.geometry import x\nimport gmsh\n", encoding="utf-8")
    violations = find_violations(root)
    assert len(violations) == 2
    assert any("model" in v and "srmcore.mesh" in v for v in violations)
    assert any("physics" in v and "gmsh" in v for v in violations)
