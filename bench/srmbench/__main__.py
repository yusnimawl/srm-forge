"""Command line entry point of the benchmark."""

import os

# In-process work (the W=1 batch, single solves) must run single-threaded like the pool workers do;
# the thread pools of numpy and its BLAS read these variables when they load, so set them before any import.
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import argparse  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from srmbench import BENCH_DIR, REPO_DIR, RUNTIME_DIR  # noqa: E402

RESULTS_DIR = BENCH_DIR / "results"
README = BENCH_DIR / "README.md"
REFERENCE_FILE = BENCH_DIR / "reference-machine.txt"

TIER_NAMES = ("quick", "standard", "long")
# Times on the reference laptop.
TIER_MENU = ("quick about 3 min", "standard about 15 min", "long about 2.2 h")


def run_self_test() -> int:
    """Run the bench unit tests with pytest and return its exit code."""
    import pytest

    return int(pytest.main(["-c", str(BENCH_DIR / "pytest.ini"), str(BENCH_DIR / "tests")]))


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive whole number")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="srmbench", description="SRM design tool machine benchmark")
    parser.add_argument("--tier", choices=TIER_NAMES, help="what to run; without it a menu asks")
    parser.add_argument("--label", help="machine label, lowercase a-z0-9 and '-', up to 40 characters")
    parser.add_argument("--workers", type=_positive_int, metavar="N", help="cap the largest worker count")
    parser.add_argument("--yes", action="store_true",
                        help="no prompts; the finish defaults to --keep and publishing to --no-push")
    finish = parser.add_mutually_exclusive_group()
    finish.add_argument("--keep", action="store_true", help="keep the benchmark environment")
    finish.add_argument("--delete", action="store_true", help="delete the benchmark environment afterwards")
    finish.add_argument("--keep-full", action="store_true",
                        help="keep the environment and install the rest of the SRM design tool into it")
    push = parser.add_mutually_exclusive_group()
    push.add_argument("--push", dest="push", action="store_true", default=None, help="commit and push the results")
    push.add_argument("--no-push", dest="push", action="store_false", help="do not commit or push")
    parser.add_argument("--report-only", action="store_true", help="rebuild the README and charts from results/ and exit")
    parser.add_argument("--self-test", action="store_true", help="run the bench unit tests and exit")
    return parser


# ---- prompts and output -----------------------------------------------------------------------------------

def _ask(input_fn, prompt: str) -> str | None:
    """The stripped answer, or None when there is no input to read (a closed stdin)."""
    try:
        return input_fn(prompt).strip()
    except EOFError:
        return None


def _yes(input_fn, prompt: str) -> bool:
    return (_ask(input_fn, prompt) or "").lower() in ("y", "yes")


