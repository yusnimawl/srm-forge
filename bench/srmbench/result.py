"""Result model and its JSON files: `results/<label>/<YYYY-MM-DD>T<HHMM>-<tier>.json`."""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = "srmbench-result"
LABEL_RULE = "a label is 1 to 40 characters from a-z0-9 and '-'"
_LABEL = re.compile(r"[a-z0-9-]{1,40}")


@dataclass
class Result:
    schema: str
    bench_version: str
    tier: str
    label: str
    started: str
    finished: str
    status: str
    machine: dict
    versions: dict
    lock_hash: str
    steps: dict
    summary: dict
    warnings: list[str]


def now_iso() -> str:
    """Local time with its UTC offset, to the second."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def validate_label(s: str) -> str:
    if not _LABEL.fullmatch(s):
        raise ValueError(f"Invalid label {s!r}: {LABEL_RULE}.")
    return s


def write_result(r: Result, results_dir: Path) -> Path:
    """Write the result under its label; an existing file name gets -2, -3, ... appended."""
    validate_label(r.label)
    stamp = datetime.fromisoformat(r.started).strftime("%Y-%m-%dT%H%M")
    folder = Path(results_dir) / r.label
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dataclasses.asdict(r), sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    n = 1
    while True:
        path = folder / (f"{stamp}-{r.tier}.json" if n == 1 else f"{stamp}-{r.tier}-{n}.json")
        try:
            with open(path, "x", encoding="utf-8", newline="\n") as f:
                f.write(text)
            return path
        except FileExistsError:
            n += 1


def _load(path: Path) -> Result | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            return None
        return Result(**{f.name: data[f.name] for f in dataclasses.fields(Result)})
    except (OSError, ValueError, KeyError):
        return None


def read_results(results_dir: Path) -> list[Result]:
    """Every result file one level down, oldest first; foreign or broken files are skipped."""
    found = []
    for path in sorted(Path(results_dir).glob("*/*.json")):
        r = _load(path)
        if r is not None:
            found.append(r)
    return sorted(found, key=lambda r: _start_key(r.started))


def _start_key(started: str):
    try:
        return datetime.fromisoformat(started).timestamp()
    except ValueError:
        return float("inf")
