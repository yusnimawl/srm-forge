"""Conversions between imported iron loops (model layer) and outline segments (topology layer)."""
from ..model.design import RadialSRMParams
from ..model.iron import ImportedIron, IronArc, IronLine, IronLoop
from .primitives import Arc, Line, Segment


def to_segments(loop: IronLoop) -> tuple[Segment, ...]:
    return tuple(Line(s.start, s.end) if isinstance(s, IronLine) else Arc(s.start, s.end, s.center) for s in loop)


def from_segments(segs: tuple[Segment, ...]) -> IronLoop:
    return tuple(IronLine(start=s.start, end=s.end) if isinstance(s, Line)
                 else IronArc(start=s.start, end=s.end, center=s.center) for s in segs)


def parametric_iron(p: RadialSRMParams) -> ImportedIron:
    """The contours of the parametric machine (ignoring `p.iron`): stator outer circle and shaft circle as
    four quarter arcs from angle 0, the salient stator bore and rotor outer outlines, and no holes."""
    from .radial import _full_circle, parametric_outline  # radial imports this module

    o = parametric_outline(p)
    return ImportedIron(
        stator_outer=from_segments(_full_circle(p.stator_outer_radius, "")),
        stator_bore=from_segments(o.stator_inner_boundary),
        rotor_outer=from_segments(o.rotor_outer_boundary),
        rotor_bore=from_segments(_full_circle(p.shaft_radius, "")),
    )
