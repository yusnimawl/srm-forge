import { describe, expect, it } from "vitest"
import { UNIT_LABEL, fromSI, toSI, type Unit } from "./units"

const ALL = Object.keys(UNIT_LABEL) as Unit[]

describe("units", () => {
  it("converts to SI", () => {
    expect(toSI(160, "mm")).toBeCloseTo(0.16, 12)
    expect(toSI(90, "deg")).toBeCloseTo(Math.PI / 2, 12)
    expect(toSI(5, "kW")).toBe(5000)
  })
  it("converts from SI", () => {
    expect(fromSI(2e7, "A/mm2")).toBe(20)
    expect(fromSI(0.001, "mH")).toBeCloseTo(1, 12)
  })
  it("round-trips every unit", () => {
    for (const u of ALL) expect(fromSI(toSI(12.5, u), u)).toBeCloseTo(12.5, 9)
  })
  it("labels", () => {
    expect(UNIT_LABEL["A/mm2"]).toBe("A/mm²")
    expect(UNIT_LABEL.Nm).toBe("N·m")
  })
})
