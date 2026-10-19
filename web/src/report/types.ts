import type { components } from "@/api/schema"
import type { Case } from "@/api/types"
import type { Trace } from "@/lib/analysis"
import type { LossesResult } from "@/lib/losses"

/** A part of the report that may be missing: fetched, or the reason it is not. */
export type Part<T> = { ok: true; value: T } | { ok: false; reason: string }
export type Finding = components["schemas"]["FindingOut"]
export type Report = components["schemas"]["ReportOut"]
export type CompareOut = components["schemas"]["CompareOut"]
export type ReportFrame = { src: string; angle: number; currentA: number; psi: number; torque: number; status: string }
export type ReportAnimation = { frames: ReportFrame[]; probes: Trace[]; currentA: number; bMax: number }

export interface ReportData {
  caseOut: Case
  report: Report
  /** SVG text of the machine outline. */
  outline: Part<string>
  losses: Part<LossesResult>
  /** Null when the case has no parent. */
  compare: Part<CompareOut> | null
  animation: Part<ReportAnimation>
}
