export type FluxMap = {
  angles: number[] // rad
  currents: number[] // A
  psi: (number | null)[][] // [angle][current], Wb
  torque: (number | null)[][] // [angle][current], N·m
}

const deg = (rad: number) => (rad * 180) / Math.PI

/** One ψ(i) curve per map angle: mechanical degrees, ψ in mWb. */
export function psiCurves(map: FluxMap) {
  return map.angles.map((a, k) => ({
    angleDeg: deg(a),
    i: map.currents,
    psi_mWb: map.psi[k].map((p) => (p == null ? NaN : p * 1000)),
  }))
}

/** Torque on the (angles x currents) grid, angles in mechanical degrees. */
export function torqueGrid(map: FluxMap) {
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
export function pickAngles(angles: number[], unaligned: number | null, max = 6): number[] {
  const n = angles.length
  let u = Math.floor((n - 1) / 2)
  if (unaligned != null) {
    u = 0
    angles.forEach((a, k) => {
      if (Math.abs(a - unaligned) < Math.abs(angles[u] - unaligned)) u = k
    })
  }
  const count = Math.min(max, u + 1)
  if (count < 2) return [0]
  return [...new Set(Array.from({ length: count }, (_, k) => Math.round((k * u) / (count - 1))))]
}
