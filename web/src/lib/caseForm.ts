import { useEffect, useState } from "react"
import type { CaseInputs } from "@/api/types"
import { newWire, parseNum, wireToSI, type Num, type WireForm } from "./searchForm"
import { fromSI, toSI, type Unit } from "./units"

export type MachineField = { key: string; label: string; unit?: Unit; optional?: boolean; hint?: string }

/** The `RadialSRMParams` fields the Dimension tab edits (UI units; arcs and tapers in degrees). */
export const MACHINE_FIELDS: MachineField[] = [
  { key: "stator_outer_diameter", label: "Stator outer diameter", unit: "mm" },
  { key: "rotor_outer_diameter", label: "Rotor outer diameter", unit: "mm" },
  { key: "air_gap", label: "Air gap", unit: "mm" },
  { key: "stack_length", label: "Stack length", unit: "mm" },
  { key: "shaft_diameter", label: "Shaft diameter", unit: "mm" },
  { key: "stator_pole_arc", label: "Stator pole arc", unit: "deg" },
  { key: "rotor_pole_arc", label: "Rotor pole arc", unit: "deg" },
  { key: "stator_pole_taper", label: "Stator pole taper", unit: "deg" },
  { key: "rotor_pole_taper", label: "Rotor pole taper", unit: "deg" },
  { key: "stator_yoke_thickness", label: "Stator yoke thickness", unit: "mm" },
  { key: "rotor_yoke_thickness", label: "Rotor yoke thickness", unit: "mm" },
  { key: "stator_fillet_radius", label: "Stator fillet radius", unit: "mm" },
  { key: "rotor_fillet_radius", label: "Rotor fillet radius", unit: "mm" },
  { key: "fill_factor", label: "Fill factor", hint: "Copper area over coil-side area." },
  { key: "slot_liner_thickness", label: "Slot liner thickness", unit: "mm" },
  { key: "coil_inner_clearance", label: "Coil inner clearance", unit: "mm" },
  { key: "lamination_thickness", label: "Lamination thickness", unit: "mm", optional: true, hint: "Empty takes the stator material's." },
]
export const POLE_KEYS = ["n_stator_poles", "n_rotor_poles", "n_phases"] as const

/** Common SRM pole sets: stator poles, rotor poles, phases. */
export const POLE_SETS: readonly (readonly [number, number, number])[] = [
  [6, 4, 3], [8, 6, 4], [12, 8, 3], [16, 12, 4], [24, 16, 3],
]

export type CaseForm = {
  requirements: {
    peakPowerKw: Num; peakTorqueNm: Num; baseSpeedRpm: Num; maxSpeedRpm: Num; busVoltageV: Num
    maxOuterDiameterMm: Num; maxMassKg: Num; maxSlotFill: Num; phaseCurrentA: Num; wires: WireForm[]
  }
  /** `MACHINE_FIELDS` and the pole counts, as text in UI units. */
  machine: Record<string, Num>
  preset: "full" | "screening"
  stator: string
  rotor: string
  winding: { mode: "auto" | "fixed"; turns: Num; strands: Num; paths: Num; wire: Num }
  margin: Num
  jPeak: Num
  jLimit: Num
  jPeakMax: Num
  /** The raw inputs, for the fields no tab edits (schema versions, shaft and coil materials, mesh settings). */
  rest: Record<string, unknown>
}

type Raw = Record<string, unknown>
const obj = (x: unknown): Raw => (x && typeof x === "object" && !Array.isArray(x) ? (x as Raw) : {})

/** A stored value as editable text; a value that is not a number (a draft may hold one) is shown as it is. */
const show = (v: unknown, unit?: Unit): string =>
  typeof v === "number" ? String(Number((unit ? fromSI(v, unit) : v).toPrecision(14))) : typeof v === "string" ? v : ""

/** Text as a stored value: a number in SI, undefined when empty, the text itself when it is no number (so the
 *  server reports it under its field). */
