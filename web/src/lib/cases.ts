import type { CaseSummary } from "@/api/types"
import { fromSI } from "./units"

export const MAX_SHOWN = 6

export type CaseStatus = "Draft" | "Evaluated" | "EM-validated" | "Failed"

export type CaseRow = {
  id: string
  label: string
  origin: string
  flag: string | null
  comment: string | null
  poles: string | null
  preset: string | null
  status: CaseStatus
  show_in_graphs: boolean
  torque_ratio: number | null
  power_ratio: number | null
  peak_power_kw: number | null
  mass_kg: number | null
  power_density: number | null
  efficiency_base: number | null
}

export function caseStatus(c: Pick<CaseSummary, "stale" | "status" | "validated">): CaseStatus {
  if (c.stale) return "Draft"
  if (c.status !== "ok") return "Failed"
  return c.validated ? "EM-validated" : "Evaluated"
}

export function toCaseRows(list: CaseSummary[]): CaseRow[] {
  return list.map((c) => {
    const draft = c.stale
    const n = (v: number | null) => (draft || v == null || !Number.isFinite(v) ? null : v)
    const power = n(c.peak_power_w)
    return {
      id: c.id,
      label: c.label || c.id,
      origin: c.origin,
      flag: c.flag,
      comment: c.comment,
      poles: c.poles,
      preset: c.preset,
      status: caseStatus(c),
      show_in_graphs: c.show_in_graphs,
      torque_ratio: n(c.torque_ratio),
      power_ratio: n(c.power_ratio),
      peak_power_kw: power == null ? null : fromSI(power, "kW"),
      mass_kg: n(c.mass_kg),
      power_density: n(c.power_density_kw_per_kg),
      efficiency_base: n(c.efficiency_base),
    }
  })
}

export const filterByFlag = (rows: CaseRow[], flag: string | null): CaseRow[] =>
  flag === null ? rows : rows.filter((r) => r.flag === flag)

export const canShowMore = (rows: CaseRow[]): boolean => rows.filter((r) => r.show_in_graphs).length < MAX_SHOWN
