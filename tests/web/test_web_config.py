from pathlib import Path

import pytest

from srmweb.config import check_exposure, is_loopback, load_settings


def test_defaults():
    s = load_settings({})
    assert (s.host, s.port, s.db, s.cache_dir) == (
        "127.0.0.1", 8000, Path("srmweb.db"), Path("cache"))
    assert s.workers is None and s.token is None and s.queue_max == 10
    assert s.static_dir.parts[-2:] == ("web", "dist")


def test_overrides():
    s = load_settings({"SRMWEB_WORKERS": "6", "SRMWEB_STATIC": "x", "SRMWEB_TOKEN": "t"})
    assert s.workers == 6 and s.static_dir == Path("x") and s.token == "t"


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_passes(host):
    assert is_loopback(host)
    check_exposure(load_settings({"SRMWEB_HOST": host}))


def test_exposed_needs_token():
    with pytest.raises(SystemExit, match="SRMWEB_HOST=0.0.0.0 is not loopback"):
        check_exposure(load_settings({"SRMWEB_HOST": "0.0.0.0"}))
    check_exposure(load_settings({"SRMWEB_HOST": "0.0.0.0", "SRMWEB_TOKEN": "t"}))