const read = (v: Num, unit?: Unit): number | string | undefined => {
  const n = parseNum(v)
  if (n === "empty") return undefined
  if (n === "invalid") return String(v)
  return unit ? toSI(n, unit) : n
}
const readOpt = (v: Num, unit?: Unit) => read(v, unit) ?? null

const MM_FIELDS: Record<WireForm["kind"], string[]> = {
  round: ["diameter", "outer_diameter"],
  rectangular: ["width", "height", "insulation"],
  litz: ["strand_diameter", "outer_diameter"],
}

function wireToForm(raw: unknown): WireForm[] {
  const w = obj(raw)
  const kind = w.kind as WireForm["kind"]
  if (!(kind in MM_FIELDS)) return []
  const out = newWire(kind) as Record<string, Num>
  for (const f of Object.keys(out)) {
    if (f !== "kind") out[f] = show(w[f], MM_FIELDS[kind].includes(f) ? "mm" : undefined)
  }
  return [out as unknown as WireForm]
}

/** The form for stored inputs; `inputs` may be an incomplete or invalid draft. */
export function toForm(inputs: Raw): CaseForm {
  const req = obj(inputs.requirements)
  const design = obj(inputs.design)
  const machine = obj(design.machine)
  const mats = obj(machine.materials)
  const w = inputs.winding
  const fixed = obj(w)
  return {
    requirements: {
      peakPowerKw: show(req.peak_power_w, "kW"),
      peakTorqueNm: show(req.peak_torque_nm),
      baseSpeedRpm: show(req.base_speed_rpm),
      maxSpeedRpm: show(req.max_speed_rpm),
      busVoltageV: show(req.bus_voltage_v),
      maxOuterDiameterMm: show(req.max_outer_diameter_m, "mm"),
      maxMassKg: show(req.max_mass_kg),
      maxSlotFill: show(req.max_slot_fill),
      phaseCurrentA: show(req.phase_current_a),
      wires: (Array.isArray(req.wires) ? req.wires : []).flatMap(wireToForm),
    },
    machine: Object.fromEntries([
      ...POLE_KEYS.map((k) => [k, show(machine[k])]),
      ...MACHINE_FIELDS.map((f) => [f.key, show(machine[f.key], f.unit)]),
    ]),
    preset: obj(design.mesh).preset === "screening" ? "screening" : "full",
    stator: typeof mats.stator === "string" ? mats.stator : "",
    rotor: typeof mats.rotor === "string" ? mats.rotor : "",
    winding: {
      mode: w && w !== "auto" && typeof w === "object" ? "fixed" : "auto",
      turns: show(fixed.turns),
      strands: show(fixed.strands) || "1",
      paths: show(fixed.paths) || "1",
      wire: show(fixed.wire),
    },
    margin: show(inputs.margin),
    jPeak: show(inputs.j_peak, "A/mm2"),
    jLimit: show(inputs.j_limit, "A/mm2"),
    jPeakMax: show(inputs.j_peak_max, "A/mm2"),
    rest: inputs,
  }
}

