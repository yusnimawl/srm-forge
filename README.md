# srm-designer

Core engine (`srmcore`) of the SRM design tool. Spec: `docs/superpowers/specs/`.

## Dev setup

Requires Python 3.12+.

Windows (PowerShell):
```
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -m "not slow"
```

Linux:
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -m "not slow"
```
Linux needs `libglu1-mesa` for the gmsh wheel.
