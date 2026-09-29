"""One Gmsh initialisation per process; a fresh, isolated model per use."""
import itertools
from collections.abc import Iterator
from contextlib import contextmanager

import gmsh

_initialized = False
_counter = itertools.count()


@contextmanager
def gmsh_model() -> Iterator[str]:
    global _initialized
    if not _initialized:
        gmsh.initialize(readConfigFiles=False, interruptible=False)
        gmsh.option.setNumber("General.Terminal", 0)
        _initialized = True
    name = f"srm_{next(_counter)}"
    gmsh.model.add(name)
    try:
        yield name
    finally:
        gmsh.model.setCurrent(name)
        gmsh.model.remove()