def _logger():
    start = time.monotonic()

    def log(message: str) -> None:
        elapsed = int(time.monotonic() - start)
        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{stamp} +{elapsed // 60:02d}:{elapsed % 60:02d}] {message}", flush=True)

    return log


def _describe(exc: BaseException) -> str:
    """One line: the error and where it came from."""
    frames = traceback.extract_tb(exc.__traceback__)
    where = f" (at {Path(frames[-1].filename).name}:{frames[-1].lineno} in {frames[-1].name})" if frames else ""
    return f"{type(exc).__name__}: {exc}{where}"


def runtime_size_gb(path: Path) -> float:
    """Total size of the files below `path` in GB (links are not followed); 0 when it does not exist."""
    total = 0
    for folder, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total / 1e9


def default_label(hostname: str) -> str:
    return re.sub("[^a-z0-9-]", "-", hostname.lower())[:40] or "machine"


def _reference_label() -> str | None:
    """The first line of bench/reference-machine.txt; None when the file is missing or empty."""
    try:
        lines = REFERENCE_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return (lines[0].strip() or None) if lines else None


# ---- steps ------------------------------------------------------------------------------------------------

def _choose_label(args, input_fn) -> str | None:
    """The label from the flag, the remembered one or a prompt; None (after printing why) when it is invalid."""
    from srmbench.result import LABEL_RULE, validate_label

    if args.label is not None:
        try:
            return validate_label(args.label)
        except ValueError as exc:
            print(exc)
            return None
    label_file = RUNTIME_DIR / "label"
    try:
        return validate_label(label_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    default = default_label(socket.gethostname())
    label = default
    if not args.yes:
        while True:
            answer = _ask(input_fn, f"Machine label ({LABEL_RULE}) [{default}]: ")
            if not answer:
                label = default
                break
            try:
                label = validate_label(answer)
                break
            except ValueError as exc:
                print(exc)
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        label_file.write_text(label + "\n", encoding="utf-8")
    except OSError:
        pass
    return label


def _choose_tier(args, input_fn) -> str | None:
    if args.tier is not None:
        return args.tier
    if args.yes:
        print("--yes needs --tier (quick, standard or long).")
        return None
    print("Which benchmark? (times on the reference laptop; slower machines take longer)")
    for i, line in enumerate(TIER_MENU, start=1):
        print(f"  {i}) {line}")
    while True:
        answer = _ask(input_fn, "Tier [1-3, default 1]: ")
        if answer is None:
            print("No tier given and no input to ask; use --tier.")
            return None
        answer = answer.lower()
        if answer == "":
            return TIER_NAMES[0]
        if answer in TIER_NAMES:
            return answer
        if answer in ("1", "2", "3"):
            return TIER_NAMES[int(answer) - 1]
        print("Enter 1, 2 or 3.")


def _preflight(tier: str, args, input_fn) -> tuple | int:
    """(platform, accepted warnings), or the exit code after printing why the run cannot or should not start."""
    from srmbench import preflight

    platform = preflight.current_platform(RUNTIME_DIR)
    problems = preflight.check_platform(platform, tier)
    fatal = [p for p in problems if p.fatal]
    if not fatal:
        fatal = preflight.check_imports()
    if fatal:
        for p in fatal:
            print(p.message)
        return 2
    warnings = [p.message for p in problems] + [p.message for p in preflight.check_load()]
    if warnings:
        for message in warnings:
            print(f"Warning: {message}")
        if not args.yes and not _yes(input_fn, "Continue anyway? [y/N] "):
            print("Nothing was run.")
            return 1
    return platform, warnings


def _print_summary(result) -> None:
    s = result.summary

    def get(key, fmt, default="n/a"):
        value = s.get(key)
        return default if value is None else fmt(value)

    def map_time(key):
        entry = s.get(key)
        if not entry:
            return "n/a"
        minutes = entry["value"] / 60
        return f"{minutes:.1f} min" + ("" if entry.get("measured") else " (projected)")

    correctness = (s.get("correctness") or {}).get("status", "n/a")
    print()
    print(f"Result for {result.label} ({result.tier}):")
    print(f"  single solve, 8/6 screening: {get('single_solve_s', lambda x: f'{x:.2f} s')}")
    print(f"  recommended workers:         {get('recommended_workers', str)}")
    print(f"  throughput:                  {get('throughput_per_min', lambda x: f'{x:.1f} solves/min')}")
    print(f"  screening map, 8/6:          {map_time('screening_map_s')}")
    print(f"  full map, 8/6:               {map_time('full_map_s')}")
    print(f"  design search:               {get('search_h', lambda x: f'{x:.1f} h')} (projected)")
    if s.get("throttle_pct") is not None:
        print(f"  sustained throttle:          {s['throttle_pct']:+.1f} %")
    print(f"  correctness:                 {correctness}")


def _publish(result, label: str, tier: str, args, input_fn, ref_label) -> None:
    from srmbench import publish, report

    if args.push is False or (args.push is None and args.yes):
        return
    ready, why = publish.git_ready(REPO_DIR)
    if not ready:
        print(f"Not publishing: {why}.")
        return
    if args.push is None and not _yes(input_fn, "Commit and push results? [y/N] "):
        return
    message = f"bench: {label} {tier} {result.started[:10]}"
    ok, detail = publish.publish(REPO_DIR, message, lambda: report.build_report(RESULTS_DIR, README, ref_label))
    if ok:
        print(detail)
    else:
        print(f"Publishing failed: {detail}")
        print("The result file is saved; nothing was lost. Fix git and publish by hand.")


def _finish(args, input_fn) -> None:
    """Leave the user's choice for run.bat / run.sh, which act on it after Python exits."""
    if args.delete:
        choice = "delete"
    elif args.keep_full:
        choice = "keep-full"
    elif args.keep or args.yes:
        choice = "keep"
    elif _yes(input_fn, f"Delete the benchmark environment (about {runtime_size_gb(RUNTIME_DIR):.1f} GB)? "
                        "You need to reinstall to run it again. [y/N] "):
        choice = "delete"
    elif _yes(input_fn, "Also install the rest of the SRM design tool into this environment so `srmweb` runs? [y/N] "):
        choice = "keep-full"
    else:
        choice = "keep"
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "finish").write_text(choice + "\n", encoding="utf-8")


def _rebuild_report(ref_label) -> None:
    from srmbench import report

    try:
        report.build_report(RESULTS_DIR, README, ref_label)
    except Exception as exc:  # the result file is already saved; a README problem must not hide it
        print(f"README not updated: {_describe(exc)}")


def _run(args, input_fn) -> int:
    from srmbench import tiers
    from srmbench.result import write_result

    label = _choose_label(args, input_fn)
    if label is None:
        return 2
    tier = _choose_tier(args, input_fn)
    if tier is None:
        return 2
    checked = _preflight(tier, args, input_fn)
    if isinstance(checked, int):
        return checked
    platform, warnings = checked

    print(f"Running the {tier} benchmark as '{label}'. Leave the machine alone until it finishes.")
    try:
        result = tiers.run_tier(tier, label, platform, args.workers, _logger())
    except KeyboardInterrupt:
        print("Cancelled; nothing saved.")
        _finish(args, input_fn)
        return 130
    except Exception as exc:
        print(f"The benchmark failed: {_describe(exc)}")
        return 1
    result.warnings = list(warnings)
    path = write_result(result, RESULTS_DIR)
    print(f"Saved {path}")
    _print_summary(result)
    ref_label = _reference_label()
    _rebuild_report(ref_label)
    _publish(result, label, tier, args, input_fn, ref_label)
    _finish(args, input_fn)
    return 0


def main(argv: list[str] | None = None, input_fn=input) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return run_self_test()
    try:
        if args.report_only:
            from srmbench import report

            report.build_report(RESULTS_DIR, README, _reference_label())
            print(f"Rebuilt {README}")
            return 0
        return _run(args, input_fn)
    except KeyboardInterrupt:
        print("Cancelled.")
        return 130
    except Exception as exc:
        print(f"Error: {_describe(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
