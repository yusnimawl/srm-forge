import type { components } from "@/api/schema"
import { fmt } from "./format"

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

const REGION_ORDER = ["stator_pole", "stator_yoke", "rotor_pole", "rotor_yoke"]

export type LossSeries = { name: string; values: (number | null)[]; hover?: string[] }

/** Loss components in W per operating point: copper DC, copper AC (0 where it was not computed) and the iron loss of
 *  each region, whose `hover` text gives its hysteresis, classical and excess parts. Unreached points are null in
 *  every series and in `totals`. */
export function splitBars(r: LossesResult): { series: LossSeries[]; totals: (number | null)[] } {
  const seen = new Set(r.points.flatMap((p) => Object.keys(p.iron)))
  const regions = [...REGION_ORDER.filter((k) => seen.has(k)), ...[...seen].filter((k) => !REGION_ORDER.includes(k))]
  const w = (v: number | null | undefined) => (v == null ? 0 : v)
  const per = (f: (p: OperatingLoss) => number) => r.points.map((p) => (p.reached ? f(p) : null))
  const series: LossSeries[] = [
    { name: "Copper DC", values: per((p) => w(p.copper_dc_w)) },
    { name: "Copper AC", values: per((p) => w(p.copper_ac_w)) },
    ...regions.map((k) => ({
      name: `Iron ${k.replaceAll("_", " ")}`,
      values: per((p) => {
        const l = p.iron[k]
        return l ? w(l.hysteresis) + w(l.classical) + w(l.excess) : 0
      }),
      hover: r.points.map((p) => {
        const l = p.iron[k]
        return p.reached && l ? `hysteresis ${fmt(l.hysteresis, 3)} W, classical ${fmt(l.classical, 3)} W, excess ${fmt(l.excess, 3)} W` : ""
      }),
    })),
  ]
  return { series, totals: r.points.map((p, k) => (p.reached ? series.reduce((sum, c) => sum + w(c.values[k]), 0) : null)) }
}

/** The two losses numbers of a result: best efficiency, and total loss at the rated point. Null where no point
 *  qualifies. */
export function lossKeyNumbers(r: LossesResult): {
  best: { efficiency: number; label: string } | null
  rated: { totalW: number; label: string } | null
} {
  const best = bestPoint(r)
  const rated = ratedPoint(r)
  const total = rated >= 0 ? splitBars(r).totals[rated] : null
  return {
    best: best >= 0 ? { efficiency: r.points[best].efficiency ?? NaN, label: pointLabel(r.points[best]) } : null,
    rated: rated >= 0 && total != null ? { totalW: total, label: pointLabel(r.points[rated]) } : null,
  }
}

/** The top reached torque level per speed, as the contour's envelope edge: points at reached speeds only. */
export function envelopeEdge(r: LossesResult): { x: number[]; y: number[] } {
  const nt = r.torque_fractions.length
  const x: number[] = []
  const y: number[] = []
  r.speeds_rpm.forEach((s, i) => {
    for (let j = nt - 1; j >= 0; j--) {
      if (r.points[i * nt + j]?.reached) {
        x.push(s ?? NaN)
        y.push(r.torque_fractions[j] ?? NaN)
        break
      }
    }
  })
  return { x, y }
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
