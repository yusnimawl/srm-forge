"""Imported lamination contours: closed loops of lines and minor arcs, in metres."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Pt = tuple[float, float]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IronLine(_Frozen):
    kind: Literal["line"] = "line"
    start: Pt
    end: Pt


class IronArc(_Frozen):
    """Minor arc (< pi) from start to end around center."""
    kind: Literal["arc"] = "arc"
    start: Pt
    end: Pt
    center: Pt


IronSegment = Annotated[IronLine | IronArc, Field(discriminator="kind")]
IronLoop = tuple[IronSegment, ...]


class ImportedIron(_Frozen):
    stator_outer: IronLoop
    stator_bore: IronLoop
    stator_holes: tuple[IronLoop, ...] = ()
    rotor_outer: IronLoop
    rotor_bore: IronLoop
    rotor_holes: tuple[IronLoop, ...] = ()
