import type { Data } from "plotly.js-dist-min"
import type { Evaluation } from "@/api/types"
import { LINE_COLORS } from "@/lib/analysis"
import { fmt } from "@/lib/format"

export type Rating = NonNullable<Evaluation["rating"]>
export type ThermalSummary = NonNullable<Evaluation["thermal_summary"]>
export type ShareRow = ThermalSummary["shares"][number]["rows"][number]

export type TabState = "unrated" | "summary-only" | "check-only" | "full"

/** Which parts of the tab an evaluation can fill: a pre-R5d rating has no stress block, a failed search candidate only a check. */
export function tabState(ev: Evaluation): TabState {
  if (ev.rating) return ev.rating.stress != null ? "full" : "summary-only"
  return ev.thermal_check ? "check-only" : "unrated"
}

const finite = (v: number | null | undefined): v is number => v != null && Number.isFinite(v)

/** Continuous and peak torque against speed: nominal and rated lines with the band between them, requirement dashed. */
export function curveSpec(rating: Rating, summary: ThermalSummary | null | undefined): Data[] {
  const x = rating.speeds.map((s) => s.rpm)
  const line = (name: string, y: (number | null)[], color: string, extra: object = {}) =>
    ({ type: "scatter", mode: "lines+markers", name, x, y, line: { color, width: 2 }, marker: { size: 5 }, ...extra }) as Data
  const need = (key: "need_continuous_nm" | "need_peak_nm", name: string, color: string): Data[] => {
    const pts = (summary?.speeds ?? []).filter((s) => finite(s[key]))
    return pts.length === 0 ? [] : [{
      type: "scatter", mode: "lines", name, x: pts.map((s) => s.rpm), y: pts.map((s) => s[key]),
      line: { color, width: 1.5, dash: "dash" },
    } as Data]
  }
  const band = { fill: "tonexty", fillcolor: "rgba(237,237,237,0.10)" }
  return [
    line("Continuous, rated", rating.speeds.map((s) => s.rated_continuous_nm), LINE_COLORS[0]),
    line("Continuous, nominal", rating.speeds.map((s) => s.nominal_continuous_nm), LINE_COLORS[0], { ...band, line: { color: LINE_COLORS[0], width: 1, dash: "dot" } }),
    line("Peak, rated", rating.speeds.map((s) => s.rated_peak_nm), LINE_COLORS[1]),
    line("Peak, nominal", rating.speeds.map((s) => s.nominal_peak_nm), LINE_COLORS[1], { ...band, fillcolor: "rgba(232,176,74,0.12)", line: { color: LINE_COLORS[1], width: 1, dash: "dot" } }),
    ...need("need_continuous_nm", "Required continuous", LINE_COLORS[2]),
    ...need("need_peak_nm", "Required peak", LINE_COLORS[3]),
  ]
}

/** Horizontal bars, largest on top; a runaway bar is drawn at 1.2 x the largest finite value and labelled. */
export function tornadoSpec(rows: ShareRow[]): Data[] {
  const finiteMax = Math.max(0, ...rows.filter((r) => !r.runaway && finite(r.k)).map((r) => r.k as number))
  const cap = (finiteMax || 1) * 1.2
  const shown = rows.filter((r) => r.runaway || (finite(r.k) && (r.k as number) > 0))
  const v = (r: ShareRow) => (r.runaway ? cap : (r.k as number))
  return [{
    type: "bar", orientation: "h",
    y: shown.map((r) => r.label), x: shown.map(v),
    text: shown.map((r) => (r.runaway ? "runaway" : `${(r.k as number).toFixed(1)} K`)),
    textposition: "outside", cliponaxis: false, hoverinfo: "text+y",
    marker: { color: shown.map((r) => (r.runaway ? LINE_COLORS[4] : LINE_COLORS[1])) },
  } as Data]
}

type Check = NonNullable<Evaluation["thermal_check"]>
type Cooling = NonNullable<Rating["cooling"]>

/** Speeds that held before the failing one. The check stores hot spots per speed, not the speeds themselves. */
export function passedSpeeds(c: Check): number {
  const failedAtPeak = c.which === "peak" && c.hot_c != null && Number.isFinite(c.hot_c)
  return Math.max(0, c.peak_hot_c.length - (failedAtPeak ? 1 : 0))
}

/** The cooling setup in one line: option kind, jacket flow and coolant where present, inlet and ambient. */
export function coolingText(c: Cooling): string {
  const j = c.jacket as { flow_m3s?: number; inlet_c?: number; coolant?: string } | null
  const parts = [c.kind.replaceAll("_", " ")]
  if (j?.flow_m3s != null) parts.push(`${(j.flow_m3s * 6e4).toFixed(1)} L/min`)
  if (j?.coolant) parts.push(j.coolant.replaceAll("_", " "))
  if (j?.inlet_c != null) parts.push(`inlet ${j.inlet_c} °C`)
  if (c.ambient_c != null) parts.push(`ambient ${c.ambient_c} °C`)
  return parts.join(", ") + (c.placeholder ? " (placeholder)" : "")
}

const SMALL_GAP_M = 0.0003

/** A hot-spot temperature, or "no steady state" when it is not finite. */
export const tempText = (c: number | null | undefined) => (c == null || !Number.isFinite(c) ? "no steady state" : `${fmt(c, 3)} °C`)

/** The rotor stress and air-gap closure in one line. */
export function rotorText(rating: Rating): string {
  const st = rating.stress
  const gap = rating.gap
  const air = gap?.air_gap_m
  const cases = Object.entries(gap?.cases ?? {}).filter(([, c]) => c.closure != null)
  const mm = (m: number) => fmt(m * 1000, 2)
  const name = (k: string) => k.replaceAll("_", " ")
  const stress = st?.status === "ok" || st?.status == null
    ? `SF ${fmt(st?.safety_factor ?? rating.stress_safety_factor, 2)} at ${fmt(st?.check_speed_rpm)} r/min · speed limit ${fmt(st?.speed_limit_rpm)} r/min`
    : `stress ${st.status.replaceAll("_", " ")}`
  const closure = air != null && cases.length > 0
    ? ` · gap closure ${cases.map(([k, c]) => `${name(k)} ${mm(c.closure as number)}`).join(", ")} mm of ${mm(air)} mm (against ${mm(SMALL_GAP_M)} mm: ${cases.map(([k, c]) => `${name(k)} ${fmt(((c.closure as number) / SMALL_GAP_M) * 100, 2)} %`).join(", ")})`
    : ""
  return `Rotor: ${stress}${closure}`
}
