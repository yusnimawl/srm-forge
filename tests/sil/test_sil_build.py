import pytest
from sil_fixtures import call_in_child

from srmsil import build

ADD_C = """
#ifdef _WIN32
__declspec(dllexport)
#endif
double add(double a, double b) { return a + b; }
"""


def test_compile_host_builds_and_caches(tmp_path):
    src = tmp_path / "add.c"
    src.write_text(ADD_C)
    lib = build.compile_host([src], [], tmp_path / "out")
    mtime = lib.stat().st_mtime_ns
    assert build.compile_host([src], [], tmp_path / "out") == lib
    assert lib.stat().st_mtime_ns == mtime
    assert call_in_child(lib, "add", 2, 3) == 5


def test_compile_host_error_carries_log(tmp_path):
    src = tmp_path / "bad.c"
    src.write_text("int f( { return 1 }\n")
    with pytest.raises(build.CompileError) as exc:
        build.compile_host([src], [], tmp_path / "out")
    assert "error" in exc.value.log


def test_cache_key_changes_with_header(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    h = inc / "k.h"
    src = tmp_path / "add.c"
    src.write_text('#include "k.h"\n' + ADD_C)
    h.write_text("#define K 1\n")
    a = build.compile_host([src], [inc], tmp_path / "out")
    h.write_text("#define K 2\n")
    b = build.compile_host([src], [inc], tmp_path / "out")
    assert a != b


def test_controller_sources_rejects_bad_folders(tmp_path):
    f = tmp_path / "x.c"
    f.write_text("")
    empty = tmp_path / "empty"
    empty.mkdir()
    for bad in (tmp_path / "missing", f, empty):
        with pytest.raises(ValueError):
            build.controller_sources(bad)
    assert build.controller_sources(tmp_path) == [f]


def test_target_check_pass_and_fail(tmp_path):
    good = tmp_path / "good.c"
    good.write_text("#include <math.h>\n#include <stdint.h>\n"
                    "float g(float x, int32_t n) { return sqrtf(x) * (float)n; }\n")
    r = build.target_check([good], [])
    assert r.ok, r.log
    assert r.compiler
    bad = tmp_path / "bad.c"
    bad.write_text("int h(void) { int unused = 3; return 0; }\n")
    r = build.target_check([bad], [])
    assert not r.ok
    assert "unused" in r.log


def test_cache_key_sees_nested_headers(tmp_path):
    inc = tmp_path / "inc"
    (inc / "sub").mkdir(parents=True)
    h = inc / "sub" / "k.h"
    src = tmp_path / "add.c"
    src.write_text('#include "sub/k.h"\n' + ADD_C)
    h.write_text("#define K 1\n")
    a = build.compile_host([src], [inc], tmp_path / "out")
    h.write_text("#define K 2\n")
    assert build.compile_host([src], [inc], tmp_path / "out") != a
