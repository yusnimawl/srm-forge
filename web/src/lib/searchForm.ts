import type { SearchRequest, ValidationIssue } from "@/api/client"
import { toSI } from "@/lib/units"

/** Numeric inputs hold text while being edited; "" means empty. */
export type Num = string | number

export type WireForm =
  | { kind: "round"; diameter: Num; outer_diameter: Num }
  | { kind: "rectangular"; width: Num; height: Num; insulation: Num }
  | { kind: "litz"; strand_diameter: Num; strands: Num; outer_diameter: Num }

/** UI units: kW, N·m, rpm, V, mm, kg, A; wire sizes in mm. */
export type SearchFormValues = {
  peakPowerKw: Num
  peakTorqueNm: Num
  baseSpeedRpm: Num
  maxSpeedRpm: Num
  busVoltageV: Num
  maxOuterDiameterMm: Num
  maxMassKg: Num
  maxSlotFill: Num
  windingMode: "density" | "wires"
  phaseCurrentA: Num
  wires: WireForm[]
  nCandidates: Num
  shortlist: Num
  seed: Num
  stator: string
  rotor: string
  preset: "full" | "screening"
}

export const defaultSearchForm = (): SearchFormValues => ({
  peakPowerKw: "10",
  peakTorqueNm: "32",
  baseSpeedRpm: "3000",
  maxSpeedRpm: "9000",
  busVoltageV: "400",
  maxOuterDiameterMm: "",
  maxMassKg: "",
  maxSlotFill: "0.6",
  windingMode: "density",
  phaseCurrentA: "",
  wires: [],
  nCandidates: "200",
  shortlist: "40",
  seed: "0",
  stator: "10JNEX900",
  rotor: "10JNEX900",
  preset: "full",
})

export const newWire = (kind: WireForm["kind"]): WireForm =>
  kind === "round" ? { kind, diameter: "", outer_diameter: "" }
    : kind === "rectangular" ? { kind, width: "", height: "", insulation: "" }
      : { kind, strand_diameter: "", strands: "", outer_diameter: "" }

// An empty or unparsable entry becomes undefined, so the server reports "Field required".
const num = (v: Num, scale = 1): number => {
  const s = String(v).trim().replace(",", ".")
  const n = s === "" ? NaN : Number(s)
  return (Number.isFinite(n) ? n * scale : undefined) as number
}
const optional = (v: Num, scale = 1): number | null => (String(v).trim() === "" ? null : num(v, scale))
const mm = (v: Num) => num(v, toSI(1, "mm"))

function wireToSI(w: WireForm): SearchRequest["requirements"]["wires"][number] {
  switch (w.kind) {
    case "round":
      return { kind: "round", diameter: mm(w.diameter), outer_diameter: mm(w.outer_diameter) }
    case "rectangular":
      return { kind: "rectangular", width: mm(w.width), height: mm(w.height), insulation: mm(w.insulation) }
    case "litz":
      return { kind: "litz", strand_diameter: mm(w.strand_diameter), strands: num(w.strands), outer_diameter: mm(w.outer_diameter) }
  }
}

export function toSearchRequest(v: SearchFormValues): SearchRequest {
  const wireMode = v.windingMode === "wires"
  return {
    requirements: {
      peak_power_w: num(v.peakPowerKw, toSI(1, "kW")),
      peak_torque_nm: num(v.peakTorqueNm),
      base_speed_rpm: num(v.baseSpeedRpm),
      max_speed_rpm: num(v.maxSpeedRpm),
      bus_voltage_v: num(v.busVoltageV),
      max_outer_diameter_m: optional(v.maxOuterDiameterMm, toSI(1, "mm")),
      max_mass_kg: optional(v.maxMassKg),
      max_slot_fill: num(v.maxSlotFill),
      wires: wireMode ? v.wires.map(wireToSI) : [],
      phase_current_a: wireMode ? optional(v.phaseCurrentA) : null,
    },
    settings: {
      n_candidates: num(v.nCandidates),
      shortlist: num(v.shortlist),
      seed: num(v.seed),
      stator: v.stator,
      rotor: v.rotor,
      preset: v.preset,
    },
  }
}

/** Field name -> message from a 422 detail. The name is the `loc` without the leading "body"/"payload";
 *  a plain-string detail is filed under "". The first message per field wins. */
export function fieldErrors(detail: ValidationIssue[] | string): Record<string, string> {
  if (typeof detail === "string") return { "": detail }
  const out: Record<string, string> = {}
  for (const issue of detail) {
    const loc = [...issue.loc]
    if (loc[0] === "body") loc.shift()
    if (loc[0] === "payload") loc.shift()
    const key = loc.join(".")
    if (!(key in out)) out[key] = issue.msg
  }
  return out
}
