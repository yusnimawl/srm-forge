import { describe, expect, it } from "vitest"
import { pickAngles, psiCurves, torqueGrid } from "./mapCurves"

const map = {
  angles: [0, Math.PI / 180, Math.PI / 90],
  currents: [0, 10],
  psi: [[0, 0.001], [0, 0.002], [0, 0.003]],
  torque: [[0, 1], [0, 2], [0, 3]],
}

describe("mapCurves", () => {
  it("one curve per angle, degrees and mWb", () => {
    const c = psiCurves(map)
    expect(c).toHaveLength(3)
    expect(c[1].angleDeg).toBeCloseTo(1)
    expect(c[1].i).toEqual([0, 10])
    expect(c[2].psi_mWb[1]).toBeCloseTo(3)
  })
  it("torqueGrid keeps angles x currents", () => {
    const g = torqueGrid(map)
    expect(g.angleDeg).toHaveLength(3)
    expect(g.i).toEqual([0, 10])
    expect(g.torque[2]).toEqual([0, 3])
  })
  it("pickAngles: aligned..unaligned half only, both ends, max 6", () => {
    const angles = Array.from({ length: 41 }, (_, k) => (k * Math.PI) / 40)
    const idx = pickAngles(angles, Math.PI / 2)
    expect(idx).toEqual([0, 4, 8, 12, 16, 20])
    expect(pickAngles([0, 1, 2], 1)).toEqual([0, 1])
  })
  it("pickAngles: symmetric 48-angle map gives no mirrored duplicates", () => {
    const n = 48
    const angles = Array.from({ length: n }, (_, k) => (k * 2 * Math.PI) / (n - 1))
    const idx = pickAngles(angles, Math.PI)
    expect(idx).toHaveLength(6)
    expect(idx[0]).toBe(0)
    expect(idx[5]).toBe(23)
    const psi = (k: number) => Math.min(k, n - 1 - k)
    expect(new Set(idx.map(psi)).size).toBe(6)
  })
})
