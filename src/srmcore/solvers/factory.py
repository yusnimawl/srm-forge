"""Solver adapters by name, so a worker process can build its own."""
from .settings import SolverAdapter


def make_solver(name: str, threads: int | None = None) -> SolverAdapter:
    if name == "ngsolve":
        try:
            from .ngsolve_adapter import NgsolveAdapter
        except ImportError as e:
            raise ImportError("the 'ngsolve' solver needs the optional extra: pip install srmcore[ngsolve]") from e
        if threads is not None:
            import ngsolve
            ngsolve.SetNumThreads(threads)
        return NgsolveAdapter()
    if name == "skfem_reference":
        from .skfem_reference import SkfemReference
        return SkfemReference()
    raise ValueError(f"unknown solver {name!r}; choose 'ngsolve' or 'skfem_reference'")
