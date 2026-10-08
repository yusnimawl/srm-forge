import { describe, expect, it } from "vitest"
import type { CaseInputs, Evaluation, MapArrays } from "@/api/types"
import { toForm, toInputs, type CaseTab } from "./caseForm"
import { applySearchSetup, applySection, candidatesCsv, mapCsv, searchSetup, sectionSetup } from "./exports"
import { toRows } from "./candidates"
import { defaultSearchForm, newWire } from "./searchForm"

const map = {
  angles: [0, Math.PI / 6],
  currents: [1, 2],
  psi: [[0.001, 0.002], [0.003, 0.004]],
  torque: [[0, 0.5], [1, 1.5]],
} as MapArrays

const inputs = {
  requirements: {
    peak_power_w: 10000, peak_torque_nm: 32, base_speed_rpm: 3000, max_speed_rpm: 9000, bus_voltage_v: 400,
    max_outer_diameter_m: 0.2, max_mass_kg: null, max_slot_fill: 0.6, phase_current_a: 60,
    wires: [{ kind: "round", diameter: 0.0012, outer_diameter: 0.00128 }],
  },
  design: {
    schema_version: 1,
    machine: {
      schema_version: 1, n_stator_poles: 8, n_rotor_poles: 6, n_phases: 4,
      stator_outer_diameter: 0.16, rotor_outer_diameter: 0.08, air_gap: 0.0004, stack_length: 0.1,
      shaft_diameter: 0.02, stator_pole_arc: (20 * Math.PI) / 180, rotor_pole_arc: (22 * Math.PI) / 180,
      stator_pole_taper: 0, rotor_pole_taper: 0, stator_yoke_thickness: 0.012, rotor_yoke_thickness: 0.012,
      stator_fillet_radius: 0.001, rotor_fillet_radius: 0.001, turns_per_pole: 60, fill_factor: 0.5,
      slot_liner_thickness: 0.0005, coil_inner_clearance: 0.001, lamination_thickness: 0.0001, max_speed_rpm: null,
      materials: { coil: "copper", rotor: "10JNEX900", shaft: "steel_1010", stator: "10JNEX900" },
    },
    mesh: { preset: "full" },
  },
  winding: { turns: 24, strands: 2, paths: 2, wire: 0 },
  margin: null, j_peak: 12e6, j_limit: 6e6, j_peak_max: null,
} as unknown as CaseInputs

describe("mapCsv", () => {
  it("writes one row per grid point with mechanical degrees first", () => {
    const lines = mapCsv(map).split("\n")
    expect(lines).toHaveLength(5)
    expect(lines[0]).toBe("angle_deg,current_a,psi_wb,torque_nm")
    expect(lines[1]).toBe("0,1,0.001,0")
    expect(Number(lines[3].split(",")[0])).toBeCloseTo(30, 12)
    expect(lines[4].split(",").slice(1)).toEqual(["2", "0.004", "1.5"])
  })

  it("writes a missing value as an empty cell", () => {
    const m = { ...map, psi: [[null, 0.002], [0.003, 0.004]] } as MapArrays
    expect(mapCsv(m).split("\n")[1]).toBe("0,1,,0")
  })
})

describe("candidatesCsv", () => {
  const ev = (id: string, error: string | null) => ({
    id, status: "ok", error, mass_kg: 3, torque_ratio: 1.2, power_ratio: 1.1, peak_power_w: 2500,
    power_density_kw_per_kg: 0.8, efficiency_base: 0.9, feasible: true,
    design: { machine: { n_stator_poles: 8, n_rotor_poles: 6, stator_outer_diameter: 0.12 } },
  }) as unknown as Evaluation

  it("uses kW and mm and quotes text fields", () => {
    const rows = toRows({ evaluations: [ev("a", 'bad, "very"')], pareto_ids: ["a"] })
    const [head, row] = candidatesCsv(rows).split("\n")
    expect(head.split(",").slice(0, 3)).toEqual(["id", "poles", "od_mm"])
    expect(head).toContain("peak_power_kw")
    expect(row.startsWith("a,8/6,120,3,1.2,1.1,2.5,0.8,0.9,")).toBe(true)
    expect(row.endsWith(',"bad, ""very"""')).toBe(true)
  })
})

describe("search setup", () => {
  it("round-trips the default form", () => {
    const f = defaultSearchForm()
    const file = searchSetup(f)
    expect(Object.keys(file).sort()).toEqual(["requirements", "schema", "search", "version"])
    expect(applySearchSetup(file, { ...f, peakPowerKw: "5", seed: "9", stator: "M19" })).toEqual(f)
  })

  it("restores the wire list and the winding mode", () => {
    const f = { ...defaultSearchForm(), windingMode: "wires" as const, phaseCurrentA: "60",
      wires: [{ ...newWire("round"), diameter: "1.2", outer_diameter: "1.28" } as never] }
    expect(applySearchSetup(searchSetup(f), defaultSearchForm())).toEqual(f)
  })

  it("leaves the form unchanged for a file without those sections", () => {
    const f = { ...defaultSearchForm(), peakPowerKw: "7" }
    const file = sectionSetup(toForm(inputs), "dimension")
    expect(applySearchSetup(file, f)).toEqual(f)
  })
})

describe("section setup", () => {
  const form = toForm(inputs)
  const TABS: CaseTab[] = ["requirement", "dimension", "material", "winding", "drive"]

  it("holds only the tab's section", () => {
    const sections = { requirement: "requirements", dimension: "geometry", material: "materials", winding: "winding", drive: "drive" }
    for (const tab of TABS) {
      const file = sectionSetup(form, tab)
      expect(file.schema).toBe("srm-setup")
      expect(file.version).toBe(1)
      expect(Object.keys(file).sort()).toEqual(["schema", sections[tab], "version"].sort())
    }
  })

  it("re-applying a tab's own section changes nothing", () => {
    for (const tab of TABS) {
      const back = applySection(form, tab, sectionSetup(form, tab))
      expect(back && toInputs(back)).toEqual(toInputs(form))
    }
  })

  it("merges one section and leaves the other tabs alone", () => {
    const other = toForm({
      ...inputs,
      requirements: { ...inputs.requirements, bus_voltage_v: 500, phase_current_a: null, peak_torque_nm: 40 },
    } as unknown as CaseInputs)
    const merged = applySection(form, "drive", sectionSetup(other, "drive"))!
    expect(merged.requirements.busVoltageV).toBe("500")
    expect(merged.requirements.phaseCurrentA).toBe("")
    expect(merged.requirements.peakTorqueNm).toBe(form.requirements.peakTorqueNm)
    expect(toInputs(merged).requirements.peak_torque_nm).toBe(32)
    expect(toInputs(merged).requirements.bus_voltage_v).toBe(500)
  })

  it("applies a winding section to Auto mode", () => {
    const auto = toForm({ ...inputs, winding: "auto" } as unknown as CaseInputs)
    const merged = applySection(form, "winding", sectionSetup(auto, "winding"))!
    expect(toInputs(merged).winding).toBe("auto")
  })

  it("returns null when the file lacks the section", () => {
    expect(applySection(form, "winding", sectionSetup(form, "drive"))).toBeNull()
  })
})
