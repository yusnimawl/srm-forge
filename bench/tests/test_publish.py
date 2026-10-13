import os
import shutil
import subprocess

import pytest

from srmbench import publish


def _done(argv, code=0, out="", err=""):
    return subprocess.CompletedProcess(argv, code, out, err)


class FakeGit:
    """Records every call. `replies` maps an argument prefix such as "rev-list --count" to
    (returncode, stdout, stderr), or to a list of those used in order (the last one repeats)."""

    def __init__(self, replies=None):
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []
        self.replies = {
            "rev-parse --abbrev-ref": (0, "origin/main\n", ""),
            "rev-list --count": (0, "0\n", ""),
            "rev-parse --is-inside-work-tree": (0, "true\n", ""),
        }
        self.replies.update(replies or {})
        self.used: dict[str, int] = {}

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        self.kwargs.append(kw)
        text = " ".join(argv[1:])
        keys = [k for k in self.replies if text.startswith(k)]
        if not keys:
            return _done(argv)
        key = max(keys, key=len)
        reply = self.replies[key]
        if isinstance(reply, list):
            i = self.used.get(key, 0)
            self.used[key] = i + 1
            reply = reply[min(i, len(reply) - 1)]
        return _done(argv, *reply)

    def subcommands(self) -> list[str]:
        return [c[1] for c in self.calls]


def _publish_sequence(tmp_path):
    """The calls of a successful publish: one commit ahead after committing."""
    fake = FakeGit({"rev-list --count": [(0, "0\n", ""), (0, "1\n", "")]})
    order = []

    def run(argv, **kw):
        order.append(argv[1])
        return fake(argv, **kw)

    ok, message = publish.publish(tmp_path, "bench: t1 quick 2026-10-14", lambda: order.append("rebuild"), run=run)
    return ok, message, fake, order


def test_publish_order_and_paths(tmp_path):
    ok, message, fake, order = _publish_sequence(tmp_path)
    assert ok, message
    writes = [c for c in fake.calls if c[1] in ("pull", "add", "commit", "push")]
    assert writes == [
        ["git", "pull", "--rebase"],
        ["git", "add", "bench/results", "bench/README.md"],
        ["git", "commit", "-m", "bench: t1 quick 2026-10-14", "--", "bench/results", "bench/README.md"],
        ["git", "push"],
    ]
    assert order.index("pull") < order.index("rebuild") < order.index("add")
    assert order[-1] == "push"
    for kw in fake.kwargs:
        assert kw["cwd"] == tmp_path and kw["capture_output"] is True and kw["text"] is True
        assert kw["encoding"] == "utf-8" and kw["errors"] == "replace"


def test_publish_never_autostashes(tmp_path):
    ok, _, fake, _ = _publish_sequence(tmp_path)
    assert ok and not any("--autostash" in c for c in fake.calls)


def test_publish_restores_generated_files_before_the_pull(tmp_path):
    fake = FakeGit({
        "rev-list --count": [(0, "0\n", ""), (0, "1\n", "")],
        "ls-files -- ": (0, "bench/README.md\nbench/results/charts/full_map.svg\n", ""),
        "ls-files --others": (0, "bench/results/charts/new.svg\n", ""),
    })
    chart = tmp_path / "bench" / "results" / "charts" / "new.svg"
    chart.parent.mkdir(parents=True)
    chart.write_text("x")
    ok, message = publish.publish(tmp_path, "m", lambda: None, run=fake)
    assert ok, message
    subs = fake.subcommands()
    checkout = ["git", "checkout", "HEAD", "--", "bench/README.md", "bench/results/charts/full_map.svg"]
    assert checkout in fake.calls
    assert fake.calls.index(checkout) < subs.index("pull")
    assert not chart.exists()  # the untracked chart would block a pull bringing the same file


