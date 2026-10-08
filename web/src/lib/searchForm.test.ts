import { describe, expect, it } from "vitest"
import { defaultSearchForm, fieldErrors, toSearchRequest } from "./searchForm"

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
  it("maps a model-level requirements error to requirements", () => {
    expect(fieldErrors([{ loc: ["body", "payload", "requirements"], msg: "power disagrees", type: "t" }]))
      .toEqual({ requirements: "power disagrees" })
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
