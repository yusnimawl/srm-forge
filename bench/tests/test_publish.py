import subprocess

from srmbench import publish


def _done(argv, code=0, out="", err=""):
    return subprocess.CompletedProcess(argv, code, out, err)


class FakeGit:
    """Records every call; `fail` maps a git subcommand to (returncode, stderr)."""

    def __init__(self, fail=None, answers=None):
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []
        self.fail = fail or {}
        self.answers = answers or {}

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        self.kwargs.append(kw)
        sub = argv[1]
        if sub in self.fail:
            code, err = self.fail[sub]
            return _done(argv, code, "", err)
        return _done(argv, 0, self.answers.get(sub, ""), "")


def test_publish_order_and_paths(tmp_path):
    fake = FakeGit()
    order = []

    def run(argv, **kw):
        order.append(argv[1])
        return fake(argv, **kw)

    ok, message = publish.publish(tmp_path, "bench: t1 quick 2026-10-14", lambda: order.append("rebuild"), run=run)
    assert ok, message
    assert order == ["pull", "rebuild", "add", "commit", "push"]
    assert fake.calls == [
        ["git", "pull", "--rebase", "--autostash"],
        ["git", "add", "bench/results", "bench/README.md"],
        ["git", "commit", "-m", "bench: t1 quick 2026-10-14", "--", "bench/results", "bench/README.md"],
        ["git", "push"],
    ]
    for kw in fake.kwargs:
        assert kw["cwd"] == tmp_path and kw["capture_output"] is True and kw["text"] is True


def test_publish_stops_on_push_failure(tmp_path):
    fake = FakeGit(fail={"push": (1, "! [rejected] main -> main (fetch first)\n")})
    ok, message = publish.publish(tmp_path, "m", lambda: None, run=fake)
    assert not ok
    assert "push" in message and "rejected" in message
    assert [c[1] for c in fake.calls] == ["pull", "add", "commit", "push"]  # the commit happened


def test_publish_stops_at_first_failure(tmp_path):
    fake = FakeGit(fail={"pull": (1, "conflict")})
    rebuilt = []
    ok, message = publish.publish(tmp_path, "m", lambda: rebuilt.append(1), run=fake)
    assert not ok and "pull" in message and "conflict" in message
    assert [c[1] for c in fake.calls] == ["pull"] and rebuilt == []


def test_publish_reports_rebuild_error_without_raising(tmp_path):
    def boom():
        raise ValueError("README markers missing")

    fake = FakeGit()
    ok, message = publish.publish(tmp_path, "m", boom, run=fake)
    assert not ok and "README markers missing" in message
    assert [c[1] for c in fake.calls] == ["pull"]


def test_publish_without_git(tmp_path):
    def run(argv, **kw):
        raise FileNotFoundError("git")

    ok, message = publish.publish(tmp_path, "m", lambda: None, run=run)
    assert not ok and "git not found" in message


def test_git_ready_ok(tmp_path):
    fake = FakeGit(answers={"rev-parse": "true\n", "remote": "origin\n"})
    assert publish.git_ready(tmp_path, run=fake) == (True, "")
    assert all(kw["cwd"] == tmp_path for kw in fake.kwargs)


def test_git_ready_without_git(tmp_path):
    def run(argv, **kw):
        raise FileNotFoundError("git")

    ok, why = publish.git_ready(tmp_path, run=run)
    assert not ok and why.startswith("git not found")


def test_git_ready_not_a_work_tree(tmp_path):
    fake = FakeGit(fail={"rev-parse": (128, "fatal: not a git repository")})
    ok, why = publish.git_ready(tmp_path, run=fake)
    assert not ok and "work tree" in why


def test_git_ready_without_remote(tmp_path):
    fake = FakeGit(answers={"rev-parse": "true\n", "remote": "\n"})
    ok, why = publish.git_ready(tmp_path, run=fake)
    assert not ok and "remote" in why
