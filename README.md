# srm-designer

Core engine (`srmcore`) of the SRM design tool. Spec: `docs/superpowers/specs/`.

## Dev setup

Requires Python 3.12+. Linux is the tested platform (CI runs on Linux only since 2026-11-13).

Linux:
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -m "not slow"
```
Linux needs `libglu1-mesa` for the gmsh wheel.

Windows (PowerShell) is not tested. It worked up to 2026-11-12:
```
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -m "not slow"
```

## Web UI

```
python -m pip install -e ".[dev,ngsolve,web]"
cd web && npm ci && npm run build && cd ..
srmweb          # http://127.0.0.1:8000
```

Binding to a non-loopback host needs `SRMWEB_TOKEN`. Frontend development: `cd web && npm run dev`.

## Licence

GPL-3.0-or-later. See `LICENSE`.
