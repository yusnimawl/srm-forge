"""Winding wire described by its dimensions (v0a-2 spec §3.1). Sizes in metres. `copper_area` is the copper
cross-section of one conductor; `outer_area` includes the insulation and is what the slot fill counts."""
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A wire size above this looks like millimetres typed as metres.
_MAX_SIZE = 0.02   # m


class _Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def _metres(self):
        for name, value in self:
            if isinstance(value, float) and value > _MAX_SIZE:
                raise ValueError(f"{name}={value} looks like millimetres; wire sizes are in metres")
        return self


class RoundWire(_Wire):
    kind: Literal["round"] = "round"
    diameter: float = Field(gt=0)          # bare copper
    outer_diameter: float = Field(gt=0)    # over the insulation

    @model_validator(mode="after")
    def _insulated(self):
        if self.outer_diameter < self.diameter:
            raise ValueError("outer_diameter must not be below the bare diameter")
        return self

    @property
    def copper_area(self) -> float:
        return math.pi * self.diameter**2 / 4

    @property
    def outer_area(self) -> float:
        return math.pi * self.outer_diameter**2 / 4


class RectangularWire(_Wire):
    """Corner radius ignored."""
    kind: Literal["rectangular"] = "rectangular"
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    insulation: float = Field(ge=0)        # thickness on each side

    @property
    def copper_area(self) -> float:
        return self.width * self.height

    @property
    def outer_area(self) -> float:
        return (self.width + 2 * self.insulation) * (self.height + 2 * self.insulation)


class LitzWire(_Wire):
    """Litz or other multistrand conductor: `strands` round strands in a round bundle."""
    kind: Literal["litz"] = "litz"
    strand_diameter: float = Field(gt=0)
    strands: int = Field(ge=1)
    outer_diameter: float = Field(gt=0)    # bundle, over the serving or insulation

    @model_validator(mode="after")
    def _holds_strands(self):
        if self.outer_area < self.copper_area:
            raise ValueError("outer_diameter is too small to hold the strands")
        return self

    @property
    def copper_area(self) -> float:
        return self.strands * math.pi * self.strand_diameter**2 / 4

    @property
    def outer_area(self) -> float:
        return math.pi * self.outer_diameter**2 / 4


Wire = Annotated[RoundWire | RectangularWire | LitzWire, Field(discriminator="kind")]
