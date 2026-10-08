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

// Callers run validateForm first; an entry that does not parse becomes undefined.
const num = (v: Num, scale = 1): number => {
  const n = parseNum(v)
  return (typeof n === "number" ? n * scale : undefined) as number
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

const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i

/** "empty" for blank text, "invalid" unless the whole text is one number. One decimal comma is accepted
 *  only when the text has no dot ("0,6"); "9,000" is rejected rather than read as 9. */
export function parseNum(v: Num): number | "empty" | "invalid" {
  let s = String(v).trim()
  if (s === "") return "empty"
  if (/^[+-]?\d{1,3},\d{3}$/.test(s)) return "invalid"   // thousands separator or decimal comma: ask
  if (!s.includes(".") && s.split(",").length === 2) s = s.replace(",", ".")
  return NUMBER.test(s) ? Number(s) : "invalid"
}

const WIRE_FIELDS: Record<WireForm["kind"], string[]> = {
  round: ["diameter", "outer_diameter"],
  rectangular: ["width", "height", "insulation"],
  litz: ["strand_diameter", "strands", "outer_diameter"],
}

/** Client-side check before submitting: field name -> message, empty when the form can be sent.
 *  Empty optional limits mean "no limit"; every other number is required. */
export function validateForm(v: SearchFormValues): Record<string, string> {
  const out: Record<string, string> = {}
  const check = (key: string, value: Num, opts: { optional?: boolean; integer?: boolean } = {}) => {
    const n = parseNum(value)
    if (n === "empty") {
      if (!opts.optional) out[key] = "Required"
    } else if (n === "invalid") out[key] = "Enter a number"
    else if (opts.integer && !Number.isInteger(n)) out[key] = "Enter a whole number"
  }
  check("requirements.peak_power_w", v.peakPowerKw)
  check("requirements.peak_torque_nm", v.peakTorqueNm)
  check("requirements.base_speed_rpm", v.baseSpeedRpm)
  check("requirements.max_speed_rpm", v.maxSpeedRpm)
  check("requirements.bus_voltage_v", v.busVoltageV)
  check("requirements.max_outer_diameter_m", v.maxOuterDiameterMm, { optional: true })
  check("requirements.max_mass_kg", v.maxMassKg, { optional: true })
  check("requirements.max_slot_fill", v.maxSlotFill)
  check("settings.n_candidates", v.nCandidates, { integer: true })
  check("settings.shortlist", v.shortlist, { integer: true })
  check("settings.seed", v.seed, { integer: true })
  if (v.windingMode === "wires") {
    check("requirements.phase_current_a", v.phaseCurrentA)
    if (v.wires.length === 0) out["requirements.wires"] = "Add at least one wire"
    v.wires.forEach((w, i) => WIRE_FIELDS[w.kind].forEach((f) =>
      check(`requirements.wires.${i}.${f}`, (w as Record<string, Num>)[f], { integer: f === "strands" })))
  }
  return out
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
    // Pydantic adds the wire's union tag after the index; the form addresses wires by index and field.
    const w = loc.indexOf("wires")
    if (w >= 0 && typeof loc[w + 1] === "number" && typeof loc[w + 2] === "string" && loc[w + 2] in WIRE_FIELDS) loc.splice(w + 2, 1)
    const key = loc.join(".")
    if (!(key in out)) out[key] = issue.msg
  }
  return out
}