def test_publish_does_nothing_when_branch_is_ahead(tmp_path):
    fake = FakeGit({"rev-list --count": (0, "3\n", "")})
    rebuilt = []
    ok, message = publish.publish(tmp_path, "m", lambda: rebuilt.append(1), run=fake)
    assert not ok
    assert "3 unpushed commits" in message and "push them yourself" in message and "--report-only" in message
    assert not {"pull", "checkout", "add", "commit", "push"} & set(fake.subcommands())
    assert rebuilt == []


def test_publish_does_nothing_without_upstream(tmp_path):
    fake = FakeGit({"rev-parse --abbrev-ref": (128, "", "fatal: no upstream configured for branch 'main'")})
    ok, message = publish.publish(tmp_path, "m", lambda: None, run=fake)
    assert not ok and "upstream" in message
    assert fake.subcommands() == ["rev-parse"]


def test_publish_does_not_push_unless_exactly_one_commit_is_ahead(tmp_path):
    for count in ("0", "2"):
        fake = FakeGit({"rev-list --count": [(0, "0\n", ""), (0, count + "\n", "")]})
        ok, message = publish.publish(tmp_path, "m", lambda: None, run=fake)
        assert not ok and f"{count} commits ahead" in message
        assert "push" not in fake.subcommands()
        assert "commit" in fake.subcommands()


def test_publish_stops_on_push_failure(tmp_path):
    fake = FakeGit({"rev-list --count": [(0, "0\n", ""), (0, "1\n", "")],
                    "push": (1, "", "! [rejected] main -> main (fetch first)\n")})
    ok, message = publish.publish(tmp_path, "m", lambda: None, run=fake)
    assert not ok
    assert "push" in message and "rejected" in message
    assert "commit" in fake.subcommands()


def test_publish_stops_at_first_failure(tmp_path):
    fake = FakeGit({"pull": (1, "", "error: cannot pull with rebase: You have unstaged changes.")})
    rebuilt = []
    ok, message = publish.publish(tmp_path, "m", lambda: rebuilt.append(1), run=fake)
    assert not ok and "pull" in message and "unstaged changes" in message
    assert rebuilt == [] and not {"add", "commit", "push"} & set(fake.subcommands())


def test_publish_reports_rebuild_error_without_raising(tmp_path):
    def boom():
        raise ValueError("README markers missing")

    fake = FakeGit()
    ok, message = publish.publish(tmp_path, "m", boom, run=fake)
    assert not ok and "README markers missing" in message
    assert not {"add", "commit", "push"} & set(fake.subcommands())


def test_publish_without_git(tmp_path):
    def run(argv, **kw):
        raise FileNotFoundError("git")

    ok, message = publish.publish(tmp_path, "m", lambda: None, run=run)
    assert not ok and "git not found" in message


def test_git_ready_ok(tmp_path):
    fake = FakeGit({"rev-parse --is-inside-work-tree": (0, "true\n", ""), "remote": (0, "origin\n", "")})
    assert publish.git_ready(tmp_path, run=fake) == (True, "")
    assert all(kw["cwd"] == tmp_path for kw in fake.kwargs)


def test_git_ready_without_git(tmp_path):
    def run(argv, **kw):
        raise FileNotFoundError("git")

    ok, why = publish.git_ready(tmp_path, run=run)
    assert not ok and why.startswith("git not found")


def test_git_ready_not_a_work_tree(tmp_path):
    fake = FakeGit({"rev-parse --is-inside-work-tree": (128, "", "fatal: not a git repository")})
    ok, why = publish.git_ready(tmp_path, run=fake)
    assert not ok and "work tree" in why


def test_git_ready_without_remote(tmp_path):
    fake = FakeGit({"remote": (0, "\n", "")})
    ok, why = publish.git_ready(tmp_path, run=fake)
    assert not ok and "remote" in why


