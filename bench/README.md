# srmbench: machine benchmark for the SRM design tool

srmbench times the real workload of this tool on your machine: the Gmsh mesh, the NGSolve nonlinear solve, and the process pool that builds flux-linkage and torque maps for the 8/6 and 12/8 reference designs. It is not a synthetic kernel, so the numbers are the waits you will feel in the tool. It also checks that the solver returns the right numbers on this machine, which catches bad RAM, an unstable overclock or a failing cooler. Use it to choose hardware, to plan (how long a map or a search takes, how many workers to use) and as a stability check. Design details are in `docs/superpowers/specs/2026-10-14-srmbench-design.md`.

## Requirements

| Platform | Supported |
|---|---|
| Windows 10 1803+ or Windows 11, x64 | yes |
| Linux x86_64, glibc 2.28+ (Ubuntu 20.04+, Debian 10+, RHEL/Rocky/Alma 8+, Fedora, WSL2, Proxmox VM or LXC, Claude cloud) | yes |
| Linux aarch64 (Raspberry Pi, Graviton, Ampere), Windows on ARM | no, there are no Gmsh or NGSolve wheels |
| Linux musl (Alpine), 32-bit systems | no, there are no wheels |
| macOS | not in v1 |

- RAM: 4 GB for `quick` and `standard`, 8 GB for `long` (a machine passes at 90 % of the figure, because Windows and VMs report less than the installed amount). Each worker process needs about 0.3 GB at the `screening` mesh (measured peak, about 43 000 nodes); `full`-mesh workers need more, roughly in proportion to the node count (about 82 000 nodes for the 8/6). The worker count is capped at (available RAM - 1 GB) / RAM per worker.
- Disk: 2 GB free on the drive that holds `bench/.runtime/`. The environment takes about 0.7 GB on disk (about 195 MB download).
- CPU: at least 2 logical CPUs.
- Network for the first setup only: GitHub (the pinned `uv`), PyPI and python-build-standalone (packages and Python 3.12). Later runs need no network, except for publishing results.
- Git: the repository must be cloned. The benchmark installs the engine from the checkout next to it (`..`), so a copied `bench/` folder alone does not work. The publish tests in the self-test build temporary repositories and need git 2.28 or newer.
- Linux: Gmsh needs a few system libraries. On first run the script installs them with `apt-get` (`libglu1-mesa libxcursor1 libxft2 libxinerama1`) or `dnf`/`yum` (`mesa-libGLU libXcursor libXft libXinerama`), using `sudo` unless you are root. If there is no root, no `sudo` or an unknown package manager, it prints the exact command and stops.

Everything the script installs goes under `bench/.runtime/` (uv, Python, the virtual environment, the uv cache). Deleting that folder removes all of it. The scripts never touch the repository's own `.venv` or any system setting, apart from the Linux libraries above.

## Tutorial: first run

### Windows (10 or 11)

