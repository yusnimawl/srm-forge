"""PNG plot of a machine mesh, coloured by region (backend-independent: no pyplot)."""
from pathlib import Path

from matplotlib.figure import Figure

from .machine import MachineMesh


def plot_mesh(mesh: MachineMesh, path: str | Path, title: str | None = None) -> Path:
    path = Path(path)
    fig = Figure(figsize=(8, 8))
    ax = fig.add_subplot()
    ax.tripcolor(mesh.nodes[:, 0], mesh.nodes[:, 1], mesh.triangles, facecolors=mesh.region_ids,
                 edgecolors="k", linewidth=0.05, cmap="tab20")
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(title or f"rotor angle {mesh.rotor_angle:.4f} rad, {len(mesh.triangles)} triangles")
    fig.savefig(path, dpi=200)
    return path
