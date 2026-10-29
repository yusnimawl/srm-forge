"""Parsing of SRM_HIL_MODES (no SCons dependency)."""

SENSE = ("ad7606", "internal")
POSITION = ("encoder", "ad2s1210", "both")
DAC = ("mcp4922x2", "mcp4921x4")


def mode_macros(text):
    """Macros (NAME=1) for 'current_sense,position[,dac]'. Raises ValueError on an unknown value or a DAC without
    internal current sensing. An empty string gives no macros."""
    parts = [p for p in text.split(",")] if text else []
    if not parts:
        return []
    if not 2 <= len(parts) <= 3:
        raise ValueError(f"SRM_HIL_MODES {text!r}: expected current_sense,position[,dac]")
    sense, pos = parts[0], parts[1]
    dac = parts[2] if len(parts) == 3 else None
    for name, v, ok in (("current_sense", sense, SENSE), ("position", pos, POSITION)):
        if v not in ok:
            raise ValueError(f"SRM_HIL_MODES {text!r}: {name} {v!r} is not one of {', '.join(ok)}")
    if dac is not None and dac not in DAC:
        raise ValueError(f"SRM_HIL_MODES {text!r}: dac {dac!r} is not one of {', '.join(DAC)}")
    out = [f"HIL_CURRENT_SENSE_{sense.upper()}=1"]
    if pos in ("encoder", "both"):
        out.append("HIL_POSITION_ENCODER=1")
    if pos in ("ad2s1210", "both"):
        out.append("HIL_POSITION_AD2S1210=1")
    if sense == "internal":
        out.append(f"HIL_DAC_{(dac or DAC[0]).upper()}=1")
    return out
