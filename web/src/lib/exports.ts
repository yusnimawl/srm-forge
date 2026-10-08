import type { SetupFile } from "@/api/cases"
import type { MapArrays } from "@/api/types"
import { toForm, toInputs, type CaseForm, type CaseTab } from "./caseForm"
import type { CandidateRow } from "./candidates"
import { toSearchRequest, type SearchFormValues } from "./searchForm"
import { fromSI } from "./units"

/** RFC 4180: a field with a comma, quote or line break is quoted and its quotes doubled. */
const field = (v: string | number | boolean | null | undefined): string => {
  if (v == null || (typeof v === "number" && !Number.isFinite(v))) return ""
  const s = typeof v === "number" ? String(Number(v.toPrecision(12))) : String(v)
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s
}

const csv = (rows: (string | number | boolean | null | undefined)[][]) => rows.map((r) => r.map(field).join(",")).join("\n")

/** One row per (angle, current) grid point; angles in mechanical degrees, a missing value is an empty cell. */
export function mapCsv(map: MapArrays): string {
  const rows: (string | number | null)[][] = [["angle_deg", "current_a", "psi_wb", "torque_nm"]]
  map.angles.forEach((a, k) =>
    map.currents.forEach((i, j) => rows.push([a == null ? null : fromSI(a, "deg"), i, map.psi[k][j], map.torque[k][j]])),
  )
  return csv(rows)
}

/** The candidate table as shown: mm, kW, kW/kg. */
export const candidatesCsv = (rows: CandidateRow[]): string =>
  csv([
    ["id", "poles", "od_mm", "mass_kg", "torque_ratio", "power_ratio", "peak_power_kw", "power_density_kw_per_kg",
      "efficiency_base", "feasible", "status", "pareto", "error"],
    ...rows.map((r) => [r.id, r.poles, r.od_mm, r.mass_kg, r.torque_ratio, r.power_ratio, r.peak_power_kw,
      r.power_density, r.efficiency_base, r.feasible, r.status, r.pareto, r.error]),
  ])

/** Saves `data` as a file through a temporary link. */
export function download(name: string, data: string | Blob): void {
  const url = URL.createObjectURL(typeof data === "string" ? new Blob([data], { type: "text/plain;charset=utf-8" }) : data)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.append(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const HEADER = { schema: "srm-setup", version: 1 } as const

/** The New-search form as a setup file with only its `requirements` and `search` sections. */
export function searchSetup(v: SearchFormValues): SetupFile {
  const { requirements, settings } = toSearchRequest(v)
  return { ...HEADER, requirements, search: settings } as SetupFile
}

/** The form with the file's `requirements` and `search` sections applied; other sections are ignored. */
export function applySearchSetup(file: SetupFile, v: SearchFormValues): SearchFormValues {
  let out = v
  if (file.requirements) {
    const r = toForm({ requirements: file.requirements }).requirements
    out = {
      ...out,
      peakPowerKw: r.peakPowerKw, peakTorqueNm: r.peakTorqueNm, baseSpeedRpm: r.baseSpeedRpm, maxSpeedRpm: r.maxSpeedRpm,
      busVoltageV: r.busVoltageV, maxOuterDiameterMm: r.maxOuterDiameterMm, maxMassKg: r.maxMassKg,
      maxSlotFill: r.maxSlotFill, phaseCurrentA: r.phaseCurrentA, wires: r.wires,
      windingMode: r.wires.length > 0 ? "wires" : "density",
    }
  }
  const s = file.search
  if (s) {
    out = {
      ...out,
      nCandidates: String(s.n_candidates), shortlist: String(s.shortlist), seed: String(s.seed),
      stator: s.stator, rotor: s.rotor, preset: s.preset,
    }
  }
  return out
}

type Raw = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

const SECTION = {
  requirement: "requirements", dimension: "geometry", material: "materials", winding: "winding", drive: "drive",
} as const

/** One tab's inputs as a setup file holding just that section. */
export function sectionSetup(form: CaseForm, tab: CaseTab): SetupFile {
  const i = toInputs(form) as unknown as Raw
  const { materials, ...machine } = i.design.machine
  const sections: Record<CaseTab, unknown> = {
    requirement: i.requirements,
    dimension: { machine, preset: i.design.mesh.preset },
    material: materials,
    winding: {
      mode: i.winding === "auto" ? "auto" : "fixed",
      fixed: i.winding === "auto" ? undefined : i.winding,
      margin: i.margin, j_peak: i.j_peak, j_limit: i.j_limit, j_peak_max: i.j_peak_max,
    },
    drive: { bus_voltage_v: i.requirements.bus_voltage_v, phase_current_a: i.requirements.phase_current_a },
  }
  return { ...HEADER, [SECTION[tab]]: sections[tab] } as SetupFile
}

/** The form with the file's section for `tab` merged in and every other tab as it was; null when the file lacks it. */
export function applySection(form: CaseForm, tab: CaseTab, file: SetupFile): CaseForm | null {
  const sec = file[SECTION[tab]] as Raw | null | undefined
  if (!sec) return null
  const cur = toInputs(form) as unknown as Raw
  const machine: Raw = cur.design.machine
  const merged: Raw = { ...cur }
  switch (tab) {
    case "requirement":
      merged.requirements = { ...cur.requirements, ...sec, bus_voltage_v: cur.requirements.bus_voltage_v, phase_current_a: cur.requirements.phase_current_a }
      break
    case "dimension":
      merged.design = { ...cur.design, machine: { ...machine, ...sec.machine, materials: machine.materials }, mesh: { ...cur.design.mesh, preset: sec.preset } }
      break
    case "material":
      merged.design = { ...cur.design, machine: { ...machine, materials: sec } }
      break
    case "winding":
      Object.assign(merged, {
        winding: sec.mode === "auto" ? "auto" : sec.fixed,
        margin: sec.margin ?? null, j_peak: sec.j_peak ?? null, j_limit: sec.j_limit ?? null, j_peak_max: sec.j_peak_max ?? null,
      })
      break
    case "drive":
      merged.requirements = { ...cur.requirements, bus_voltage_v: sec.bus_voltage_v, phase_current_a: sec.phase_current_a ?? null }
      break
  }
  const n = toForm(merged)
  const slices: Record<CaseTab, Partial<CaseForm>> = {
    requirement: {
      requirements: { ...n.requirements, busVoltageV: form.requirements.busVoltageV, phaseCurrentA: form.requirements.phaseCurrentA },
    },
    dimension: { machine: n.machine, preset: n.preset },
    material: { stator: n.stator, rotor: n.rotor },
    winding: { winding: n.winding, margin: n.margin, jPeak: n.jPeak, jLimit: n.jLimit, jPeakMax: n.jPeakMax },
    drive: { requirements: { ...form.requirements, busVoltageV: n.requirements.busVoltageV, phaseCurrentA: n.requirements.phaseCurrentA } },
  }
  return { ...form, rest: merged, ...slices[tab] }
}