1. **Get the repository.** Install Git for Windows (https://git-scm.com/download/win) if `git --version` fails. The repository is private, so sign in when Git asks (a browser window opens). Then, in PowerShell:
   ```powershell
   git clone https://github.com/yusnimawl/srm-forge.git
   cd srm-forge
   ```
   Already cloned? `cd` into it and run `git pull`.
2. **Prepare the machine.** Plug in the charger, set Settings > System > Power > Power mode to "Best performance", close the browser and other heavy programs.
3. **Start it.** Double-click `bench\run.bat` in Explorer, or in the terminal:
   ```powershell
   bench\run.bat
   ```
   The first run downloads about 195 MB (uv, Python 3.12, the packages) into `bench\.runtime\`. That takes a few minutes; later runs start in seconds.
4. **Answer the questions.**
   - Machine label: a short name for this machine, for example `laptop-asus-i5`. Lowercase letters, digits and `-` only. It is remembered. The reference laptop must use `i7-13620h-laptop`.
   - Tier: `1` quick (minutes), `2` standard (about 15 min on the reference laptop), `3` long (hours). Start with quick.
   - If it warns about battery or a busy CPU, fix that and answer `N`, then run again.
5. **Wait.** Each step prints a timestamped line. Do not use the machine meanwhile.
6. **Read the summary** it prints at the end: single-solve time, recommended workers, projected map and search times, correctness. The result is saved in `bench\results\<label>\` and this README is rebuilt.
7. **Publish** (optional): answer `y` to "Commit and push results?". It commits only the result and this README and pushes them. It refuses if your branch has other unpushed commits.
8. **Finish:** "Delete the benchmark environment?" `y` frees about 0.7 GB (the next run downloads it again); `N` keeps it for faster reruns.
9. **See the comparison:** open `bench/README.md` on GitHub. The table and charts at the bottom show every machine that has published.

### Linux (Ubuntu, Debian, Fedora, WSL2, Proxmox, cloud)

1. **Get the repository.**
   ```sh
   sudo apt-get install -y git        # Fedora: sudo dnf install -y git
   git clone https://github.com/yusnimawl/srm-forge.git
   cd srm-forge
   ```
   The repository is private: use `gh auth login` (GitHub CLI) or a personal access token as the password when Git asks.
2. **Prepare the machine.** Laptops: plug in. Close heavy programs. On WSL, the Windows side must also be idle.
3. **Start it as your normal user** (not with `sudo`; the script asks for `sudo` itself only to install the Gmsh libraries the first time):
   ```sh
   sh bench/run.sh
   ```
   The first run downloads about 195 MB into `bench/.runtime/`.
4. **Answer the same questions** as on Windows (label, tier, warnings).
5. **Wait, read the summary, publish if you want, choose keep or delete** — the same as Windows steps 5 to 8.
6. **Headless or cloud machine** (no questions asked, nothing published):
   ```sh
   sh bench/run.sh --tier quick --label my-server --yes --keep --no-push
   ```
   Then commit the result yourself with `git add bench/results bench/README.md`, `git commit`, `git push`, or rerun later with `--push`.

### Running it again

- Rerun the same command; it skips the download. A new result file is added; the README shows each machine's latest run and lists the earlier ones in its details.
- After `git pull` on a machine that changed nothing locally, `bench/run.bat --report-only` (Windows) or `sh bench/run.sh --report-only` (Linux) rebuilds the comparison from everything published so far.

## How to run

Windows: double-click `bench\run.bat`, or in a terminal:

```powershell
bench\run.bat --tier quick
```

Linux, WSL, Proxmox, cloud:

```sh
./bench/run.sh --tier quick
```

Without `--tier`, a menu asks. Unattended (cloud, scripts), with no prompts, keeping the environment and not publishing:

```sh
./bench/run.sh --tier standard --label my-machine --yes --keep --no-push
```

Claude cloud sessions are Ubuntu 24.04 on 4 vCPU and 16 GB RAM, running as root. A command times out after 2 minutes by default, and a background command stops after 30 more minutes. Any tier can exceed the default, even `quick` on a first run (the setup downloads about 195 MB first). Set both `BASH_DEFAULT_TIMEOUT_MS` and `BASH_MAX_TIMEOUT_MS` in the cloud environment (for example `3600000`), or run the benchmark as a background command. `long` is still not advised there.

### Before you run

- The reference laptop must run with `--label i7-13620h-laptop` (the name in `bench/reference-machine.txt`). Under any other label the index columns and the index chart stay empty.
- Plug in the charger. Laptops throttle on battery.
- On Windows, set the power mode to "Best performance" (Settings, System, Power). The benchmark cannot read this setting reliably.
- Close heavy programs (browsers, sync clients, memory cleaners). The benchmark warns when other processes use more than 20 % of the CPU, and the numbers then are not representative.
- Leave the machine alone until it finishes.

### Tiers

Times are for the reference laptop (i7-13620H, 10 cores, 16 threads, 16 GB). Slower machines take longer.

| Tier | About | What it runs |
|---|---|---|
| `quick` | 3 min | meshes, single solves, correctness points, throughput at the physical and the logical core count |
| `standard` | 15 min | quick, plus throughput at 1, 2, 4, ... workers, an 8/6 `screening` map and a 5 minute sustained run |
| `long` | 2.2 h | standard with a 20 minute sustained run, plus the `full` maps of the 8/6 and the 12/8 with the overlap map and held-out checks |

### Flags

| Flag | Meaning |
|---|---|
| `--tier quick\|standard\|long` | what to run; without it a menu asks |
| `--label NAME` | machine label: lowercase letters, digits and `-`, up to 40 characters; without it you are asked once (the host name is the default) and the answer is remembered in `.runtime/label` |
| `--workers N` | cap the largest worker count (the default is capped by CPUs and RAM) |
| `--yes` | no prompts; the finish defaults to `--keep` and `--no-push` unless you give the flags |
| `--keep` / `--delete` / `--keep-full` | keep the environment, delete it, or keep it and also install the rest of the SRM design tool so `srmweb` runs from it (the web frontend build then needs Node: `cd web; npm ci; npm run build`) |
| `--push` / `--no-push` | commit and push the results, or not |
| `--report-only` | rebuild this README block and the charts from `results/` and exit |
| `--self-test` | run the benchmark's own unit tests and exit |

### Notes

- On Windows, if you press Ctrl+C, answer `N` to "Terminate batch job (Y/N)?". Then the finish step still runs. The interrupted run saves nothing.
- Publishing commits only `bench/results` and `bench/README.md`. It refuses to run when your branch has unpushed commits (push your own work first), and when any other local change would block `git pull --rebase`. Before pulling it restores `bench/README.md` and the charts from git, so do not hand-edit `bench/README.md` and publish in the same run: commit prose edits first.
- A failed correctness check does not stop the run. The result records it and the row is marked with a cross.

## How to read the results

- Full map chart: minutes to build a `full` 8/6 map, which is the wait you feel in the tool. Lower is better. Hatched bars are projected from the throughput, not measured.
- Scaling chart: solves per minute against workers. Where the line flattens, more workers stop helping. The recommended worker count is the smallest one that reaches 95 % of the best throughput, capped by RAM; use it for `SRMWEB_WORKERS`.
- Index chart: single-core and all-core speed relative to the reference machine (100). Higher is faster.
- `~` in the table marks a projected value. Search time (24 candidates) is a rough projection: the real search adds the stage-1 filter and the turns scan.
- A cross in the correctness column means the solver returned wrong numbers on that machine. Suspect RAM errors, an overclock or heat, and run again.
- Throttle is the sustained throughput in the last 20 % of the batches against the first 20 % (standard and long only). A large negative value means the machine slows down under load.
- Batch throughput includes starting the worker pool for every batch, which costs more on Windows, so Windows all-core figures are slightly pessimistic. The long tier's projection error (in the machine's details) shows how large this effect is. The all-core index uses the best measured throughput, so tiers compare.
- Only results with the current benchmark version are compared. Older ones are listed separately.

## Not measured

Temperature and GPU. There is no reliable cross-platform temperature reading without administrator rights, so the sustained run stands in for it.

<!-- srmbench:results:start -->
![Full 8/6 map time](results/charts/full_map.svg)

![Solves per minute against workers](results/charts/scaling.svg)

![Single-core and all-core index](results/charts/index.svg)

| Machine | CPU | Cores | RAM (GB) | OS | Tier | Single solve (s) | Workers | Screening map (min) | Full map (min) | Search of 24 (h) | RAM per worker (GB) | Throttle (%) | Correct | Index single/all |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [i7-13620h-laptop](#machine-i7-13620h-laptop) | 13th Gen Intel(R) Core(TM) i7-13620H | 10C/16T | 17 | Windows 11 | standard | 3.4 | 10 | 4.1 | ~36 | ~14 | 0.29 | +0.8 | ✓ | 100/100 |

`~` marks a projected value (a map not run, estimated from the batch throughput); the search is always projected. Correct: ✓ passed, ✗ failed, – not checked.

<details id="machine-i7-13620h-laptop">
<summary><b>i7-13620h-laptop</b> – 13th Gen Intel(R) Core(TM) i7-13620H, standard, 2026-10-15</summary>

- Machine: 13th Gen Intel(R) Core(TM) i7-13620H; 10 cores, 16 threads; 16.9 GB RAM; Windows 11 (10.0.26200, AMD64); Python 3.12.14
- Versions: engine commit 905a87b, gmsh 4.15.2, matplotlib 3.11.2, ngsolve 6.2.2608, numpy 2.5.4, psutil 7.2.2, scipy 1.18.1, srmcore 0.4.0; srmbench 1.0; lock 3e7c9e8c8462
- Run: 2026-10-15T17:11:06+07:00 to 2026-10-15T17:28:45+07:00, tier standard, status complete
- Result file: [2026-10-15T1711-standard.json](results/i7-13620h-laptop/2026-10-15T1711-standard.json)

**Mesh (8/6)**

| Preset | Seconds | Nodes | Grid points |
|---|---|---|---|
| screening | 7.39 | 42 935 | 360 |
| full | 10.91 | 81 984 | 1008 |

**Single solve (8/6)**

| Preset | Median (s) | Samples (s) |
|---|---|---|
| screening | 3.433 | 3.730, 3.433, 3.554, 3.317, 3.158 |
| full | 7.535 | 7.674, 7.403, 7.535 |

**Correctness points:** pass

**Batches**

| Workers | Points | Seconds | Solves per minute | Peak RAM per worker (GB) |
|---|---|---|---|---|
| 1 | 8 | 28.86 | 16.6 | – |
| 2 | 16 | 35.01 | 27.4 | 0.29 |
| 4 | 32 | 43.49 | 44.1 | 0.29 |
| 8 | 64 | 66.42 | 57.8 | 0.29 |
| 10 | 80 | 77.86 | 61.7 | 0.29 |
| 16 | 128 | 122.63 | 62.6 | 0.29 |

**Recommended workers:** 10 (uncapped choice 10, RAM cap 16)

**Screening map 8/6:** 244.0 s, 360 points, 10 workers, correctness pass; key numbers: aligned_angle 0, i_max 20, la 0.0328289, la_lu 9.16354, lu 0.00358256, peak_torque 12.4247, psi_max 0.320169, unaligned_angle 0.523599

**Sustained load:** 5 min at 10 workers, throttle +0.8 %; trace (time: solves per minute): 74 s: 64.7; 148 s: 64.7; 222 s: 65.0; 297 s: 64.5; 370 s: 65.2

**Scaling**

| Workers | Solves per minute | Speed-up over 1 worker(s) | Efficiency (%) |
|---|---|---|---|
| 1 | 16.6 | 1.00 | 100 |
| 2 | 27.4 | 1.65 | 82 |
| 4 | 44.1 | 2.65 | 66 |
| 8 | 57.8 | 3.48 | 43 |
| 10 | 61.7 | 3.71 | 37 |
| 16 | 62.6 | 3.77 | 24 |

</details>
<!-- srmbench:results:end -->
