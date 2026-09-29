"""Public entry point: validated, quality-gated static mesh."""
from ..model.design import Design
from .machine import mesh_at_angle
from .quality import check_quality, quality_report
from .static import StaticMesh, build_static_mesh


def build_machine_mesh(design: Design) -> StaticMesh:
    static = build_static_mesh(design)
    for theta in (0.0, static.settings.band_pitch / 2):
        check_quality(quality_report(mesh_at_angle(static, theta, check=False)), static.settings)
    return static
