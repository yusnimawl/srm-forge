/** A rectangle in the glyph's 100 x 100 viewBox (centred at 0), rotated by `angle` degrees about the origin. */
export type Rect = { x: number; y: number; width: number; height: number; angle: number }

export const STATOR_RING_R = 44
export const STATOR_RING_STROKE = 8
export const SHAFT_R = 17
export const SHAFT_HOLE_R = 5

const STATOR_POLE = { r0: 26, r1: 41, halfWidth: 3.5 }
const ROTOR_POLE = { r0: 0, r1: 24, halfWidth: 4.5 }

function poles(n: number, { r0, r1, halfWidth }: typeof STATOR_POLE, scale: number): Rect[] {
  return Array.from({ length: n }, (_, k) => ({
    x: r0,
    y: -halfWidth * scale,
    width: r1 - r0,
    height: 2 * halfWidth * scale,
    angle: (k * 360) / n,
  }))
}

/** Pole rectangles of an Ns/Nr radial machine; `poleScale` scales the pole widths (0 collapses the poles). */
export function srmGlyph(ns: number, nr: number, poleScale = 1): { stator: Rect[]; rotor: Rect[] } {
  return { stator: poles(ns, STATOR_POLE, poleScale), rotor: poles(nr, ROTOR_POLE, poleScale) }
}

export const SET_SECONDS = 2.4
export const MORPH_SECONDS = 0.2
export const STATOR_DEG_PER_S = 30
export const ROTOR_DEG_PER_S = -80
const POLE_SETS: [number, number][] = [
  [6, 4],
  [8, 6],
  [12, 8],
]

export type SpinnerFrame = { statorAngle: number; rotorAngle: number; poles: [number, number]; scale: number }

/** The spinner's state t seconds after it started. */
export function spinnerFrame(t: number): SpinnerFrame {
  const i = Math.floor(t / SET_SECONDS)
  const u = t - i * SET_SECONDS
  const scale = Math.max(0, Math.min(1, u / MORPH_SECONDS, (SET_SECONDS - u) / MORPH_SECONDS))
  return {
    statorAngle: STATOR_DEG_PER_S * t,
    rotorAngle: ROTOR_DEG_PER_S * t,
    poles: POLE_SETS[i % POLE_SETS.length],
    scale,
  }
}
