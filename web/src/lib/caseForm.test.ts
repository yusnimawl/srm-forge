import { describe, expect, it } from "vitest"
import type { CaseInputs } from "@/api/types"
import { toForm, toInputs, validationByField, withWires } from "./caseForm"

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
      "design.machine.stator_pole_arc": "too wide; second",
      "winding.paths": "bad paths",
      "": "whole input",
      "requirements.wires.0.diameter": "wire",
    })
  })

  it("keeps stored values bit for bit until their field is edited", () => {
    const awkward = structuredClone(inputs) as unknown as Record<string, any>
    awkward.design.machine.stator_outer_diameter = 0.16 * 0.42
    awkward.design.machine.stator_pole_arc = 0.35123456789012345
    awkward.design.machine.air_gap = 0.1 + 0.2
    awkward.requirements.wires[0].diameter = 0.0012 * 1.1
    awkward.j_peak = 12e6 * 1.0000000000001
    expect(toInputs(toForm(awkward))).toEqual(awkward)
    const f = toForm(awkward)
    expect(f.machine.air_gap).toBe("300")                     // shown with 6 significant digits at most
    expect(f.machine.stator_pole_arc).toBe("20.1243")
    expect((f.requirements.wires[0] as { diameter: string }).diameter).toBe("1.32")
    const edited = toInputs({ ...f, machine: { ...f.machine, air_gap: "0.5" } }) as unknown as typeof awkward
    expect(edited.design.machine.air_gap).toBeCloseTo(0.0005, 15)
    expect(edited.design.machine.stator_outer_diameter).toBe(0.16 * 0.42)
  })

  it("sends one strand in density mode", () => {
    const f = toForm(inputs)
    const out = toInputs({ ...f, winding: { ...f.winding, wire: "" } }).winding
    expect(out).toEqual({ turns: 24, strands: 1, paths: 2, wire: null })
  })

  it("keeps a fixed winding on the same wire when an earlier wire is removed", () => {
    const wire = (d: string) => ({ kind: "round" as const, diameter: d, outer_diameter: "1.3" })
    const f0 = toForm(inputs)
    const f = { ...f0, requirements: { ...f0.requirements, wires: [wire("1"), wire("2"), wire("3")] }, winding: { ...f0.winding, wire: "1" } }
    const [w0, w1, w2] = f.requirements.wires
    expect(withWires(f, [w1, w2]).winding.wire).toBe("0")
    expect(withWires(f, [w0, w2]).winding.wire).toBe("2") // its wire is gone: the index is past the list
    expect(withWires(f, [w0, w1]).winding.wire).toBe("1")
    expect(withWires({ ...f, winding: { ...f.winding, wire: "2" } }, [w1, w2]).winding.wire).toBe("1")
    expect(withWires({ ...f, winding: { ...f.winding, wire: "" } }, [w1, w2]).winding.wire).toBe("")
    expect(withWires(f, [w1, w2]).requirements.wires).toEqual([w1, w2])
  })
})
