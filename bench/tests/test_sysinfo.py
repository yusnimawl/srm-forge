import getpass
import importlib.metadata
import json
import socket

from srmbench.sysinfo import lock_hash, machine_info, package_versions

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
