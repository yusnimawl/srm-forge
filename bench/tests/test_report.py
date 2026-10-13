import colorsys
import copy
import json
import re
import shutil
from pathlib import Path

import pytest

from srmbench import report
from srmbench.result import read_results

FIXTURES = Path(__file__).parent / "fixtures"
REF = "i7-13620h-laptop"
PROSE_BEFORE = "# Title\n\nHand-written text.\n\n"
PROSE_AFTER = "\n\n## After\n\nMore text.\n"


@pytest.fixture
def env(tmp_path):
    results = tmp_path / "results"
    shutil.copytree(FIXTURES, results)
    readme = tmp_path / "README.md"
    readme.write_text(f"{PROSE_BEFORE}{report.START}\nold block\n{report.END}{PROSE_AFTER}", encoding="utf-8")
    return results, readme


def build(env, ref=REF):
    results, readme = env
    report.build_report(results, readme, ref)
    return readme.read_text(encoding="utf-8")


def table_rows(text: str) -> list[list[str]]:
    lines = [ln for ln in text.splitlines() if ln.startswith("| ")]
    head = next(i for i, ln in enumerate(lines) if ln.startswith("| Machine |"))
    rows = []
    for ln in lines[head + 1:]:
        if not ln.startswith("| ") or ln.startswith("| Preset") or ln.startswith("| Workers"):
            break
        rows.append([c.strip() for c in ln.strip("|").split(" | ")])
    return rows


def section_before(text: str, heading: str) -> str:
    return text.split(heading)[0]


def test_block_has_table_rows_for_current_version_only(env):
    text = build(env)
    rows = table_rows(text)
    labels = [re.match(r"\[(.*?)\]", r[0]).group(1) for r in rows]
    assert sorted(labels) == ["cloud-vm", "i7-13620h-laptop", "lattepanda"]
    assert "old-box" not in section_before(text, "### Older benchmark versions")
    older = text.split("### Older benchmark versions")[1]
    assert "old-box" in older and "2026-09-30T1000-quick.json" in older
    assert "lattepanda" not in older


def test_rows_ordered_by_full_map_ascending(env):
    rows = report.latest_per_machine(read_results(env[0]))
    times = [r.summary["full_map_s"]["value"] for r in rows]
    assert times == sorted(times)
    assert [r.label for r in rows] == ["i7-13620h-laptop", "cloud-vm", "lattepanda"]
    assert all(r.bench_version == "1.0" for r in rows)


def test_latest_per_machine_takes_the_newest_run_of_a_label(env):
    results = read_results(env[0])
    newer = copy.deepcopy(next(r for r in results if r.label == "lattepanda"))
    newer.started = "2026-10-14T12:00:00+07:00"
    newer.summary["full_map_s"] = {"value": 60.0, "measured": True}
    rows = report.latest_per_machine(results + [newer])
    assert [r.label for r in rows].count("lattepanda") == 1
    assert next(r for r in rows if r.label == "lattepanda").summary["full_map_s"]["value"] == 60.0


def test_projected_values_marked(env):
    rows = {re.match(r"\[(.*?)\]", r[0]).group(1): r for r in table_rows(build(env))}
    head = ["Machine", "CPU", "Cores", "RAM (GB)", "OS", "Tier", "Single solve (s)", "Workers", "Screening map (min)",
            "Full map (min)", "Search of 24 (h)", "RAM per worker (GB)", "Throttle (%)", "Correct", "Index single/all"]
    col = head.index
    cloud, laptop = rows["cloud-vm"], rows["i7-13620h-laptop"]
    assert cloud[col("Full map (min)")].startswith("~") and cloud[col("Screening map (min)")].startswith("~")
    assert laptop[col("Full map (min)")].startswith("~")
    assert not laptop[col("Screening map (min)")].startswith("~")
    assert laptop[col("Search of 24 (h)")].startswith("~")
    assert cloud[col("Throttle (%)")] == "–" and laptop[col("Throttle (%)")].startswith("-")
    assert laptop[col("Correct")] == "✓"
    assert laptop[col("RAM per worker (GB)")] == "0.86"


def test_reference_index(env):
    results = read_results(env[0])
    by = {r.label: r for r in results if r.bench_version == "1.0"}
    ref, lp = by[REF].summary, by["lattepanda"].summary
    want = f"{round(ref['single_solve_s'] / lp['single_solve_s'] * 100)}/" \
           f"{round(lp['throughput_per_min'] / ref['throughput_per_min'] * 100)}"
    rows = {re.match(r"\[(.*?)\]", r[0]).group(1): r for r in table_rows(build(env))}
    assert rows[REF][-1] == "100/100"
    assert rows["lattepanda"][-1] == want == "32/15"
    assert (env[0] / "charts" / "index.svg").is_file()


def test_no_reference_result_leaves_index_empty(env):
    text = build(env, "missing")
    assert all(r[-1] == "" for r in table_rows(text))
    assert not (env[0] / "charts" / "index.svg").exists()
    assert "index.svg" not in text
    assert (env[0] / "charts" / "full_map.svg").is_file()


def test_stale_index_chart_is_removed_when_the_reference_goes_away(env):
    build(env)
    assert (env[0] / "charts" / "index.svg").is_file()
    build(env, "missing")
    assert not (env[0] / "charts" / "index.svg").exists()


def test_build_report_replaces_only_block_and_is_idempotent(env):
    first = build(env)
    assert first.startswith(PROSE_BEFORE + report.START + "\n") and first.endswith(report.END + PROSE_AFTER)
    assert "old block" not in first
    svgs = {p.name: p.read_bytes() for p in (env[0] / "charts").glob("*.svg")}
    assert set(svgs) == {"full_map.svg", "scaling.svg", "index.svg"}
    second = build(env)
    assert second == first
    assert {p.name: p.read_bytes() for p in (env[0] / "charts").glob("*.svg")} == svgs


