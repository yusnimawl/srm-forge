import { LINE_COLORS, type Trace } from "./analysis"
import { electricalDeg } from "./fieldView"
import type { FieldFrameData } from "./fieldWire"

export const SPEEDS = [0.5, 1, 2]

/** The frame after `index`, wrapping to 0. */
export const nextFrame = (index: number, count: number): number => (index + 1) % count

/** Milliseconds per frame; 1x is 100 ms. */
export const frameInterval = (speed: number): number => 100 / speed

const ZONES: [string, string][] = [
  ["stator_pole", "stator pole"],
  ["stator_yoke", "stator yoke"],
  ["rotor_pole", "rotor pole"],
]

/** |B| (T) of the three probe zones against electrical degrees. */
export function probeSeries(frames: FieldFrameData[], nRotorPoles: number): Trace[] {
  const x = frames.map((f) => electricalDeg(f.angle, nRotorPoles))
  return ZONES.map(([key, name], k) => ({
    type: "scatter",
    mode: "lines",
    name,
    x,
    y: frames.map((f) => f.probes[key] ?? null),
    line: { color: LINE_COLORS[k], dash: "solid", width: 2 },
    connectgaps: false,
  }))
}
