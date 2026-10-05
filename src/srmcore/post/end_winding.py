"""Analytic end-winding inductance of a concentrated pole coil (core spec §7.1 end-effect hook).

The 2D model holds the straight coil sides. The two end overhangs of a coil are straight bars of length
`span` with a `build × depth` bundle section, carrying opposite currents `separation` apart. Partial
inductances (Grover, Inductance Calculations, 1946; Ruehli, IBM J. Res. Dev. 16, 1972): each bar's self
inductance is the mutual inductance of two filaments at the geometric mean distance of the section from
itself, g = 0.2235·(build + depth) for a rectangle. The overhangs are perpendicular to the coil sides,
so they have no mutual inductance with them."""
import math

MU0 = 4e-7 * math.pi
GMD_RECTANGLE = 0.2235


def parallel_filament_mutual(length: float, distance: float) -> float:
    """Mutual inductance of two parallel, aligned filaments of equal `length` at `distance`, H."""
    root = math.hypot(length, distance)
    return MU0 / (2 * math.pi) * (length * math.log((length + root) / distance) - root + distance)


def end_turn_inductance(turns: int, span: float, build: float, depth: float, separation: float,
                        image_factor: float = 1.0) -> float:
    """End-winding inductance of one coil of `turns` turns, H. `image_factor` 1 is the coil in free air
    (lower bound), 2 a coil against an infinitely permeable end face (upper bound)."""
    if turns <= 0:
        raise ValueError(f"turns must be positive, got {turns}")
    for name, value in (("span", span), ("build", build), ("depth", depth), ("separation", separation)):
        if not value > 0:
            raise ValueError(f"{name} must be positive, got {value}")
    if not 1.0 <= image_factor <= 2.0:
        raise ValueError(f"image_factor must be in [1, 2], got {image_factor}")
    g = GMD_RECTANGLE * (build + depth)
    per_turn = 2 * (parallel_filament_mutual(span, g) - parallel_filament_mutual(span, separation))
    return image_factor * turns**2 * per_turn
