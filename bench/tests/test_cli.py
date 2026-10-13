import pytest

import srmbench.__main__ as cli
from srmbench import preflight, publish, report, tiers
from srmbench.preflight import Platform, Problem
from srmbench.result import Result

PLAT = Platform("Windows", "AMD64", "", None, 22631, 16.0, 9.0, 100.0, 8)
SUMMARY = {
    "single_solve_s": 2.1, "single_solve_full_s": 9.5, "best_workers": 8, "recommended_workers": 8,
    "throughput_per_min": 120.0, "peak_ram_worker_gb": 0.9, "throttle_pct": None,
    "screening_map_s": {"value": 300.0, "measured": False}, "full_map_s": {"value": 2400.0, "measured": False},
    "search_h": 1.5, "correctness": {"status": "pass", "details": []}, "srmweb_workers": 8,
    "projection_error_pct": None,
}


def _result(label, tier, warnings=()):
    return Result(
        schema="srmbench-result", bench_version="1.0", tier=tier, label=label, started="2026-10-14T09:05:12+07:00",
        finished="2026-10-14T09:09:00+07:00", status="complete", machine={"cpu_model": "x"}, versions={},
        lock_hash="abc", steps={}, summary=SUMMARY, warnings=list(warnings),
    )


class Env:
    """Fakes for everything the CLI calls outside itself; records the calls."""

    def __init__(self, tmp_path, monkeypatch):
        self.runtime = tmp_path / "runtime"
        self.results = tmp_path / "results"
        self.readme = tmp_path / "README.md"
        self.readme.write_text("x", encoding="utf-8")
        self.reference = tmp_path / "reference-machine.txt"
        self.reference.write_text("ref-box\nignored\n", encoding="utf-8")
        for name, value in (("RUNTIME_DIR", self.runtime), ("RESULTS_DIR", self.results), ("README", self.readme),
                            ("REFERENCE_FILE", self.reference), ("REPO_DIR", tmp_path)):
            monkeypatch.setattr(cli, name, value)
        self.run_calls: list[tuple] = []
        self.report_calls: list[tuple] = []
        self.publish_calls: list[tuple] = []
        self.git = (True, "")
        self.run_error: BaseException | None = None
        self.load_problems: list[Problem] = []
        self.platform_problems: list[Problem] = []
        self.publish_result = (True, "pushed")
        monkeypatch.setattr(preflight, "current_platform", lambda runtime: PLAT)
        monkeypatch.setattr(preflight, "check_platform", lambda p, tier: list(self.platform_problems))
        monkeypatch.setattr(preflight, "check_imports", lambda: [])
        monkeypatch.setattr(preflight, "check_load", lambda *a, **k: list(self.load_problems))
        monkeypatch.setattr(tiers, "run_tier", self._run_tier)
        monkeypatch.setattr(report, "build_report", lambda *a: self.report_calls.append(a))
        monkeypatch.setattr(publish, "git_ready", lambda repo: self.git)
        monkeypatch.setattr(publish, "publish", self._publish)

    def _run_tier(self, tier, label, platform, worker_cap, log):
        self.run_calls.append((tier, label, platform, worker_cap))
        log("a progress line")
        if self.run_error is not None:
            raise self.run_error
        return _result(label, tier)

    def _publish(self, repo, message, rebuild, run=None):
        self.publish_calls.append((repo, message))
        rebuild()
        return self.publish_result

    @property
    def finish(self):
        path = self.runtime / "finish"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def _sparse(path, size):
    """A file of `size` bytes without writing them."""
    with open(path, "wb") as f:
        f.truncate(size)


def _answers(*values):
    it = iter(values)
    asked = []

    def input_fn(prompt=""):
        asked.append(prompt)
        return next(it)

    input_fn.asked = asked
    return input_fn


def test_cli_yes_defaults(env, capsys):
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes"], input_fn=_answers()) == 0
    files = list((env.results / "t1").glob("*-quick.json"))
    assert len(files) == 1
    assert env.finish == "keep"
    assert env.publish_calls == []
    assert env.run_calls[0][:2] == ("quick", "t1") and env.run_calls[0][3] is None
    assert len(env.report_calls) == 1
    assert env.report_calls[0] == (env.results, env.readme, "ref-box")
    out = capsys.readouterr().out
    assert "a progress line" in out and "recommended" in out.lower()


def test_cli_workers_cap_is_passed(env):
    cli.main(["--tier", "quick", "--label", "t1", "--yes", "--workers", "3"], input_fn=_answers())
    assert env.run_calls[0][3] == 3


