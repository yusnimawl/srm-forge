"""Physical constants shared by all layers."""
import math

# Exact pre-2019 value, as used by FEMM; keeps the M5 cross-tool comparison free of a 1e-10 offset.
MU0 = 4e-7 * math.pi
