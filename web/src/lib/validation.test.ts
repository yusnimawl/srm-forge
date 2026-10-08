import { describe, expect, it } from "vitest"
import { atScale, turnsScale } from "./validation"

describe("turnsScale", () => {
  it("is turns over paths times the reference turns", () => {
    expect(turnsScale({ turns: 60, paths: 1 }, 20)).toBe(3)
    expect(turnsScale({ turns: 60, paths: 2 }, 20)).toBe(1.5)
    expect(turnsScale({ turns: 20, paths: 1 }, 20)).toBe(1)
  })
})

describe("atScale", () => {
  it("scales La and Lu by k squared, psi by k, and leaves torque", () => {
    const v = { la: 2, lu: 1, peak_torque: 5, psi_max: 0.5, other: 7 }
    expect(atScale(v, 3)).toEqual({ la: 18, lu: 9, peak_torque: 5, psi_max: 1.5, other: 7 })
  })
  it("keeps a missing value missing", () => {
    expect(atScale({ la: null, psi_max: 2 }, 2)).toEqual({ la: null, psi_max: 4 })
  })
})
