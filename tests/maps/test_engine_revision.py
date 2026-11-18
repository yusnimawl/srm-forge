"""ENGINE_REVISION in the map provenance, and the pinned digest of the engine code that decides map numbers."""
import ast
import json

import numpy as np
import pytest

import engine_digest
from conftest import make_8_6
from srmcore.maps import dataset, stroke
from srmcore.maps.run import STATUS_OK, MapResult
from srmcore.model.design import Design, MeshSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
ANGLES, CURRENTS = np.array([0.0, 0.01]), np.array([0.0, 5.0])


def _prov():
    return dataset.provenance(DESIGN, ANGLES, CURRENTS, "A", SkfemReference())


def _result():
    rng = np.random.default_rng(0)
    return MapResult(
        ANGLES, CURRENTS, ("A", "B", "C", "D"), "A", rng.random((2, 2, 4)), rng.random((2, 2)),
        rng.random((2, 2)), rng.random((2, 2)), rng.random((2, 2)), rng.random((2, 2, 4)),
        rng.random((2, 2, 8, 2)), rng.random((2, 2)), np.full((2, 2), 7, dtype=np.int32),
        np.full((2, 2), STATUS_OK, dtype=np.int8), np.zeros((2, 2), dtype=bool), True,
        design_hash="0123456789abcdef", preset="screening")


def test_provenance_holds_the_engine_revision():
    assert _prov()["engine_revision"] == dataset.ENGINE_REVISION
    assert isinstance(dataset.ENGINE_REVISION, int) and dataset.ENGINE_REVISION >= 1


def test_a_new_engine_revision_misses_a_stored_map(tmp_path, monkeypatch):
    prov = _prov()
    dataset.store_map(tmp_path, _result(), prov)
    assert dataset.cached_map(tmp_path, prov) is not None
    monkeypatch.setattr(dataset, "ENGINE_REVISION", dataset.ENGINE_REVISION + 1)
    bumped = _prov()
    assert dataset.provenance_hash(bumped) != dataset.provenance_hash(prov)
    assert dataset.cached_map(tmp_path, bumped) is None


def test_stroke_and_field_keys_follow_the_engine_revision(monkeypatch):
    field = pytest.importorskip("srmapp.field")
    keys = lambda: (stroke.stroke_key(DESIGN, ANGLES, np.ones((2, 4)), solver="skfem_reference"),
                    field.field_key(DESIGN, "skfem_reference"))
    before = keys()
    monkeypatch.setattr(dataset, "ENGINE_REVISION", dataset.ENGINE_REVISION + 1)
    after = keys()
    assert before[0] != after[0] and before[1] != after[1]


def test_engine_code_matches_the_pinned_digest():
    pin = json.loads(engine_digest.PIN.read_text(encoding="utf-8"))
    revision = engine_digest.engine_revision()
    assert revision == dataset.ENGINE_REVISION
    fix = (f"if the change can alter map numbers, bump ENGINE_REVISION in "
           f"{engine_digest.REVISION_FILE.relative_to(engine_digest.ROOT).as_posix()}; "
           f"then run `{engine_digest.UPDATE_COMMAND}` to update the pin")
    assert pin["engine_revision"] == revision, (
        f"ENGINE_REVISION is {revision} but the pin was taken at {pin['engine_revision']}: {fix}")
    changed = engine_digest.changed_files(pin)
    assert pin["digest"] == engine_digest.digest(), (
        f"the engine code that decides map numbers changed ({', '.join(changed) or 'file set'}): {fix}")


def test_every_srmcore_import_of_a_hashed_file_is_hashed_or_excluded():
    hashed = set(engine_digest.engine_files())
    known = hashed | set(engine_digest.EXCLUDED)
    missing = {}
    for rel in sorted(hashed):
        for target in engine_digest.srmcore_imports(engine_digest.ROOT / rel):
            if target not in known:
                missing.setdefault(target, []).append(rel)
    assert not missing, f"add these to engine_digest.INCLUDED or EXCLUDED (with a reason): {missing}"


def test_excluded_files_exist():
    assert all((engine_digest.ROOT / rel).is_file() for rel in engine_digest.EXCLUDED)


def test_digest_changes_with_content_but_not_line_endings(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_bytes(b"x = 1\ny = 2\n")
    (tmp_path / "b.py").write_bytes(b"z = 3\n")
    files = ["pkg/a.py", "b.py"]
    base = engine_digest.digest(tmp_path, files)
    assert base == engine_digest.digest(tmp_path, list(reversed(files)))
    (tmp_path / "pkg" / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    assert engine_digest.digest(tmp_path, files) == base
    (tmp_path / "pkg" / "a.py").write_bytes(b"x = 1\ny = 3\n")
    assert engine_digest.digest(tmp_path, files) != base


def test_digest_depends_on_the_file_names(tmp_path):
    for name in ("a.py", "c.py"):
        (tmp_path / name).write_bytes(b"x = 1\n")
    assert engine_digest.digest(tmp_path, ["a.py"]) != engine_digest.digest(tmp_path, ["c.py"])


def test_engine_revision_is_read_from_the_source():
    tree = ast.parse(engine_digest.REVISION_FILE.read_text(encoding="utf-8"))
    names = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    assert names.count("ENGINE_REVISION") == 1
