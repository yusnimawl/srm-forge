# srmbench — machine benchmark for the SRM design tool — Design Spec

Status: approved in chat 2026-10-14 (owner). Not an R step; a side tool beside the roadmap R1–R10.

## 1. Goal

One double-click (Windows `run.bat`) or one command (Linux `./run.sh`) sets up everything, measures how fast a machine runs this tool's real workload, writes a result file, and rebuilds a comparison README across all machines the owner has run it on. Uses: choosing hardware, planning (how long a map or a search takes, how many workers), and stability/stress checks.

Machines in view: four Windows 10/11 laptops (the reference is the owner's i7-13620H, 10C/16T, 16 GB), a mini PC, a LattePanda Sigma (i5-1340P, 32 GB), Claude cloud sessions, WSL2, Proxmox VMs/LXC, other Linux cloud machines.

## 2. Decisions (owner, 2026-10-14)

- The benchmark runs the real engine (srmcore 8/6 and 12/8 reference designs, Gmsh, NGSolve, the process pool). No synthetic kernel: it would measure a different solver.
- Delivery: bootstrap scripts plus a pinned private environment (approach A). Not a frozen executable (fragile with Gmsh/NGSolve native libraries and spawn workers, about 500 MB per OS, same numbers), not Docker (on Windows it would measure WSL, not the laptop).
- Lives in `bench/` in this repo. The repo is private, so the core is installed from the checkout next to it (`..`); a clone is enough on any machine, a copied `bench/` folder alone is not.
- Three tiers: quick, standard, long.
- Results are committed to the repo and compared in `bench/README.md` (charts, summary table, per-machine detail).
- Run as the normal user; `sudo` only for the Linux system libraries Gmsh needs.

## 3. Supported platforms

| Platform | Supported | Reason |
|---|---|---|
| Windows 10 1803+ / 11, x64 | yes | `curl.exe` and `tar.exe` are built in from 1803 |
| Linux x86_64, glibc ≥ 2.28 (Ubuntu 20.04+, Debian 10+, RHEL/Rocky/Alma 8+, Fedora, WSL2, Proxmox VM/LXC, Claude cloud) | yes | NGSolve wheels are `manylinux_2_28_x86_64`, Gmsh `manylinux_2_24_x86_64` |
| Linux aarch64 (Raspberry Pi, Graviton, Ampere), Windows on ARM | no | no Gmsh or NGSolve wheels |
| Linux musl (Alpine) | no | no musl wheels for Gmsh or NGSolve |
| 32-bit anything | no | no wheels |
| macOS | not supported in v1 | wheels exist; left out until asked |

Resource minimums (checked by preflight; the per-worker figure is measured during implementation and written into the README requirements section):

- RAM: 4 GB total for quick and standard, 8 GB for long. The worker count is capped at `floor((available RAM − 1 GB) / peak RAM per worker)`.
- Disk: 2 GB free in `bench/.runtime/` (uv, Python, the venv, the uv cache).
- CPU: at least 2 logical CPUs.
- Network for the first setup (GitHub for uv, PyPI and python-build-standalone for packages and Python). Runs after setup need no network except the optional push.

## 4. Layout

```
bench/
  run.bat               Windows entry point
  run.sh                Linux entry point (executable bit set in git)
  requirements.in       direct dependencies of the bench environment
  requirements.lock     uv pip compile --universal --generate-hashes, Python 3.12
  uv.version            the pinned uv version and the SHA-256 of each uv archive used
  srmbench/             the benchmark package (Python)
    __main__.py         CLI
    preflight.py        OS, CPU, RAM, disk, battery, import checks
    sysinfo.py          machine description
    workload.py         the measured steps (mesh, solve, batch, maps)
    monitor.py          peak RAM of the worker processes
    tiers.py            which steps each tier runs, in order
    result.py           result model, JSON write/read, versions
    projections.py      projected times and recommended workers
    report.py           README tables and SVG charts
    publish.py          git pull/commit/push of results
    reference/          reference values for the correctness checks
  tests/                unit tests for srmbench (run with `run --self-test`)
  results/<label>/<YYYY-MM-DD>T<HHMM>-<tier>.json
  results/charts/*.svg  generated
  README.md             how to run, requirements, and the generated comparison
  .runtime/             git-ignored: uv, Python, venv, uv cache, local label
```

`srmbench` uses srmcore and srmapp modules the way `examples/` do: `srmapp.references.make_8_6`, `make_12_8`; `srmcore.model.design` (`Design`, `MeshSettings`); `srmcore.mesh.build_machine_mesh`; `srmcore.solvers.factory.make_solver`; `srmcore.maps.point.solve_point`; `srmcore.maps.run.run_map`; `srmcore.maps` (`build_map`, `analyse_map`, `build_overlap_map`, `fem_checks`); `srmcore.maps.grids` (`GRID_SIZES`, `angle_grid`, `current_grid`, `aligned_angle`); `srmcore.mesh.settings.resolve_mesh_settings`. It never imports `tests/` and nothing in `src/` imports it.

## 5. Bootstrap (`run.bat`, `run.sh`)

Both scripts do the same steps; everything goes under `bench/.runtime/` (`UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR` and the venv point there), so deleting that folder removes all of it.

1. **Platform gate (in the shell, before any download).** Windows: `PROCESSOR_ARCHITECTURE` (and `PROCESSOR_ARCHITEW6432`) must be `AMD64`; the Windows build must be ≥ 17134. Linux: `uname -m` must be `x86_64`; glibc from `ldd --version` must be ≥ 2.28; musl is detected and refused. On failure: one plain message naming the problem and the supported list, exit code 2, nothing downloaded.
2. **uv.** If `.runtime/uv/uv(.exe)` is missing: download the pinned uv release archive from GitHub (`curl.exe` on Windows; `curl` or `wget` on Linux), check its SHA-256 against `uv.version` (`certutil -hashfile` / `sha256sum`), unpack (`tar`). A hash mismatch stops with a message.
3. **Python and venv.** `uv python install 3.12`, `uv venv .runtime/venv --python 3.12` (skipped when present and its lock hash stamp matches).
4. **Packages.** `uv pip sync requirements.lock` then `uv pip install --no-deps -e ..` (srmcore, srmapp, srmweb from the checkout, editable, so the benchmark always runs the checked-out source). A stamp file holds the hashes of `requirements.lock` and `../pyproject.toml`; a mismatch reinstalls.
5. **Linux system libraries.** After install, `python -c "import gmsh"`. If it fails with a missing shared library: with `apt-get` install `libglu1-mesa libxcursor1 libxft2 libxinerama1`; with `dnf`/`yum` install `mesa-libGLU libXcursor libXft libXinerama`; prefix `sudo` unless running as root; if neither root nor sudo is available, or the package manager is unknown, print the exact command and stop. Then re-check the import.
6. **Run.** `.runtime/venv/.../python -m srmbench <args>`.
7. **Cleanup (after Python exits, so no file is in use).** Python leaves a flag file in `.runtime/` saying what the user chose at the finish prompt; the script acts on it: delete `.runtime/` entirely, or keep it, or keep it and `uv pip install "..[web]"` so `srmweb` runs from this environment (and print that the web frontend build needs Node: `cd web; npm ci; npm run build`).

The scripts never run `pip` outside `.runtime/`, never touch the repo's own `.venv`, and never change system settings beyond the Linux library install in step 5.

## 6. CLI

```
run.bat | ./run.sh [--tier quick|standard|long] [--label NAME] [--workers N]
                   [--yes] [--keep | --delete | --keep-full] [--push | --no-push]
                   [--report-only] [--self-test]
```

- No `--tier`: a menu with the three tiers and their time on the reference laptop (quick about 3 min, standard about 15 min, long about 2.2 h; "slower machines take longer").
- `--label`: the machine label (lowercase, `[a-z0-9-]`, max 40). Without it, asked once with the hostname as default and remembered in `.runtime/label`.
- `--workers N`: cap the largest worker count (default: RAM- and CPU-capped as in §3).
- `--yes`: no prompts (cloud and CI); with it, the finish defaults are `--keep` and `--no-push` unless given.
- `--report-only`: rebuild the README and charts from `results/` and exit (no benchmark).
- `--self-test`: run `bench/tests` with pytest in the bench environment.
- Ctrl+C: stops the running step, kills the workers, saves nothing, and still reaches the finish prompt.

## 7. Preflight (Python, before any timing)

Fails with a plain message and exit code 2:

- OS/arch/glibc again (defence in depth for direct `python -m srmbench` use).
- RAM below the tier minimum; free disk below 2 GB.
- `import srmcore, gmsh, ngsolve` fails (the message names the missing library).

Warns and asks to continue (`--yes` continues):

- On battery (`psutil.sensors_battery()`): "Plug in; laptops throttle on battery."
- Other processes using more than 20 % of the CPU over a 3 s sample: "Close other heavy programs."
- Windows power mode cannot be read reliably; the README tells the user to set "Best performance".

## 8. What is measured

All timings are wall clock (`time.perf_counter`), cold (no map cache: `cache_dir=None`; field cache unused), NGSolve solver, workers single-threaded as in `srmcore.maps.pool`. Designs: `make_8_6()` and `make_12_8()` with `I_MAX = {"8_6": 20.0, "12_8": 10.0}` as in `examples/speed_budget.py`.

| Step | What | Tiers |
|---|---|---|
| `sysinfo` | OS, version, arch, CPU model (`py-cpuinfo`), physical and logical cores, RAM, Python, glibc, versions of srmcore, numpy, scipy, gmsh, ngsolve, the lock hash | all |
| `mesh` | `build_machine_mesh` time for the 8/6 at `screening` and `full`; node counts | all |
| `single_solve` | 5 cold `solve_point` calls in the parent, 8/6 `screening`, phase A 20 A at the aligned angle; median and spread; plus 3 at `full` | all |
| `correctness_points` | 3 points (aligned, mid, unaligned; 20 A) on the 8/6 `screening`: ψ and torque against `reference/points_8_6.json` (ψ within 1e-3 relative; torque within 1e-3 × the largest reference torque, so the near-zero aligned and unaligned torques are not judged on cancellation noise; the same level the engine's goldens hold on Windows and Linux CI; a different mesh node count is reported) | all |
| `batch` | throughput at W workers: `run_map` on a fixed mesh with the same 8 points per worker for every W (4 angles of the 8/6 `screening` grid, repeated W times, at I_max/2 and I_max); solves per minute, excluding the parent mesh build | quick: W = physical cores and W = logical; standard and long: W = 1, 2, 4, … up to the cap, plus the physical and logical counts |
| `peak_ram` | peak resident memory per worker process during the batches (`monitor.py`, 0.5 s sampling; Windows peak working set); not recorded for W = 1, which runs in the benchmark's own process | all |
| `screening_map` | `build_map` + `analyse_map`, 8/6 `screening` (40 × 8), at the recommended W; key numbers and check statuses against `reference/goldens_8_6.json` (rel 1e-3, statuses equal) | standard, long |
| `sustained` | the `batch` at the recommended W repeated for 5 min (standard) or 20 min (long); throughput per minute; throttle = last minute / first minute − 1 | standard, long |
| `full_maps` | `build_map` + `analyse_map` at `full` for the 8/6 and 12/8, then `build_overlap_map` + `fem_checks` (the `full` extras), at the recommended W | long |

Recommended workers: the smallest W whose batch throughput is at least 95 % of the best measured, then RAM-capped. In quick, the better of the two measured W.

Reference values: `reference/points_8_6.json` is generated on the reference machine by a `srmbench` maintenance command and stamped with the srmcore version; `reference/goldens_8_6.json` is a copy of `tests/maps/goldens_8_6.json`. If the installed srmcore version differs from the stamp, the correctness result is "not checked" (not a failure).

A correctness failure does not stop the run; the result records it and the README marks the row ✗.

## 9. Projections

Every result carries projections, labelled "projected" when estimated and "measured" when the tier ran the step:

- `screening` map (8/6) = mesh time + (the `screening` grid's point count, `len(angle_grid) × len(current_grid)`) × (60 / batch throughput at the recommended W).
- `full` map (8/6) = full mesh time + (the `full` grid's point count) × (single solve `full` / single solve `screening`) × (60 / throughput).
- Search, 24 candidates = 24 × the `full` map projection. Labelled rough: the real search adds the stage-1 filter and the turns scan, and candidate sizes vary.
- Recommended `SRMWEB_WORKERS` = the recommended W.

The long tier records how far the projections were from the measured times, so the projection rules can be judged.

## 10. Result file

`results/<label>/<YYYY-MM-DD>T<HHMM>-<tier>.json`, UTF-8, sorted keys:

- `schema` (`"srmbench-result"`), `bench_version` (`"1.0"`), `tier`, `label`, `started`, `finished` (ISO 8601 with offset), `status` (`complete`).
- `machine` (the `sysinfo` step), `versions`, `lock_hash`.
- `steps`: one entry per step with its raw numbers (every sample, not only summaries).
- `summary`: single solve s (screening), best and recommended W, throughput at recommended W, peak RAM per worker GB, throttle %, screening and full map times (measured or projected, with a flag), search hours (projected), correctness (`pass`, `fail`, `not checked` with details).
- `warnings`: the preflight warnings that were accepted.

No user name, home path or IP address is stored. The label and hostname-derived default are the only identifiers.

## 11. README comparison

`bench/README.md` has hand-written parts (what this is, requirements from §3, how to run on each platform, the flags, how to read the results) and one generated block between `<!-- srmbench:results:start -->` and `<!-- srmbench:results:end -->`, rebuilt by `report.py`:

1. **Charts** (SVG in `results/charts/`, matplotlib, transparent background, mid-grey text that reads on GitHub's light and dark themes, no blue; the reference machine in grey, the rest amber; a dash or hatch pattern per machine where series overlap):
   - `full_map.svg`: horizontal bars, `full` map minutes per machine (measured where available, projected bars hatched), sorted, lower is better. The headline chart.
   - `scaling.svg`: solves per minute against workers, one line per machine (standard and long results).
   - `index.svg`: grouped bars, single-core index and all-core index per machine, reference = 100.
2. **Summary table**, one row per machine (its latest result with the current `bench_version`): label, CPU, cores, RAM, OS, tier, single solve, recommended W, screening map, full map, search (24), RAM per worker, throttle, correctness, index. Projected values are marked `~`.
3. **Per machine**: a `<details>` section with machine info, versions, every step's numbers, the scaling data, the sustained trace, all earlier runs (date, tier, headline numbers), and a link to each JSON file.

Rules: results with a different `bench_version` are listed under "older benchmark versions" and left out of the charts and the table. The reference machine is named in `bench/reference-machine.txt` (initially the owner's i7-13620H label); without a result for it, the index columns are left empty.

## 12. Finish prompt and publishing

After the run (or after Ctrl+C), in order:

1. The summary is printed (the table row and the projections).
2. The README and charts are rebuilt locally.
3. "Commit and push results? [y/N]" (`--push`/`--no-push`). On yes: `git pull --rebase --autostash`, rebuild the README again (so results pushed by other machines are included), `git add bench/results bench/README.md`, `git commit -m "bench: <label> <tier> <date>" -- bench/results bench/README.md` (only those paths), `git push`. Any git failure prints the reason and leaves the result file in place; the run itself still counts as done. Without git or a remote, the prompt is skipped with a note.
4. "Delete the benchmark environment (about 1.5 GB)? You need to reinstall to run it again. [y/N]". On no: "Also install the rest of the SRM design tool into this environment so `srmweb` runs? [y/N]". The choice goes into the flag file for the shell script (§5 step 7).

## 13. Testing

- `bench/tests` (pytest, run by `--self-test`): preflight decisions on faked platform data (arch, glibc, musl, RAM, disk); label validation; result write/read round trip and schema; projections and recommended W on synthetic numbers; README generation from fixture result files (table rows, version filtering, reference index, projected markers) and that every chart is written and contains no blue colour literal (hue 190–250°, as `web/src/lib/noBlue.test.ts`); publish commands built correctly (git calls faked).
- Smoke run of `quick` with `run.bat` on the owner's laptop during implementation; its result is the first committed result and the reference row.
- CI: a new workflow `.github/workflows/bench.yml` on pushes that touch `bench/**` and on `workflow_dispatch`: Ubuntu and Windows runners each run the bootstrap from scratch with `--self-test --yes --keep`, then `--tier quick --label ci-<os> --yes --delete --no-push` (which also checks that the delete leaves no `.runtime/`). The CI results are not committed.

## 14. Out of scope

macOS, ARM, GPU, temperature sensors (no reliable cross-platform reading without admin; the sustained step stands in), an offline installer, a frozen executable, Docker, the web UI, uploading results anywhere other than this repo.
