import { describe, expect, it } from "vitest"
import { compareRows } from "./compare"

describe("compareRows", () => {
  it("computes the change and the relative change", () => {
    const [r] = compareRows([{ name: "Peak torque", unit: "N·m", before: 10, after: 11 }])
    expect(r.delta).toBeCloseTo(1)
    expect(r.deltaPct).toBeCloseTo(10)
  })
  it("uses a null change when a value is missing", () => {
    const [a, b] = compareRows([
      { name: "a", unit: "", before: null, after: 1 },
      { name: "b", unit: "", before: 1, after: null },
    ])
    expect([a.delta, a.deltaPct, b.delta, b.deltaPct]).toEqual([null, null, null, null])
  })
  it("has no relative change from zero", () => {
    const [r] = compareRows([{ name: "a", unit: "", before: 0, after: 2 }])
    expect(r.delta).toBe(2)
    expect(r.deltaPct).toBeNull()
  })
})