def test_cli_rejects_bad_label(env, capsys):
    assert cli.main(["--label", "Bad Label", "--yes", "--tier", "quick"], input_fn=_answers()) == 2
    assert "a-z0-9" in capsys.readouterr().out
    assert env.run_calls == [] and env.finish is None


def test_cli_unsupported_platform_returns_2(env, capsys):
    env.platform_problems = [Problem(True, "This machine is not supported: Windows on ARM64.")]
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes"], input_fn=_answers()) == 2
    assert "not supported" in capsys.readouterr().out
    assert env.run_calls == []


def test_cli_fatal_import_problem_returns_2(env, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "check_imports", lambda: [Problem(True, "Cannot import gmsh: OSError: libGLU")])
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes"], input_fn=_answers()) == 2
    assert "Cannot import gmsh" in capsys.readouterr().out and env.run_calls == []


def test_cli_ctrl_c(env, capsys):
    env.run_error = KeyboardInterrupt()
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes"], input_fn=_answers()) == 130
    assert not env.results.exists() or not list(env.results.rglob("*.json"))
    assert env.finish == "keep"
    assert env.publish_calls == [] and env.report_calls == []
    assert "Cancelled; nothing saved." in capsys.readouterr().out


def test_cli_ctrl_c_still_asks_the_finish_prompts(env):
    env.run_error = KeyboardInterrupt()
    ask = _answers("y")
    assert cli.main(["--tier", "quick", "--label", "t1"], input_fn=ask) == 130
    assert env.finish == "delete" and env.publish_calls == []
    assert len(ask.asked) == 1 and "Delete the benchmark environment" in ask.asked[0]


def test_cli_run_error_prints_and_returns_1(env, capsys):
    env.run_error = RuntimeError("mesh blew up")
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes"], input_fn=_answers()) == 1
    assert "mesh blew up" in capsys.readouterr().out
    assert env.finish is None


def test_cli_finish_choices_delete(env):
    ask = _answers("n", "y")  # push n, delete y
    assert cli.main(["--tier", "quick", "--label", "t1"], input_fn=ask) == 0
    assert env.finish == "delete" and env.publish_calls == []
    assert ask.asked[0].startswith("Commit and push results? [y/N]")
    assert ask.asked[1].startswith("Delete the benchmark environment (about ")
    assert ask.asked[1].endswith("GB)? You need to reinstall to run it again. [y/N] ")


def test_cli_finish_choices_keep_full(env):
    ask = _answers("n", "n", "y")  # push n, delete n, install y
    assert cli.main(["--tier", "quick", "--label", "t1"], input_fn=ask) == 0
    assert env.finish == "keep-full"
    assert "srmweb" in ask.asked[2]


def test_cli_finish_choices_keep(env):
    ask = _answers("n", "", "")
    assert cli.main(["--tier", "quick", "--label", "t1"], input_fn=ask) == 0
    assert env.finish == "keep"


def test_cli_push_yes_publishes_with_message(env):
    ask = _answers("y", "n", "n")
    assert cli.main(["--tier", "quick", "--label", "t1"], input_fn=ask) == 0
    assert env.publish_calls == [(env.runtime.parent, "bench: t1 quick 2026-10-14")]
    assert len(env.report_calls) == 2  # once locally, once inside publish


def test_cli_push_flag_skips_the_prompt(env):
    ask = _answers("n", "n")
    assert cli.main(["--tier", "quick", "--label", "t1", "--push"], input_fn=ask) == 0
    assert len(env.publish_calls) == 1
    assert all("push" not in p for p in ask.asked)


def test_cli_publish_failure_is_not_fatal(env, capsys):
    env.publish_result = (False, "git push failed: rejected")
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes", "--push"], input_fn=_answers()) == 0
    assert "rejected" in capsys.readouterr().out
    assert list((env.results / "t1").glob("*.json"))


def test_cli_push_skipped_without_git(env, capsys):
    env.git = (False, "git not found on PATH")
    ask = _answers("n", "n")  # delete n, install n
    assert cli.main(["--tier", "quick", "--label", "t1"], input_fn=ask) == 0
    assert env.publish_calls == []
    assert "git not found on PATH" in capsys.readouterr().out
    assert not any("push" in p for p in ask.asked) and len(ask.asked) == 2


def test_cli_no_push_flag(env):
    ask = _answers("n", "n")
    assert cli.main(["--tier", "quick", "--label", "t1", "--no-push"], input_fn=ask) == 0
    assert env.publish_calls == []


@pytest.mark.parametrize("flag,expected", [("--keep", "keep"), ("--delete", "delete"), ("--keep-full", "keep-full")])
def test_cli_finish_flags(env, flag, expected):
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes", flag], input_fn=_answers()) == 0
    assert env.finish == expected


