"""Outline -> Gmsh OCC surfaces with named regions. Call inside geometry.session.gmsh_model()."""
from dataclasses import dataclass

import gmsh
import numpy as np

from ..model.design import RadialSRMParams
from ..topology.primitives import Line, Point, Segment, sample_segment
from ..topology.radial import RadialOutline, build_outline

STATOR_REGIONS = ("stator_iron", "slot_air", "airgap_stator")
ROTOR_REGIONS = ("rotor_iron", "shaft", "airgap_rotor")


@dataclass(frozen=True)
class GeometryModel:
    region_surfaces: dict[str, tuple[int, ...]]
    region_part: dict[str, str]
    region_size_key: dict[str, str]
    stator_outer_curve: int
    band_outer_curve: int
    band_inner_curve: int
    band_inner_radius: float
    band_outer_radius: float
    refinement_points: dict[str, np.ndarray]


class _Points:
    def __init__(self) -> None:
        self._tags: dict[tuple[float, float], int] = {}

    def get(self, q: Point) -> int:
        key = (round(q[0], 12), round(q[1], 12))
        if key not in self._tags:
            self._tags[key] = gmsh.model.occ.addPoint(q[0], q[1], 0.0)
        return self._tags[key]


def _curves(segments: tuple[Segment, ...], points: _Points, centres: list[int]) -> list[int]:
    occ = gmsh.model.occ
    curves = []
    for s in segments:
        a, b = points.get(s.start), points.get(s.end)
        if isinstance(s, Line):
            curves.append(occ.addLine(a, b))
        else:
            c = occ.addPoint(s.center[0], s.center[1], 0.0)
            centres.append(c)
            curves.append(occ.addCircleArc(a, c, b))
    return curves


def _full_circle_on_boundary(surfaces: tuple[int, ...], radius: float, tol: float) -> int:
    boundary = gmsh.model.getBoundary([(2, s) for s in surfaces], combined=False, oriented=False)
    for _, tag in boundary:
        xmin, ymin, _, xmax, ymax, _ = gmsh.model.getBoundingBox(1, abs(tag))
        if all(abs(v - w) < tol for v, w in ((xmax, radius), (xmin, -radius), (ymax, radius), (ymin, -radius))):
            return abs(tag)
    raise RuntimeError(f"no full circle of radius {radius} on the boundary")


def _size_key(region: str) -> str:
    if region.startswith("coil_"):
        return "coil"
    if region.startswith("airgap_"):
        return "airgap"
    return region


def _disk(radius: float) -> int:
    """A plane disk of the given radius, bounded by a true Circle curve.

    occ.addDisk's boundary is type "Ellipse" (an OCC quirk: equal-axis conic,
    not a Circle) even before any boolean op, and that quirk survives cut/fragment.
    Building the disk from occ.addCircle instead keeps the boundary a real Circle,
    which later boolean results (and getType/getBoundingBox checks) rely on.
    """
    occ = gmsh.model.occ
    loop = occ.addCurveLoop([occ.addCircle(0, 0, 0, radius)])
    return occ.addPlaneSurface([loop])


def build_geometry(outline: RadialOutline, feature_step: float) -> GeometryModel:
    occ = gmsh.model.occ
    points = _Points()
    centres: list[int] = []

    # stator part
    outer_loop = occ.addCurveLoop([occ.addCircle(0, 0, 0, outline.stator_outer_radius)])
    bore_curves = _curves(outline.stator_inner_boundary, points, centres)
    stator_iron = occ.addPlaneSurface([outer_loop, occ.addCurveLoop(bore_curves)])
    inside_bore = occ.addPlaneSurface([occ.addCurveLoop(bore_curves)])
    coils = [(c.name, occ.addPlaneSurface([occ.addCurveLoop(_curves(c.boundary, points, centres))]))
             for c in outline.coil_sides]
    bore_disk = _disk(outline.bore_radius)
    band_out_disk = _disk(outline.band_outer_radius)
    slot_air, _ = occ.cut([(2, inside_bore)], [(2, bore_disk)] + [(2, t) for _, t in coils],
                          removeObject=True, removeTool=False)
    gap_stator, _ = occ.cut([(2, bore_disk)], [(2, band_out_disk)])

    # rotor part
    rotor_area = occ.addPlaneSurface([occ.addCurveLoop(_curves(outline.rotor_outer_boundary, points, centres))])
    shaft = _disk(outline.shaft_radius)
    band_in_disk = _disk(outline.band_inner_radius)
    gap_rotor, _ = occ.cut([(2, band_in_disk)], [(2, rotor_area)], removeObject=True, removeTool=False)
    rotor_iron, _ = occ.cut([(2, rotor_area)], [(2, shaft)], removeObject=True, removeTool=False)

    occ.remove([(0, c) for c in centres])

    named: list[tuple[str, list[tuple[int, int]]]] = (
        [("stator_iron", [(2, stator_iron)]), ("slot_air", slot_air), ("airgap_stator", gap_stator)]
        + [(name, [(2, tag)]) for name, tag in coils]
        + [("rotor_iron", rotor_iron), ("shaft", [(2, shaft)]), ("airgap_rotor", gap_rotor)]
    )
    objects = [dt for _, dts in named for dt in dts]
    _, out_map = occ.fragment(objects, [])
    occ.synchronize()

    region_surfaces: dict[str, tuple[int, ...]] = {}
    index = 0
    for name, dts in named:
        tags: list[int] = []
        for _ in dts:
            tags.extend(t for d, t in out_map[index] if d == 2)
            index += 1
        region_surfaces[name] = tuple(sorted(set(tags)))
    all_tags = [t for tags in region_surfaces.values() for t in tags]
    if len(all_tags) != len(set(all_tags)):
        raise RuntimeError("a surface was assigned to two regions")

    region_part = {n: ("rotor" if n in ROTOR_REGIONS else "stator") for n in region_surfaces}
    tol = (outline.band_outer_radius - outline.band_inner_radius) / 4
    stator_outer = _full_circle_on_boundary(region_surfaces["stator_iron"], outline.stator_outer_radius, tol)
    band_outer = _full_circle_on_boundary(region_surfaces["airgap_stator"], outline.band_outer_radius, tol)
    band_inner = _full_circle_on_boundary(region_surfaces["airgap_rotor"], outline.band_inner_radius, tol)

    for name, tags in region_surfaces.items():
        gmsh.model.addPhysicalGroup(2, list(tags), name=name)
    gmsh.model.addPhysicalGroup(1, [stator_outer], name="stator_outer")
    gmsh.model.addPhysicalGroup(1, [band_outer], name="band_outer")
    gmsh.model.addPhysicalGroup(1, [band_inner], name="band_inner")

    refinement_points = {}
    for tag, features in outline.refinement_features.items():
        pts: list[Point] = []
        for f in features:
            pts.extend(sample_segment(f, feature_step) if not isinstance(f, tuple) else [f])
        refinement_points[tag] = np.asarray(pts, dtype=float).reshape(-1, 2)

    return GeometryModel(
        region_surfaces=region_surfaces, region_part=region_part,
        region_size_key={n: _size_key(n) for n in region_surfaces},
        stator_outer_curve=stator_outer, band_outer_curve=band_outer, band_inner_curve=band_inner,
        band_inner_radius=outline.band_inner_radius, band_outer_radius=outline.band_outer_radius,
        refinement_points=refinement_points,
    )


def build_machine_geometry(p: RadialSRMParams, feature_step: float) -> GeometryModel:
    return build_geometry(build_outline(p), feature_step)