def test_crlf_readme_keeps_its_line_endings(env):
    results, readme = env
    readme.write_bytes(f"a\r\n{report.START}\r\nx\r\n{report.END}\r\nb\r\n".encode())
    report.build_report(results, readme, REF)
    data = readme.read_bytes()
    assert b"\r\n" in data and re.search(rb"(?<!\r)\n", data) is None
    before = data
    report.build_report(results, readme, REF)
    assert readme.read_bytes() == before


def test_missing_markers_raise(env):
    results, readme = env
    for bad in ("no markers", f"{report.START}\nonly start", f"{report.END}\n{report.START}"):
        readme.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            report.build_report(results, readme, REF)
        assert readme.read_text(encoding="utf-8") == bad


def test_empty_results_dir(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    readme = tmp_path / "README.md"
    readme.write_text(f"{report.START}\n{report.END}\n", encoding="utf-8")
    report.build_report(results, readme, REF)
    assert "No results yet" in readme.read_text(encoding="utf-8")
    assert not (results / "charts").exists()


def colours(svg: str) -> list[str]:
    found = re.findall(r"#[0-9a-fA-F]{6}\b", svg)
    for rgb in re.findall(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", svg):
        found.append("#%02x%02x%02x" % tuple(int(v) for v in rgb))
    return found


def test_charts_have_no_blue(env):
    build(env)
    for name in ("full_map", "scaling", "index"):
        svg = (env[0] / "charts" / f"{name}.svg").read_text(encoding="utf-8")
        found = colours(svg)
        assert found, name
        for c in found:
            r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
            h, _, s = colorsys.rgb_to_hls(r, g, b)
            assert not (190 <= h * 360 <= 250 and s > 0.15), (name, c)
        assert "#ededed" not in svg.lower()


def test_charts_are_transparent_and_dated_nowhere(env):
    build(env)
    for name in ("full_map", "scaling", "index"):
        svg = (env[0] / "charts" / f"{name}.svg").read_text(encoding="utf-8")
        assert "<dc:date>" not in svg
        assert "#ffffff" not in svg.lower()


def test_scaling_skips_machines_with_fewer_than_two_batches(env):
    results = read_results(env[0])
    one = copy.deepcopy(next(r for r in results if r.label == "cloud-vm"))
    one.steps["batches"] = one.steps["batches"][:1]
    rows = [r for r in report.latest_per_machine(results) if r.label != "cloud-vm"] + [one]
    svg = report.scaling_chart(rows, REF).decode()
    assert "cloud-vm" not in svg  # text is drawn as paths, so labels are glyph ids; check the line count instead
    full = report.scaling_chart(report.latest_per_machine(results), REF).decode()
    assert svg.count("stroke-dasharray") < full.count("stroke-dasharray")
    assert report.scaling_chart([one], REF) is None


def test_scaling_without_any_line_has_no_chart_or_image(env):
    results = read_results(env[0])
    for r in results:
        r.steps["batches"] = r.steps["batches"][:1]
    block = report.render_block(results, REF, "results/charts")
    assert "scaling.svg" not in block and "full_map.svg" in block


def test_details_links_are_relative(env):
    text = build(env)
    links = re.findall(r"\]\((results/[^)]+\.json)\)", text)
    assert links
    for ln in links:
        assert re.fullmatch(r"results/[a-z0-9-]+/\d{4}-\d\d-\d\dT\d{4}-(quick|standard|long)(-\d+)?\.json", ln), ln
        assert (env[1].parent / ln).is_file()
    assert "(results/charts/full_map.svg)" in text
    assert text.count("<details") == 3 == text.count("</details>")
    assert str(env[0]) not in text and "\\" not in "".join(links)


def test_details_content_and_earlier_runs(env):
    results = read_results(env[0])
    earlier = copy.deepcopy(next(r for r in results if r.label == "lattepanda"))
    earlier.started = earlier.finished = "2026-10-01T08:00:00+07:00"
    earlier.tier = "quick"
    text = report.render_block(results + [earlier], REF, "results/charts")
    lp = text.split('<details id="machine-lattepanda">')[1].split("</details>")[0]
    assert "All runs of this machine" in lp
    assert "2026-10-01T0800-quick.json" in lp and "2026-10-13T2030-standard.json" in lp
    for needle in ("Intel(R) N100", "srmcore 0.4.0", "**Mesh (8/6)**", "**Batches**", "**Scaling**", "Sustained load",
                   "trace (time: solves per minute)", "Recommended workers", "Single solve (8/6)"):
        assert needle in lp, needle
    cloud = text.split('<details id="machine-cloud-vm">')[1].split("</details>")[0]
    assert "Sustained load" not in cloud and "All runs of this machine" not in cloud


def test_pipes_in_machine_text_do_not_break_the_table(env):
    results = read_results(env[0])
    for r in results:
        if r.label == "lattepanda":
            r.machine["cpu_model"] = "Odd | <b>CPU</b>"
    rows = table_rows(report.render_block(results, REF, "results/charts"))
    assert all(len(r) == 15 for r in rows)


def test_fixture_files_are_valid_json_with_the_real_layout():
    for p in FIXTURES.glob("*/*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["schema"] == "srmbench-result" and p.parent.name == d["label"]
        assert {"mesh", "single_solve", "correctness_points", "batches", "recommended"} <= set(d["steps"])