def test_cli_finish_flags_are_exclusive(env):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--keep", "--delete"], input_fn=_answers())
    assert exc.value.code == 2


def test_cli_warnings_are_asked_and_recorded(env):
    env.load_problems = [Problem(False, "The machine is running on battery.")]
    ask = _answers("y")
    assert cli.main(["--tier", "quick", "--label", "t1", "--no-push", "--keep"], input_fn=ask) == 0
    assert "Continue anyway? [y/N]" in ask.asked[0]
    import json

    data = json.loads(next((env.results / "t1").glob("*.json")).read_text(encoding="utf-8"))
    assert data["warnings"] == ["The machine is running on battery."]


def test_cli_warnings_declined(env):
    env.load_problems = [Problem(False, "The machine is running on battery.")]
    assert cli.main(["--tier", "quick", "--label", "t1"], input_fn=_answers("n")) == 0
    assert env.run_calls == [] and env.finish is None


def test_cli_yes_accepts_warnings(env):
    env.load_problems = [Problem(False, "busy")]
    assert cli.main(["--tier", "quick", "--label", "t1", "--yes"], input_fn=_answers()) == 0
    assert env.run_calls


def test_cli_label_is_asked_and_remembered(env):
    ask = _answers("my-box")
    assert cli.main(["--tier", "quick", "--no-push", "--keep"], input_fn=ask) == 0
    assert env.run_calls[0][1] == "my-box"
    assert (env.runtime / "label").read_text(encoding="utf-8").strip() == "my-box"
    ask2 = _answers()
    assert cli.main(["--tier", "quick", "--no-push", "--keep"], input_fn=ask2) == 0
    assert env.run_calls[1][1] == "my-box" and ask2.asked == []


def test_cli_label_prompt_default_and_retry(env, monkeypatch):
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "My_Host.Local")
    ask = _answers("Not Valid", "")
    assert cli.main(["--tier", "quick", "--no-push", "--keep"], input_fn=ask) == 0
    assert env.run_calls[0][1] == "my-host-local"


def test_default_label():
    assert cli.default_label("DESKTOP-ABC_1") == "desktop-abc-1"
    assert len(cli.default_label("x" * 80)) == 40
    assert cli.default_label("") == "machine"


def test_cli_tier_menu(env, capsys):
    ask = _answers("2")
    assert cli.main(["--label", "t1", "--no-push", "--keep"], input_fn=ask) == 0
    assert env.run_calls[0][0] == "standard"
    out = capsys.readouterr().out
    assert "1) quick about 3 min" in out and "3) long about 2.2 h" in out
    assert "slower machines take longer" in out


def test_cli_tier_required_with_yes(env, capsys):
    assert cli.main(["--label", "t1", "--yes"], input_fn=_answers()) == 2
    assert "--tier" in capsys.readouterr().out


def test_cli_delete_prompt_shows_runtime_size(env):
    env.runtime.mkdir()
    _sparse(env.runtime / "blob", 150_000_000)
    ask = _answers("n", "n", "n")
    cli.main(["--tier", "quick", "--label", "t1"], input_fn=ask)
    assert "(about 0.1 GB)" in ask.asked[1]


def test_runtime_size_gb(tmp_path):
    (tmp_path / "a").mkdir()
    _sparse(tmp_path / "a" / "f", 700_000_000)
    (tmp_path / "g").write_bytes(b"\0" * 10)
    assert cli.runtime_size_gb(tmp_path) == pytest.approx(0.7, abs=0.01)
    assert cli.runtime_size_gb(tmp_path / "missing") == 0.0


def test_cli_report_only(env):
    assert cli.main(["--report-only"], input_fn=_answers()) == 0
    assert env.report_calls == [(env.results, env.readme, "ref-box")]
    assert env.run_calls == [] and env.finish is None


def test_cli_report_only_without_reference_file(env):
    env.reference.unlink()
    cli.main(["--report-only"], input_fn=_answers())
    assert env.report_calls[0][2] is None


def test_cli_self_test_writes_no_flag(env, monkeypatch):
    monkeypatch.setattr(cli, "run_self_test", lambda: 7)
    assert cli.main(["--self-test"], input_fn=_answers()) == 7
    assert env.finish is None


def test_cli_progress_lines_carry_time_and_elapsed(env, capsys):
    cli.main(["--tier", "quick", "--label", "t1", "--yes"], input_fn=_answers())
    line = next(x for x in capsys.readouterr().out.splitlines() if "a progress line" in x)
    assert line.startswith("[") and "+" in line.split("]")[0]
