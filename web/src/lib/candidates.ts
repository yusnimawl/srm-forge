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

/** The parts of `search_result_json` the run pages read. */
export type SearchResult = {
  sampled?: number
  dropped?: Record<string, number>
  stage1_rejected?: number
  cancelled?: boolean
  pareto_ids: string[]
  evaluations: {
    id: string
    design: { machine: { n_stator_poles: number; n_rotor_poles: number; stator_outer_diameter: number } }
    status: string
    error?: string | null
    mass_kg?: number | null
    torque_ratio?: number | null
    power_ratio?: number | null
    peak_power_w?: number | null
    power_density_kw_per_kg?: number | null
    efficiency_base?: number | null
    feasible?: boolean | null
  }[]
}

const num = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? null : v)

export function toRows(result: SearchResult): CandidateRow[] {
  const front = new Set(result.pareto_ids)
  return result.evaluations.map((e) => {
    const m = e.design.machine
    const ok = e.status === "ok"
    const power = num(e.peak_power_w)
    const od = num(m.stator_outer_diameter)
    return {
      id: e.id,
      poles: `${m.n_stator_poles}/${m.n_rotor_poles}`,
      od_mm: od == null ? null : od * 1000,
      mass_kg: num(e.mass_kg),
      torque_ratio: num(e.torque_ratio),
      power_ratio: num(e.power_ratio),
      peak_power_kw: power == null ? null : power / 1000,
      power_density: num(e.power_density_kw_per_kg),
      efficiency_base: num(e.efficiency_base),
      feasible: ok && e.feasible === true,
      status: e.status,
      error: e.error ?? null,
      pareto: front.has(e.id),
    }
  })
}
