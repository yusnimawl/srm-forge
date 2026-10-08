import type { Evaluation, MapArrays, MapCurves } from "@/api/types"
import { fmt } from "./format"
import { fromSI } from "./units"

export type Num = number | null

export interface Trace {
  type: "scatter"
  mode: "lines" | "lines+markers"
  name: string
  x: Num[]
  y: Num[]
  line: { color: string; dash: string; width: number }
  marker?: { symbol: string; size: number }
  yaxis?: "y2"
  /** Per-point hover lines, shown through `hovertemplate`. */
  text?: string[]
  hovertemplate?: string
  connectgaps: false
}

/** Another case drawn on the same axes; `label` names it in the legend. */
export interface Overlay {
  label: string
  evaluation: Evaluation
}

export const MAX_OVERLAYS = 6
/** Okabe-Ito colours, colour-blind safe. */
export const LINE_COLORS = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9", "#8c8c8c"]
export const LINE_DASHES = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]
/** Case n gets its own colour and a dash from this cycle, so cases stay apart without colour. */
const CASE_DASHES = ["solid", "dash", "dot"]

const caseLine = (n: number) => ({ color: LINE_COLORS[n % LINE_COLORS.length], dash: CASE_DASHES[n % CASE_DASHES.length], width: 2 })

const conv = (values: Num[], unit: Parameters<typeof fromSI>[1]): Num[] => values.map((v) => (v == null ? null : fromSI(v, unit)))

function trace(name: string, x: Num[], y: Num[], line: Trace["line"], extra: Partial<Trace> = {}): Trace {
  return { type: "scatter", mode: "lines", name, x, y, line, connectgaps: false, ...extra }
}

export const MAIN_LABEL = "this case"

export interface PerformanceSeries {
  torque: Trace[]
  power: Trace[]
  efficiency: Trace[]
  current: Trace[]
}

/** Envelope traces against speed in UI units; the main case first, then up to `MAX_OVERLAYS` overlays. */
export function performanceSeries(ev: Evaluation, overlays: Overlay[] = [], mainLabel = MAIN_LABEL): PerformanceSeries {
  const out: PerformanceSeries = { torque: [], power: [], efficiency: [], current: [] }
  const cases = [{ label: mainLabel, evaluation: ev }, ...overlays.slice(0, MAX_OVERLAYS)]
  cases.forEach(({ label, evaluation }, n) => {
    const e = evaluation.envelope
    if (!e) return
    const line = caseLine(n)
    // The envelope's switching angles are already electrical degrees from the unaligned position.
    const text = e.speeds_rpm.map((_, k) => `turn-on ${fmt(e.theta_on_el[k])}° el, turn-off ${fmt(e.theta_off_el[k])}° el`)
    const hover = { mode: "lines+markers" as const, marker: { symbol: "circle", size: 5 }, text, hovertemplate: `%{x:.0f} rpm, ${label} %{y:.4g}<br>%{text}<extra></extra>` }
    out.torque.push(trace(label, e.speeds_rpm, e.torque, line, hover))
    out.power.push(trace(label, e.speeds_rpm, conv(e.power, "kW"), line, hover))
    out.efficiency.push(trace(label, e.speeds_rpm, conv(e.efficiency, "%"), line, hover))
    out.current.push(trace(label, e.speeds_rpm, e.i_rms, line, hover))
  })
  return out
}

/** Up to `max` evenly spaced indices of the nonzero currents, the largest included. */
function pickCurrents(currents: Num[], max = 6): number[] {
  const nonzero = currents.map((_, k) => k).filter((k) => (currents[k] ?? 0) > 0)
  const idx = nonzero.length ? nonzero : currents.map((_, k) => k)
  const count = Math.min(max, idx.length)
  return Array.from({ length: count }, (_, k) => idx[Math.round(((k + 1) * idx.length) / count) - 1])
}

const column = (grid: Num[][], j: number): Num[] => grid.map((row) => row[j])
const angleDeg = (angles: Num[]): Num[] => conv(angles, "deg")
const currentLine = (n: number) => ({ color: LINE_COLORS[n % LINE_COLORS.length], dash: LINE_DASHES[n % LINE_DASHES.length], width: 2 })

/** T against mechanical angle (degrees), one trace per picked current. */
export function torqueCurves(map: MapArrays): Trace[] {
  const x = angleDeg(map.angles)
  return pickCurrents(map.currents).map((j, n) => trace(`${fmt(map.currents[j])} A`, x, column(map.torque, j), currentLine(n)))
}

/** L (mH) against mechanical angle (degrees), one trace per picked current. */
export function inductanceCurves(curves: MapCurves, angles: Num[]): Trace[] {
  const x = angleDeg(angles)
  return pickCurrents(curves.currents).map((j, n) =>
    trace(`${fmt(curves.currents[j])} A`, x, conv(column(curves.inductance, j), "mH"), currentLine(n)),
  )
}

export interface DesignFactorTraces {
  /** La_sat, Lu and La_unsat (mH) against current. */
  inductance: Trace[]
  /** k2 on the left axis; B_sp and B_sp·k2 (T) on `y2`. */
  factors: Trace[]
  /** B_sp·k2 (T) against La_sat/Lu. */
  bspK2VsRatio: Trace[]
}

/** Design-factor traces for the given cases; a case without curves is skipped. */
export function designFactorTraces(cases: { label: string; curves: MapCurves | null | undefined }[]): DesignFactorTraces {
  const out: DesignFactorTraces = { inductance: [], factors: [], bspK2VsRatio: [] }
  const multi = cases.length > 1
  cases.slice(0, 1 + MAX_OVERLAYS).forEach(({ label, curves: c }, n) => {
    if (!c) return
    const line = caseLine(n)
    const name = (q: string) => (multi ? `${label} ${q}` : q)
    const sym = (symbol: string) => ({ mode: "lines+markers" as const, marker: { symbol, size: 6 } })
    const x = c.currents
    const unsat: Num[] = x.map(() => (c.la_unsat == null ? null : fromSI(c.la_unsat, "mH")))
    out.inductance.push(
      trace(name("La_sat"), x, conv(c.la_sat, "mH"), line, sym("circle")),
      trace(name("Lu"), x, conv(c.lu, "mH"), line, sym("square")),
      trace(name("La_unsat"), x, unsat, line),
    )
    out.factors.push(
      trace(name("k2"), x, c.k2, line, sym("circle")),
      trace(name("B_sp"), x, c.b_sp, line, { ...sym("triangle-up"), yaxis: "y2" }),
      trace(name("B_sp·k2"), x, c.b_sp_k2, line, { ...sym("square"), yaxis: "y2" }),
    )
    out.bspK2VsRatio.push(trace(label, c.la_lu, c.b_sp_k2, line, sym("circle")))
  })
  return out
}
