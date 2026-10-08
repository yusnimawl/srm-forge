import { describe, expect, it } from "vitest"
import type { CaseInputs } from "@/api/types"
import { toForm, toInputs, validationByField } from "./caseForm"

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

const close = (a: unknown, b: unknown, path = ""): void => {
  if (typeof a === "number" && typeof b === "number") {
    expect(Math.abs(a - b), path).toBeLessThanOrEqual(1e-12 * Math.max(1, Math.abs(a)))
  } else if (a && typeof a === "object") {
    const o = b as Record<string, unknown>
    for (const k of Object.keys(a)) close((a as Record<string, unknown>)[k], o[k], `${path}.${k}`)
    expect(Object.keys(o).sort(), path).toEqual(Object.keys(a).sort())
  } else expect(b, path).toEqual(a)
}

describe("caseForm", () => {
  it("round-trips the inputs through the form", () => close(inputs, toInputs(toForm(inputs))))

  it("shows arcs in degrees and sends radians", () => {
    const f = toForm(inputs)
    expect(Number(f.machine.stator_pole_arc)).toBeCloseTo(20, 12)
    expect(Number(f.machine.rotor_pole_arc)).toBeCloseTo(22, 12)
    const out = toInputs({ ...f, machine: { ...f.machine, stator_pole_arc: "30", rotor_pole_arc: "31" } })
    expect(out.design.machine.stator_pole_arc).toBeCloseTo(Math.PI / 6, 12)
    expect(out.design.machine.rotor_pole_arc).toBeCloseTo((31 * Math.PI) / 180, 12)
  })

  it("drops the fixed winding fields in Auto mode and keeps them in Fixed mode", () => {
    const f = toForm(inputs)
    expect(f.winding.mode).toBe("fixed")
    expect(toInputs(f).winding).toEqual({ turns: 24, strands: 2, paths: 2, wire: 0 })
    expect(toInputs({ ...f, winding: { ...f.winding, mode: "auto" } }).winding).toBe("auto")
  })

  it("tolerates a draft with missing or invalid values", () => {
    const f = toForm({ requirements: { peak_power_w: "abc" }, design: { machine: { air_gap: "x" } } })
    expect(f.requirements.peakPowerKw).toBe("abc")
    expect(f.machine.air_gap).toBe("x")
    expect(f.machine.stack_length).toBe("")
    expect(f.winding.mode).toBe("auto")
    const out = toInputs(f)
    expect(out.requirements.peak_power_w).toBe("abc")
    expect(out.requirements.peak_torque_nm).toBeUndefined()
  })

  it("maps a validation loc to a dotted field name", () => {
    const resp = {
      errors: [
        { loc: ["design", "machine", "stator_pole_arc"], msg: "Value error, too wide" },
        { loc: ["design", "machine", "stator_pole_arc"], msg: "second" },
        { loc: ["winding", "paths"], msg: "bad paths" },
        { loc: [], msg: "whole input" },
        { loc: ["requirements", "wires", 0, "round", "diameter"], msg: "wire" },
      ],
      warnings: [],
    }
    expect(validationByField(resp)).toEqual({
      "design.machine.stator_pole_arc": "too wide",
      "winding.paths": "bad paths",
      "": "whole input",
      "requirements.wires.0.diameter": "wire",
    })
  })
})
