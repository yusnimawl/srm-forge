import getpass
import importlib.metadata
import json
import socket

import subprocess

from srmbench.sysinfo import git_commit, lock_hash, machine_info, package_versions

KEYS = {"os", "os_version", "arch", "cpu_model", "physical_cores", "logical_cpus", "ram_gb", "python", "glibc"}


def test_machine_info_keys_and_no_identity():
    info = machine_info()
    assert set(info) == KEYS
    text = json.dumps(info)
    assert socket.gethostname() not in text and getpass.getuser() not in text
    assert info["logical_cpus"] >= 1 and info["ram_gb"] == round(info["ram_gb"], 1)


def test_package_versions_has_srmcore():
    v = package_versions()
    assert v["srmcore"] == importlib.metadata.version("srmcore")
    assert set(v) == {"srmcore", "numpy", "scipy", "gmsh", "ngsolve", "matplotlib", "psutil"}


def test_lock_hash(tmp_path):
    f = tmp_path / "x.lock"
    f.write_bytes(b"x")
    assert lock_hash(f) == "2d711642b726"


def _fake_git(head="abc1234\n", status="", fail=False):
    def run(argv, **kw):
        assert argv[0] == "git" and kw["encoding"] == "utf-8" and kw["timeout"] > 0
        out = head if argv[1] == "rev-parse" else status
        return subprocess.CompletedProcess(argv, 1 if fail else 0, out, "boom")
    return run


def test_git_commit_clean_dirty_and_missing(tmp_path):
    assert git_commit(tmp_path, run=_fake_git()) == "abc1234"
    assert git_commit(tmp_path, run=_fake_git(status=" M src/x.py\n")) == "abc1234-dirty"
    assert git_commit(tmp_path, run=_fake_git(fail=True)) is None

    def no_git(argv, **kw):
        raise FileNotFoundError("git")

    def hangs(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 10)

    assert git_commit(tmp_path, run=no_git) is None and git_commit(tmp_path, run=hangs) is None