# ---- real git, a bare remote and two clones ----------------------------------------------------------------

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(cwd, *args):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def remotes(tmp_path, monkeypatch):
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Bench Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "bench@example.invalid")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(bare), str(seed))
    _write(seed / "bench" / "README.md", "start\nno results\nend\n")
    _write(seed / "bench" / "results" / "first" / "r.json", "{}\n")
    _write(seed / "other.txt", "x\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "seed")
    _git(seed, "push", "-u", "origin", "main")
    other, mine = tmp_path / "other", tmp_path / "mine"
    _git(tmp_path, "clone", str(bare), str(other))
    _git(tmp_path, "clone", str(bare), str(mine))
    return bare, other, mine


def _rebuild(repo):
    """Stands in for the report generator: lists every result file in the README and writes a chart."""
    def rebuild():
        names = sorted(p.parent.name for p in (repo / "bench" / "results").glob("*/*.json"))
        _write(repo / "bench" / "README.md", "start\nresults: " + " ".join(names) + "\nend\n")
        _write(repo / "bench" / "results" / "charts" / "full_map.svg", "<svg>" + " ".join(names) + "</svg>\n")
    return rebuild


@needs_git
def test_publish_real_repo_after_another_machine_published(remotes):
    bare, other, mine = remotes
    # Another machine publishes first.
    _write(other / "bench" / "results" / "other-box" / "r.json", "{}\n")
    _rebuild(other)()
    _git(other, "add", "bench")
    _git(other, "commit", "-m", "bench: other-box quick")
    _git(other, "push")
    # This machine has run: its result is untracked and its report is already rebuilt locally.
    _write(mine / "bench" / "results" / "my-box" / "r.json", "{}\n")
    _rebuild(mine)()
    assert "M" in _git(mine, "status", "--short", "bench/README.md")

    ok, message = publish.publish(mine, "bench: my-box quick 2026-10-14", _rebuild(mine))

    assert ok, message
    assert _git(mine, "stash", "list") == ""
    assert _git(mine, "status", "--short") == ""
    assert _git(mine, "rev-list", "--count", "@{u}..HEAD").strip() == "0"
    pushed = _git(bare, "show", "main:bench/README.md")
    assert "<<<<<<<" not in pushed and "=======" not in pushed
    assert pushed == "start\nresults: first my-box other-box\nend\n"
    files = _git(bare, "ls-tree", "-r", "--name-only", "main")
    assert "bench/results/my-box/r.json" in files and "bench/results/other-box/r.json" in files


@needs_git
def test_publish_real_repo_leaves_unpushed_commits_alone(remotes):
    bare, _, mine = remotes
    _write(mine / "unrelated.txt", "work in progress\n")
    _git(mine, "add", "unrelated.txt")
    _git(mine, "commit", "-m", "unrelated local work")
    _write(mine / "bench" / "results" / "my-box" / "r.json", "{}\n")
    before = _git(bare, "rev-parse", "main")

    ok, message = publish.publish(mine, "bench: my-box quick 2026-10-14", _rebuild(mine))

    assert not ok and "1 unpushed commit" in message
    assert _git(bare, "rev-parse", "main") == before
    assert _git(mine, "rev-list", "--count", "@{u}..HEAD").strip() == "1"
    assert (mine / "bench" / "results" / "my-box" / "r.json").exists()


@needs_git
def test_publish_real_repo_refuses_other_tracked_changes(remotes):
    bare, other, mine = remotes
    _write(other / "other.txt", "changed elsewhere\n")
    _git(other, "commit", "-am", "other change")
    _git(other, "push")
    _write(mine / "other.txt", "dirty local edit\n")
    _write(mine / "bench" / "results" / "my-box" / "r.json", "{}\n")
    before = _git(bare, "rev-parse", "main")

    ok, message = publish.publish(mine, "m", _rebuild(mine))

    assert not ok and "pull" in message
    assert _git(bare, "rev-parse", "main") == before
    assert (mine / "other.txt").read_text() == "dirty local edit\n"
    assert (mine / "bench" / "results" / "my-box" / "r.json").exists()
