import type { Evaluation } from "@/api/types"
import { LINE_COLORS, type Num, type Trace } from "./analysis"
import { fromSI } from "./units"

export interface WaveformSeries {
  current: Trace[]
  psi: Trace[]
  voltage: Trace[]
  torque: Trace[]
  line: Trace[]
  /** Stroke psi (mWb) against i (A), with the aligned and unaligned curves from the origin. */
  loop: Trace[]
}

const tr = (name: string, x: Num[], y: Num[], color: string, dash = "solid"): Trace => ({
  type: "scatter",
  mode: "lines",
  name,
  x,
  y,
  line: { color, dash, width: 2 },
  connectgaps: false,
})

/** One speed's waveforms in UI units, or null for an evaluation without them. */
export function waveformSeries(ev: Evaluation, speed: number): WaveformSeries | null {
  const w = ev.envelope?.waveforms
  if (!w) return null
  const x = w.theta_el
  const one = (name: string, rows: Num[][], scale = 1) =>
    [tr(name, x, rows[speed].map((v) => (v == null ? null : v * scale)), LINE_COLORS[0])]
  const i = w.current[speed]
  const psi = w.psi[speed].map((v) => (v == null ? null : fromSI(v, "mWb")))
  const c = ev.curves
  // psi = L(i) * i at every map current, starting from the origin.
  const ray = (name: string, l: Num[] | undefined, color: string, dash: string) => {
    const cur = c?.currents ?? []
    return tr(name, [0, ...cur], [0, ...cur.map((a, k) => (a == null || l?.[k] == null ? null : fromSI(l[k]! * a, "mWb")))], color, dash)
  }
  return {
    current: one("Phase current", w.current),
    psi: [tr("Flux linkage", x, psi, LINE_COLORS[0])],
    voltage: one("Phase voltage", w.voltage),
    torque: one("Phase torque", w.torque),
    line: one("Line current", w.line),
    loop: [tr("stroke", i, psi, LINE_COLORS[0]), ray("aligned", c?.la_sat, LINE_COLORS[1], "dash"), ray("unaligned", c?.lu, LINE_COLORS[2], "dot")],
  }
}

/** The speed nearest `baseSpeedRpm`, else the one with the largest power. */
export function defaultSpeedIndex(ev: Evaluation, baseSpeedRpm?: number): number {
  const e = ev.envelope
  if (!e) return 0
  const sp = e.speeds_rpm.map((v) => v ?? NaN)
  const pw = e.power.map((v) => v ?? -Infinity)
  const score = (k: number) => (baseSpeedRpm != null ? Math.abs(sp[k] - baseSpeedRpm) : -pw[k])
  // NaN scores never win the comparison, so a null speed is skipped unless every one is null.
  return sp.reduce((b, _, k) => (score(k) < score(b) || Number.isNaN(score(b)) ? k : b), 0)
}
