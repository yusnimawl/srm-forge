import importlib
from dataclasses import replace

import pytest

from srmbench import preflight
from srmbench.preflight import (
    Platform,
    apply_cgroup,
    cgroup_memory,
    check_imports,
    check_load,
    check_platform,
    current_platform,
    max_workers,
)

WIN = Platform("Windows", "AMD64", "", None, 22631, 16.0, 9.0, 100.0, 16)
LNX = Platform("Linux", "x86_64", "glibc", (2, 39), None, 16.0, 9.0, 100.0, 4)


def test_supported_platforms_pass():
    assert check_platform(WIN, "long") == []
    assert check_platform(LNX, "quick") == []


@pytest.mark.parametrize(
    "p",
    [
        replace(WIN, machine="ARM64"),
        replace(LNX, machine="aarch64"),
        replace(LNX, libc="musl", glibc=None),
        replace(LNX, glibc=(2, 27)),
        replace(WIN, windows_build=17133),
        replace(WIN, system="Darwin"),
        replace(WIN, machine="x86"),
    ],
)
def test_unsupported_is_fatal(p):
    assert any(x.fatal for x in check_platform(p, "quick"))


def test_supported_boundaries_pass():
    assert check_platform(replace(WIN, windows_build=17134), None) == []
    assert check_platform(replace(LNX, glibc=(2, 28)), None) == []


def test_ram_minimum_per_tier():
    assert check_platform(replace(WIN, ram_gb=7.6), "long") == []  # 0.9 x 8 = 7.2
    assert any(x.fatal for x in check_platform(replace(WIN, ram_gb=7.0), "long"))
    assert check_platform(replace(WIN, ram_gb=3.7), "quick") == []
    assert check_platform(replace(WIN, ram_gb=1.0), None) == []


def test_ram_message():
    msg = check_platform(replace(WIN, ram_gb=3.0), "standard")[0].message
    assert msg == "standard needs at least 4 GB RAM; this machine has 3.0 GB."


def test_disk_and_cpu_minimum():
    problems = check_platform(replace(WIN, free_disk_gb=1.5), None)
    assert any(x.fatal for x in problems)
    assert problems[0].message == "Needs 2 GB free disk for the benchmark environment; 1.5 GB free."
    assert any(x.fatal for x in check_platform(replace(WIN, logical_cpus=1), None))


def test_unsupported_message_names_reason_and_supported_list():
    msg = check_platform(replace(LNX, machine="aarch64"), None)[0].message
    assert "aarch64" in msg and "x86_64" in msg and "2.28" in msg
    assert msg.startswith("This machine is not supported: ")
    assert msg.endswith("Supported: Windows 10 1803+ or 11 on x64, Linux x86_64 with glibc 2.28+.")


@pytest.mark.parametrize(
    "args,want",
    [
        ((16, 30.0, 1.0, None), 16),
        ((32, 8.0, 1.0, None), 7),
        ((16, 30.0, 1.0, 4), 4),
        ((16, 1.2, 2.0, None), 1),
        ((16, 30.0, None, None), 16),
        ((16, 30.0, 0.0, None), 16),
        ((16, 30.0, -1.0, 4), 4),
    ],
)
def test_max_workers(args, want):
    assert max_workers(*args) == want


def test_current_platform_runs_here(tmp_path):
    p = current_platform(tmp_path / "does" / "not" / "exist")
    assert p.logical_cpus >= 1 and p.ram_gb > 0 and p.free_disk_gb > 0
    assert p.available_ram_gb <= p.ram_gb


def test_check_imports_ok_here():
    assert check_imports() == []


def test_check_imports_names_module_and_error(monkeypatch):
    real = importlib.import_module

    def fake(name, *a, **k):
        if name == "gmsh":
            raise ImportError("libGLU.so.1: cannot open shared object file")
        return real(name, *a, **k)

    monkeypatch.setattr(preflight.importlib, "import_module", fake)
    problems = check_imports()
    assert len(problems) == 1 and problems[0].fatal
    assert "gmsh" in problems[0].message and "libGLU.so.1" in problems[0].message


class _Battery:
    def __init__(self, plugged):
        self.power_plugged = plugged


def test_check_load_battery_and_cpu(monkeypatch):
    monkeypatch.setattr(preflight.psutil, "sensors_battery", lambda: _Battery(False))
    monkeypatch.setattr(preflight.psutil, "cpu_percent", lambda interval=None: 55.0)
    problems = check_load(0.0)
    assert len(problems) == 2 and not any(x.fatal for x in problems)


def test_check_load_quiet_machine(monkeypatch):
    monkeypatch.setattr(preflight.psutil, "sensors_battery", lambda: None)
    monkeypatch.setattr(preflight.psutil, "cpu_percent", lambda interval=None: 3.0)
    assert check_load(0.0) == []
    monkeypatch.setattr(preflight.psutil, "sensors_battery", lambda: _Battery(True))
    assert check_load(0.0) == []


def test_check_load_unknown_ac_state_is_not_a_warning(monkeypatch):
    monkeypatch.setattr(preflight.psutil, "sensors_battery", lambda: _Battery(None))
    monkeypatch.setattr(preflight.psutil, "cpu_percent", lambda interval=None: 3.0)
    assert check_load(0.0) == []


def _write(root, rel, text):
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def test_cgroup_v2_limited(tmp_path):
    _write(tmp_path, "memory.max", "4294967296\n")
    _write(tmp_path, "memory.current", "1073741824\n")
    assert cgroup_memory(tmp_path) == (4294967296, 1073741824)


def test_cgroup_v2_max_means_unlimited(tmp_path):
    _write(tmp_path, "memory.max", "max\n")
    _write(tmp_path, "memory.current", "1073741824\n")
    assert cgroup_memory(tmp_path) is None


def test_cgroup_v1_limited(tmp_path):
    _write(tmp_path, "memory/memory.limit_in_bytes", "2147483648\n")
    _write(tmp_path, "memory/memory.usage_in_bytes", "536870912\n")
    assert cgroup_memory(tmp_path) == (2147483648, 536870912)


def test_cgroup_v1_unlimited(tmp_path):
    _write(tmp_path, "memory/memory.limit_in_bytes", "9223372036854771712\n")
    _write(tmp_path, "memory/memory.usage_in_bytes", "536870912\n")
    assert cgroup_memory(tmp_path) is None


def test_cgroup_files_missing_or_garbled(tmp_path):
    assert cgroup_memory(tmp_path) is None
    _write(tmp_path, "memory.max", "garbage")
    _write(tmp_path, "memory.current", "1")
    assert cgroup_memory(tmp_path) is None


def test_apply_cgroup_takes_the_smaller_figures():
    gb = 1_000_000_000
    assert apply_cgroup(64 * gb, 50 * gb, (4 * gb, 1 * gb)) == (4 * gb, 3 * gb)
    assert apply_cgroup(8 * gb, 2 * gb, (16 * gb, 1 * gb)) == (8 * gb, 2 * gb)
    assert apply_cgroup(8 * gb, 2 * gb, (4 * gb, 5 * gb)) == (4 * gb, 0)
    assert apply_cgroup(8 * gb, 2 * gb, None) == (8 * gb, 2 * gb)
