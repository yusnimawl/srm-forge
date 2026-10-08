import type { SearchResult } from "@/api/types"
import { fromSI } from "./units"
export const AXES = {
  mass_kg: "Mass (kg)",
  peak_power_kw: "Peak power (kW)",
  power_density: "Power density (kW/kg)",
  efficiency_base: "Efficiency at base speed",
  torque_ratio: "Torque ratio",
} as const
export type AxisKey = keyof typeof AXES

export type CandidateRow = {
  id: string
  poles: string
  od_mm: number | null
  mass_kg: number | null
  torque_ratio: number | null
  power_ratio: number | null
  peak_power_kw: number | null
  power_density: number | null
  efficiency_base: number | null
  feasible: boolean
  status: string
  error: string | null
  pareto: boolean
}

const num = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? null : v)

export function toRows(result: Pick<SearchResult, "evaluations" | "pareto_ids">): CandidateRow[] {
  const front = new Set(result.pareto_ids)
  return result.evaluations.map((e) => {
    const m = e.design.machine
    const ok = e.status === "ok"
    const power = num(e.peak_power_w)
    const od = num(m.stator_outer_diameter)
    return {
      id: e.id,
      poles: `${m.n_stator_poles}/${m.n_rotor_poles}`,
      od_mm: od == null ? null : fromSI(od, "mm"),
      mass_kg: num(e.mass_kg),
      torque_ratio: num(e.torque_ratio),
      power_ratio: num(e.power_ratio),
      peak_power_kw: power == null ? null : fromSI(power, "kW"),
      power_density: num(e.power_density_kw_per_kg),
      efficiency_base: num(e.efficiency_base),
      feasible: ok && e.feasible === true,
      status: e.status,
      error: e.error ?? null,
      pareto: front.has(e.id),
    }
  })
}
