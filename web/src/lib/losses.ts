import type { components } from "@/api/schema"

export type LossesResult = components["schemas"]["LossesOut"]
export type OperatingLoss = components["schemas"]["OperatingLossOut"]

/** Efficiency in percent on the speed x torque-level grid: `z[torque level][speed]`, null where the point was not
 *  reached. The points are speed-major with the torque levels ascending. */
export function contourData(r: LossesResult): { x: number[]; y: number[]; z: (number | null)[][] } {
  const x = r.speeds_rpm.map((v) => v ?? NaN)
  const y = r.torque_fractions.map((v) => v ?? NaN)
  const z = y.map((_, j) =>
    x.map((_, i) => {
      const e = r.points[i * y.length + j]?.efficiency
      return e == null ? null : e * 100
    }),
  )
  return { x, y, z }
}

const IRON_PARTS = ["hysteresis", "classical", "excess"] as const

/** Loss components in W per operating point, with the total; unreached points are null in `totals` and 0 elsewhere.
 *  AC copper counts as 0 where it was not computed. */
export function splitBars(r: LossesResult): { series: { name: string; values: number[] }[]; totals: (number | null)[] } {
  const iron = (p: OperatingLoss, part: (typeof IRON_PARTS)[number]) =>
    Object.values(p.iron).reduce((s, reg) => s + (reg[part] ?? 0), 0)
  const rows = r.points.map((p) =>
    p.reached ? [p.copper_dc_w ?? 0, p.copper_ac_w ?? 0, ...IRON_PARTS.map((k) => iron(p, k))] : [0, 0, 0, 0, 0],
  )
  const names = ["Copper DC", "Copper AC", "Iron hysteresis", "Iron classical", "Iron excess"]
  return {
    series: names.map((name, c) => ({ name, values: rows.map((row) => row[c]) })),
    totals: r.points.map((p, k) => (p.reached ? rows[k].reduce((a, b) => a + b, 0) : null)),
  }
}

/** Index of the reached point with the highest efficiency, or -1 when none was reached. */
export function bestPoint(r: LossesResult): number {
  let best = -1
  r.points.forEach((p, k) => {
    if (p.reached && p.efficiency != null && (best < 0 || p.efficiency > (r.points[best].efficiency ?? -Infinity))) best = k
  })
  return best
}

/** Index of the highest-speed reached point at the top torque level, or -1 when there is none. */
export function ratedPoint(r: LossesResult): number {
  const nt = r.torque_fractions.length
  for (let i = r.speeds_rpm.length - 1; i >= 0; i--) {
    const k = i * nt + nt - 1
    if (r.points[k]?.reached) return k
  }
  return -1
}

export const pointLabel = (p: OperatingLoss) =>
  `${p.speed_rpm == null ? "?" : Math.round(p.speed_rpm)} rpm, ${p.torque_nm == null ? "?" : Number(p.torque_nm.toPrecision(3))} N·m`

/** A client position in metres in the machine frame of the outline SVG (millimetres, y down; the machine's y axis
 *  points up), for an svg of `viewBox` drawn centred in `box` at the largest size that fits. */
export function svgToMetres(
  box: { left: number; top: number; width: number; height: number },
  viewBox: [number, number, number, number],
  clientX: number,
  clientY: number,
): { x: number; y: number } {
  const [vx, vy, vw, vh] = viewBox
  const scale = Math.min(box.width / vw, box.height / vh)
  const offX = (box.width - vw * scale) / 2
  const offY = (box.height - vh * scale) / 2
  const sx = vx + (clientX - box.left - offX) / scale
  const sy = vy + (clientY - box.top - offY) / scale
  return { x: sx / 1000 + 0, y: -sy / 1000 + 0 }
}
