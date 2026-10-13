"""Command line entry point of the benchmark."""

import argparse
import sys

from srmbench import BENCH_DIR


def run_self_test() -> int:
    """Run the bench unit tests with pytest and return its exit code."""
    import pytest

    return int(pytest.main(["-c", str(BENCH_DIR / "pytest.ini"), str(BENCH_DIR / "tests")]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="srmbench", description="SRM design tool machine benchmark")
    parser.add_argument("--self-test", action="store_true", help="run the bench unit tests and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return run_self_test()
    parser.print_usage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
