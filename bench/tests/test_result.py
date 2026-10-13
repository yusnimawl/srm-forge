import json

import pytest

from srmbench.result import Result, read_results, validate_label, write_result


def _result(label="lattepanda-sigma", tier="quick", started="2026-10-14T09:05:12+07:00") -> Result:
    return Result(
        schema="srmbench-result", bench_version="1.0", tier=tier, label=label, started=started,
        finished="2026-10-14T09:09:00+07:00", status="complete", machine={"cpu_model": "x"},
        versions={"srmcore": "0.4.0"}, lock_hash="abc", steps={"batches": []}, summary={"search_h": 1.5},
        warnings=["on battery"],
    )


def test_label_rules():
    assert validate_label("lattepanda-sigma") == "lattepanda-sigma"
    assert validate_label("x" * 40) == "x" * 40
    for bad in ("Laptop", "a b", "", "x" * 41, "a_b", "a\n", "é"):
        with pytest.raises(ValueError, match="a-z0-9"):
            validate_label(bad)


def test_write_read_round_trip(tmp_path):
    first = write_result(_result(), tmp_path)
    second = write_result(_result(started="2026-10-14T09:05:40+07:00"), tmp_path)
    third = write_result(_result(), tmp_path)
    assert first == tmp_path / "lattepanda-sigma" / "2026-10-14T0905-quick.json"
    assert second.name == "2026-10-14T0905-quick-2.json"
    assert third.name == "2026-10-14T0905-quick-3.json"
    got = read_results(tmp_path)
    assert len(got) == 3
    assert got[0] == _result()
    assert [r.started for r in got] == sorted(r.started for r in got)


def test_file_format(tmp_path):
    path = write_result(_result(), tmp_path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["schema"] == "srmbench-result" and data["status"] == "complete"
    assert text.startswith('{\n "')  # indent=1
    assert list(data) == sorted(data)  # sorted keys


def test_read_sorted_by_started_across_labels(tmp_path):
    write_result(_result(label="b", started="2026-10-15T08:00:00+07:00"), tmp_path)
    write_result(_result(label="a", started="2026-10-14T08:00:00+07:00"), tmp_path)
    assert [r.label for r in read_results(tmp_path)] == ["a", "b"]


def test_read_results_skips_foreign_and_broken(tmp_path):
    write_result(_result(), tmp_path)
    d = tmp_path / "other"
    d.mkdir()
    (d / "foreign.json").write_text(json.dumps({"schema": "something-else"}), encoding="utf-8")
    (d / "broken.json").write_text("{not json", encoding="utf-8")
    (d / "missing-fields.json").write_text(json.dumps({"schema": "srmbench-result"}), encoding="utf-8")
    (d / "list.json").write_text("[1, 2]", encoding="utf-8")
    (tmp_path / "top-level.json").write_text(json.dumps(_result().__dict__), encoding="utf-8")
    (tmp_path / "charts").mkdir()
    (tmp_path / "charts" / "x.svg").write_text("<svg/>", encoding="utf-8")
    assert len(read_results(tmp_path)) == 1


def test_read_results_missing_dir(tmp_path):
    assert read_results(tmp_path / "nope") == []
