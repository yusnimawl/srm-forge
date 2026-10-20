import { describe, expect, it } from "vitest"
import { defaultSearchForm, fieldErrors, parseNum, toSearchRequest, validateForm } from "./searchForm"

describe("toSearchRequest", () => {
  it("converts the defaults to SI", () => {
    const r = toSearchRequest(defaultSearchForm())
    expect(r.requirements.peak_power_w).toBe(10000)
    expect(r.requirements.peak_torque_nm).toBe(32)
    expect(r.requirements.max_outer_diameter_m).toBeNull()
    expect(r.requirements.wires).toEqual([])
    expect(r.requirements.phase_current_a).toBeNull()
    expect(r.settings).toMatchObject({ n_candidates: 200, shortlist: 40, seed: 0, preset: "full", stator: "10JNEX900" })
  })

  it("converts wires from mm to m in wire mode", () => {
    const v = defaultSearchForm()
    v.windingMode = "wires"
    v.phaseCurrentA = "100"
    v.maxOuterDiameterMm = "250"
    v.wires = [
      { kind: "round", diameter: 1.0, outer_diameter: 1.08 },
      { kind: "rectangular", width: 3, height: 2, insulation: 0.1 },
      { kind: "litz", strand_diameter: 0.1, strands: 100, outer_diameter: 2 },
    ]
    const r = toSearchRequest(v).requirements
    expect(r.phase_current_a).toBe(100)
    expect(r.max_outer_diameter_m).toBeCloseTo(0.25, 12)
    expect(r.wires[0]).toEqual({ kind: "round", diameter: 0.001, outer_diameter: 0.00108 })
    expect(r.wires[1]).toEqual({ kind: "rectangular", width: 0.003, height: 0.002, insulation: 0.0001 })
    expect(r.wires[2]).toEqual({ kind: "litz", strand_diameter: 0.0001, strands: 100, outer_diameter: 0.002 })
  })

  it("drops wires and current in density mode", () => {
    const v = defaultSearchForm()
    v.wires = [{ kind: "round", diameter: 1, outer_diameter: 1.1 }]
    v.phaseCurrentA = "100"
    const r = toSearchRequest(v).requirements
    expect(r.wires).toEqual([])
    expect(r.phase_current_a).toBeNull()
  })
})

describe("fieldErrors", () => {
  it("maps a field path without body and payload", () => {
    expect(fieldErrors([{ loc: ["body", "payload", "requirements", "peak_power_w"], msg: "x", type: "t" }]))
      .toEqual({ "requirements.peak_power_w": "x" })
  })
  it("strips pydantic's prefix and copies a power error under power and torque", () => {
    const msg = "power 10000 W disagrees with torque"
    expect(fieldErrors([{ loc: ["body", "payload", "requirements"], msg: `Value error, ${msg}`, type: "t" }]))
      .toEqual({ requirements: msg, "requirements.peak_power_w": msg, "requirements.peak_torque_nm": msg })
  })
  it("keeps other model-level requirements errors as one entry", () => {
    expect(fieldErrors([{ loc: ["body", "payload", "requirements"], msg: "Value error, max speed below base", type: "t" }]))
      .toEqual({ requirements: "max speed below base" })
  })
  it("keeps settings and indexed paths, first message wins", () => {
    expect(fieldErrors([
      { loc: ["body", "payload", "settings", "n_candidates"], msg: "a", type: "t" },
      { loc: ["body", "payload", "settings", "n_candidates"], msg: "b", type: "t" },
      { loc: ["body", "payload", "requirements", "wires", 0, "diameter"], msg: "c", type: "t" },
    ])).toEqual({ "settings.n_candidates": "a", "requirements.wires.0.diameter": "c" })
  })
  it("handles a string detail", () => {
    expect(fieldErrors("queue full")).toEqual({ "": "queue full" })
  })
})

describe("fieldErrors with wires", () => {
  it("drops the union tag from field and wire-level errors", () => {
    expect(fieldErrors([
      { loc: ["body", "payload", "requirements", "wires", 0, "round", "diameter"], msg: "gt 0" },
      { loc: ["body", "payload", "requirements", "wires", 1, "round"], msg: "outer below bare" },
    ])).toEqual({ "requirements.wires.0.diameter": "gt 0", "requirements.wires.1": "outer below bare" })
  })
})

describe("parseNum", () => {
  it("accepts plain numbers and one decimal comma", () => {
    expect(parseNum("0.6")).toBe(0.6)
    expect(parseNum("0,6")).toBe(0.6)
    expect(parseNum(" 1e3 ")).toBe(1000)
    expect(parseNum("")).toBe("empty")
  })
  it("rejects partial or ambiguous text", () => {
    for (const t of ["25o", "9,000", "1,2,3", "1.2.3", "0x10", "1,5.2", "abc"]) expect(parseNum(t)).toBe("invalid")
  })
})

describe("validateForm", () => {
  it("passes the defaults", () => expect(validateForm(defaultSearchForm())).toEqual({}))
  it("flags empty required and unparsable fields, allows empty limits", () => {
    const v = defaultSearchForm()
    v.busVoltageV = ""
    v.maxOuterDiameterMm = "25o"
    v.maxMassKg = ""
    v.nCandidates = "1.5"
    expect(validateForm(v)).toEqual({
      "requirements.bus_voltage_v": "Required",
      "requirements.max_outer_diameter_m": "Enter a number",
      "settings.n_candidates": "Enter a whole number",
    })
  })
  it("needs a wire and a current in wire mode, and checks wire fields", () => {
    const v = defaultSearchForm()
    v.windingMode = "wires"
    expect(validateForm(v)).toEqual({
      "requirements.phase_current_a": "Required", "requirements.wires": "Add at least one wire",
    })
    v.phaseCurrentA = "100"
    v.wires = [{ kind: "litz", strand_diameter: "0.1", strands: "", outer_diameter: "x" }]
    expect(validateForm(v)).toEqual({
      "requirements.wires.0.strands": "Required", "requirements.wires.0.outer_diameter": "Enter a number",
    })
  })
})

describe("winding temperature", () => {
  it("is sent from the form, 120 by default", () => {
    expect(toSearchRequest(defaultSearchForm()).requirements.winding_temperature_c).toBe(120)
    const v = { ...defaultSearchForm(), windingTemperatureC: "95" }
    expect(toSearchRequest(v).requirements.winding_temperature_c).toBe(95)
  })
  it("must be a number", () => {
    const v = { ...defaultSearchForm(), windingTemperatureC: "hot" }
    expect(validateForm(v)).toEqual({ "requirements.winding_temperature_c": "Enter a number" })
  })
})