/** Stored inputs (SI, radians) for the form; the fixed-winding fields are present only in Fixed mode. */
export function toInputs(f: CaseForm): CaseInputs {
  const r = f.requirements
  const restDesign = obj(f.rest.design)
  const restMachine = obj(restDesign.machine)
  const machine: Raw = { ...restMachine }
  for (const k of POLE_KEYS) machine[k] = read(f.machine[k])
  for (const m of MACHINE_FIELDS) machine[m.key] = m.optional ? readOpt(f.machine[m.key], m.unit) : read(f.machine[m.key], m.unit)
  machine.materials = { ...obj(restMachine.materials), stator: f.stator, rotor: f.rotor }
  const wd = f.winding
  return {
    ...f.rest,
    requirements: {
      peak_power_w: read(r.peakPowerKw, "kW"),
      peak_torque_nm: read(r.peakTorqueNm),
      base_speed_rpm: read(r.baseSpeedRpm),
      max_speed_rpm: read(r.maxSpeedRpm),
      bus_voltage_v: read(r.busVoltageV),
      max_outer_diameter_m: readOpt(r.maxOuterDiameterMm, "mm"),
      max_mass_kg: readOpt(r.maxMassKg),
      max_slot_fill: read(r.maxSlotFill),
      phase_current_a: readOpt(r.phaseCurrentA),
      wires: r.wires.map(wireToSI),
    },
    design: { ...restDesign, machine, mesh: { ...obj(restDesign.mesh), preset: f.preset } },
    winding: wd.mode === "auto"
      ? "auto"
      : { turns: read(wd.turns), strands: read(wd.strands), paths: read(wd.paths), wire: readOpt(wd.wire) },
    margin: readOpt(f.margin),
    j_peak: readOpt(f.jPeak, "A/mm2"),
    j_limit: readOpt(f.jLimit, "A/mm2"),
    j_peak_max: readOpt(f.jPeakMax, "A/mm2"),
  } as unknown as CaseInputs
}

export type Issue = { loc: (string | number)[]; msg: string }
export type IssuesResponse = { errors: Issue[]; warnings: Issue[] }

const WIRE_TAGS = new Set(["round", "rectangular", "litz"])

/** Dotted field name of an issue's loc; Pydantic's union tag after a wire index is dropped. */
export function issueKey(loc: Issue["loc"]): string {
  const l = [...loc]
  const w = l.indexOf("wires")
  if (w >= 0 && typeof l[w + 1] === "number" && WIRE_TAGS.has(String(l[w + 2]))) l.splice(w + 2, 1)
  return l.join(".")
}

/** Field name -> first error message; whole-input messages are under "". */
export function validationByField(resp: Pick<IssuesResponse, "errors">): Record<string, string> {
  const out: Record<string, string> = {}
  for (const e of resp.errors) {
    const key = issueKey(e.loc)
    if (!(key in out)) out[key] = e.msg.replace(/^Value error, /, "")
  }
  return out
}

export type CaseTab = "requirement" | "dimension" | "material" | "winding" | "drive"
export const CASE_TABS: { id: CaseTab; label: string }[] = [
  { id: "requirement", label: "Requirement" },
  { id: "dimension", label: "Dimension" },
  { id: "material", label: "Material" },
  { id: "winding", label: "Winding" },
  { id: "drive", label: "Drive" },
]

const REQ_KEYS = ["peak_power_w", "peak_torque_nm", "base_speed_rpm", "max_speed_rpm", "max_outer_diameter_m", "max_mass_kg", "max_slot_fill"]
const TAB_OF_KEY: Record<string, CaseTab> = {
  ...Object.fromEntries(REQ_KEYS.map((k) => [`requirements.${k}`, "requirement"])),
  "requirements.bus_voltage_v": "drive",
  "requirements.phase_current_a": "drive",
  ...Object.fromEntries([...POLE_KEYS, ...MACHINE_FIELDS.map((f) => f.key)].map((k) => [`design.machine.${k}`, "dimension"])),
  "design.mesh.preset": "dimension",
  "design.machine.materials.stator": "material",
  "design.machine.materials.rotor": "material",
  margin: "material",
  ...Object.fromEntries(["turns", "strands", "paths", "wire"].map((k) => [`winding.${k}`, "winding"])),
  ...Object.fromEntries(["j_peak", "j_limit", "j_peak_max"].map((k) => [k, "winding"])),
}

/** The tab whose field shows this error, or null when no field does (the error goes to the summary). */
export function tabOfKey(key: string): CaseTab | null {
  return TAB_OF_KEY[key] ?? (/^requirements\.wires\.\d+(\.\w+)?$/.test(key) ? "requirement" : null)
}

/** `value`, updated `ms` after it stops changing. */
export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}
