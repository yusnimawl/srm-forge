"""Digest of the srmcore source files that decide map numbers, and its pin.

Cached maps (and the stroke and field caches, which use the same provenance) are keyed by
`srmcore.maps.dataset.provenance`, which holds `ENGINE_REVISION`. The pin in `tests/maps/engine_digest_pin.json`
records the digest of the files below and the revision it was taken at; `tests/maps/test_engine_revision.py`
fails when either differs. After a change to these files: if the change can alter map numbers, bump
ENGINE_REVISION in `src/srmcore/maps/dataset.py`; then run

    python tools/engine_digest.py --update

Without `--update` the script prints the digest, lists the changed files and exits 1 when the pin is stale.
Line endings are normalised (CRLF to LF) and paths are POSIX and relative to the repository root, so the digest
is the same on Windows and Linux. Standard library only.
"""
import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "srmcore"
PIN = ROOT / "tests" / "maps" / "engine_digest_pin.json"
REVISION_FILE = SRC / "maps" / "dataset.py"
UPDATE_COMMAND = "python tools/engine_digest.py --update"

# Every .py file of these subpackages, and these single files. Material JSON data are left out: the provenance
# holds a digest of each material file a design uses.
INCLUDED_PACKAGES = ("model", "topology", "geometry", "mesh", "materials", "physics", "solvers", "fields")
INCLUDED_FILES = (
    "post/__init__.py", "post/quantities.py", "post/forces.py",
    "maps/api.py", "maps/dataset.py", "maps/identity.py", "maps/grids.py", "maps/point.py", "maps/run.py",
    "maps/pool.py", "maps/overlap.py", "maps/tables.py", "maps/stroke.py",
)
# Files a hashed file imports that cannot change map numbers, with the reason.
EXCLUDED = {
    "src/srmcore/__init__.py": "the package version only; the provenance holds the installed version",
    "src/srmcore/maps/__init__.py": "re-exports only",
    "src/srmcore/maps/checks.py": "checks on a finished map; overlap.py imports only its Check type",
    "src/srmcore/mesh/plot.py": "plots a mesh",
    "src/srmcore/materials/loss.py": "iron-loss model fit; magnetostatic solves never use it",
}


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def engine_files() -> list[str]:
    """POSIX paths, relative to the repository root, of the hashed files, sorted."""
    files = {_rel(p) for pkg in INCLUDED_PACKAGES for p in (SRC / pkg).rglob("*.py")}
    files |= {_rel(SRC / f) for f in INCLUDED_FILES}
    return sorted(files - set(EXCLUDED))


def _normalised(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def file_digests(root: Path = ROOT, files=None) -> dict[str, str]:
    files = engine_files() if files is None else files
    return {rel: hashlib.sha256(_normalised(Path(root) / rel)).hexdigest() for rel in sorted(files)}


def digest(root: Path = ROOT, files=None) -> str:
    """SHA-256 over the sorted (path, content) pairs; independent of line endings and of the order given."""
    h = hashlib.sha256()
    for rel, file_hash in file_digests(root, files).items():
        h.update(f"{rel}\n{file_hash}\n".encode())
    return h.hexdigest()


def engine_revision() -> int:
    """ENGINE_REVISION as written in its source file, read without importing srmcore."""
    for node in ast.parse(REVISION_FILE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ENGINE_REVISION"
                                                for t in node.targets):
            return int(ast.literal_eval(node.value))
    raise LookupError(f"ENGINE_REVISION not found in {_rel(REVISION_FILE)}")


def changed_files(pin: dict) -> list[str]:
    """Files added, removed or changed since the pin was taken."""
    now, then = file_digests(), pin.get("files", {})
    return sorted(f for f in set(now) | set(then) if now.get(f) != then.get(f))


def srmcore_imports(path: Path) -> set[str]:
    """Repository-relative paths of the srmcore modules `path` imports, with the package __init__ files that
    importing them runs."""
    package = list(path.resolve().relative_to(SRC.parent).parts[:-1])
    found: set[str] = set()

    def add(parts: list[str]) -> None:
        for k in range(1, len(parts) + 1):
            base = SRC.parent.joinpath(*parts[:k])
            if base.is_dir() and (base / "__init__.py").is_file():
                found.add(_rel(base / "__init__.py"))
            elif base.with_suffix(".py").is_file():
                found.add(_rel(base.with_suffix(".py")))

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules = [alias.name.split(".") for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
            else:
                base = []
            module = base + (node.module.split(".") if node.module else [])
            modules = [module + [alias.name] for alias in node.names]
        else:
            continue
        for parts in modules:
            if parts and parts[0] == SRC.name:
                add(parts)
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="write the pin from the current files")
    args = parser.parse_args(argv)
    revision, files = engine_revision(), file_digests()
    current = digest()
    if args.update:
        PIN.write_text(json.dumps({"engine_revision": revision, "digest": current, "files": files},
                                  indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"pinned {current} at ENGINE_REVISION {revision} ({len(files)} files) in {_rel(PIN)}")
        return 0
    pin = json.loads(PIN.read_text(encoding="utf-8")) if PIN.exists() else {}
    print(f"digest {current}, ENGINE_REVISION {revision}")
    if pin.get("digest") == current and pin.get("engine_revision") == revision:
        print("pin is current")
        return 0
    for rel in changed_files(pin):
        print(f"  changed: {rel}")
    print(f"pin is stale: if the change can alter map numbers, bump ENGINE_REVISION in {_rel(REVISION_FILE)}; "
          f"then run `{UPDATE_COMMAND}`")
    return 1


if __name__ == "__main__":
    sys.exit(main())
