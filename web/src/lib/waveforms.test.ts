import { describe, expect, it } from "vitest"
import type { Evaluation } from "@/api/types"
import { defaultSpeedIndex, waveformSeries } from "./waveforms"

const wf = {
  theta: [0, 1, 2],
  theta_el: [0, 90, 180],
  current: [[0, 0, 0], [1, 2, 3], [4, 5, 6]],
  psi: [[0, 0, 0], [0.001, 0.002, 0.003], [0, 0, 0]],
  voltage: [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
  torque: [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
  line: [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
}
const ev = (waveforms: unknown = wf) =>
  ({
    envelope: { speeds_rpm: [100, 1500, 3000], power: [1, 5, 9], waveforms },
    curves: { currents: [5, 10], la_sat: [0.002, 0.003], lu: [0.0005, 0.0006] },
  }) as unknown as Evaluation

describe("waveformSeries", () => {
  it("takes the speed row against electrical angle", () => {
    const s = waveformSeries(ev(), 1)!
    expect(s.current[0].y).toEqual([1, 2, 3])
    expect(s.current[0].x).toEqual([0, 90, 180])
    expect(s.psi[0].y[2]).toBeCloseTo(3)
  })
  it("builds the loop with aligned and unaligned lines from the origin", () => {
    const s = waveformSeries(ev(), 1)!
    expect(s.loop).toHaveLength(3)
    const al = s.loop.find((t) => t.name === "aligned")!
    expect([al.x[0], al.y[0]]).toEqual([0, 0])
    expect(al.y[1]).toBeCloseTo(0.002 * 5 * 1e3)
    expect(s.loop[0].x).toEqual([1, 2, 3])
  })
  it("handles a zero row and a missing waveform", () => {
    expect(waveformSeries(ev(), 0)!.current[0].y).toEqual([0, 0, 0])
    expect(waveformSeries(ev(null), 0)).toBeNull()
  })
})

describe("defaultSpeedIndex", () => {
  it("picks the speed nearest base, else the largest power", () => {
    expect(defaultSpeedIndex(ev(), 1500)).toBe(1)
    expect(defaultSpeedIndex(ev(), 2900)).toBe(2)
    expect(defaultSpeedIndex(ev())).toBe(2)
  })
})
