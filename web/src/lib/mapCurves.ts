import type { MapArrays } from "@/api/types"
import { fromSI } from "./units"

/** A missing angle is NaN, which Plotly draws as a gap, not as 0°. */
const deg = (rad: number | null) => (rad == null ? NaN : fromSI(rad, "deg"))

/** One ψ(i) curve per map angle: mechanical degrees, ψ in mWb. */
export function psiCurves(map: MapArrays) {
  return map.angles.map((a, k) => ({
    angleDeg: deg(a),
    i: map.currents,
    psi_mWb: map.psi[k].map((p) => (p == null ? NaN : fromSI(p, "mWb"))),
  }))
}

/** Torque on the (angles x currents) grid, angles in mechanical degrees. */
export function torqueGrid(map: MapArrays) {
  return {
    angleDeg: map.angles.map(deg),
    i: map.currents,
    torque: map.torque.map((row) => row.map((t) => (t == null ? NaN : t))),
  }
}

/**
 * Up to `max` evenly spaced indices over the aligned -> unaligned half of the pitch, both ends included.
 * The second half mirrors the first for a symmetric machine, so it adds no new curves.
 */
export function pickAngles(angles: (number | null)[], unaligned: number | null, max = 6): number[] {
  const n = angles.length
  let u = Math.floor((n - 1) / 2)
  if (unaligned != null) {
    u = 0
    const dist = (k: number) => Math.abs((angles[k] ?? NaN) - unaligned)
    angles.forEach((_, k) => {
      if (dist(k) < dist(u)) u = k
    })
  }
  const count = Math.min(max, u + 1)
  if (count < 2) return [0]
  return [...new Set(Array.from({ length: count }, (_, k) => Math.round((k * u) / (count - 1))))]
}
