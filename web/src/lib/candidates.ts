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

export type Winding = {
  turns: number
  strands?: number | null
  paths?: number | null
  copper_area?: number | null
  current?: number | null
  resistance?: number | null
  wire?: number | null
}
export type Envelope = {
  speeds_rpm: number[]
  torque: (number | null)[]
  power: (number | null)[]
  theta_on_el?: (number | null)[]
  theta_off_el?: (number | null)[]
}
export type Evaluation = {
  id: string
  design: {
    machine: { n_stator_poles: number; n_rotor_poles: number; stator_outer_diameter: number }
  }
  status: string
  error?: string | null
  mass_kg?: number | null
  winding?: Winding | null
  torque_ratio?: number | null
  power_ratio?: number | null
  peak_power_w?: number | null
  power_density_kw_per_kg?: number | null
  efficiency_base?: number | null
  feasible?: boolean | null
  envelope?: Envelope | null
  key?: {
    la: number | null
    lu: number | null
    la_lu: number | null
    peak_torque: number | null
    psi_max: number | null
    i_max: number | null
    unaligned_angle: number | null
  } | null
  scan?: { winding: Winding; torque_ratio: number | null; power_ratio: number | null; i_rms: number | null; feasible: boolean | null }[] | null
  i_rms_a?: number | null
  j_rms?: number | null
  map?: { angles: number[]; currents: number[]; psi: (number | null)[][]; torque: (number | null)[][] } | null
}

/** The parts of `search_result_json` the run pages read. */
export type SearchResult = {
  sampled?: number
  dropped?: Record<string, number>
  stage1_rejected?: number
  cancelled?: boolean
  pareto_ids: string[]
  requirements?: { wires?: { kind: string }[] | null }
  evaluations: Evaluation[]
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
