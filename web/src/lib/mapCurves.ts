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

/** Up to `max` evenly spaced angle indices, always the first (aligned) and the one nearest `unaligned`. */
export function pickAngles(angles: number[], unaligned: number | null, max = 6): number[] {
  const n = angles.length
  if (n <= max) return angles.map((_, k) => k)
  const idx = new Set(Array.from({ length: max }, (_, k) => Math.round((k * (n - 1)) / (max - 1))))
  if (unaligned != null) {
    let u = 0
    angles.forEach((a, k) => {
      if (Math.abs(a - unaligned) < Math.abs(angles[u] - unaligned)) u = k
    })
    if (!idx.has(u)) {
      let drop = -1
      for (const k of idx) if (k !== 0 && (drop < 0 || Math.abs(k - u) < Math.abs(drop - u))) drop = k
      idx.delete(drop)
      idx.add(u)
    }
  }
  return [...idx].sort((a, b) => a - b)
}
