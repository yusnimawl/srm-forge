import { describe, expect, it } from "vitest"
import type { Evaluation, MapArrays, MapCurves } from "@/api/types"
import {
  designFactorTraces,
  inductanceCurves,
  MAX_OVERLAYS,
  performanceSeries,
  torqueCurves,
  type Overlay,
} from "./analysis"

const envelope = {
  speeds_rpm: [1000, 2000, 3000],
  torque: [2, null, 1],
  power: [2000, 4000, null],
  efficiency: [0.9, 0.85, null],
  i_rms: [5, 6, 7],
}
const ev = (e: Partial<typeof envelope> | null = {}) =>
  ({ id: "x", envelope: e && { ...envelope, ...e } }) as unknown as Evaluation
const overlays = (n: number): Overlay[] => Array.from({ length: n }, (_, k) => ({ label: `c${k}`, evaluation: ev() }))

describe("performanceSeries", () => {
  it("converts W to kW and a fraction to percent", () => {
    const s = performanceSeries(ev())
    expect(s.power[0].y[0]).toBeCloseTo(2)
    expect(s.efficiency[0].y[0]).toBeCloseTo(90)
    expect(s.torque[0].y[0]).toBe(2)
    expect(s.current[0].y).toEqual([5, 6, 7])
    expect(s.torque[0].x).toEqual([1000, 2000, 3000])
  })
  it("keeps nulls as null (gaps)", () => {
    const s = performanceSeries(ev())
    expect(s.torque[0].y[1]).toBeNull()
    expect(s.power[0].y[2]).toBeNull()
    expect(s.efficiency[0].y[2]).toBeNull()
  })
  it("overlays differ by colour and cycle the dash style", () => {
    const s = performanceSeries(ev(), overlays(4)).torque
    expect(s).toHaveLength(5)
    expect(s.map((t) => t.line.dash)).toEqual(["solid", "dash", "dot", "solid", "dash"])
    expect(new Set(s.map((t) => t.line.color)).size).toBe(5)
    expect(s[1].name).toBe("c0")
  })
  it("draws at most 6 overlays and skips a case without an envelope", () => {
    expect(performanceSeries(ev(), overlays(9)).torque).toHaveLength(1 + MAX_OVERLAYS)
    const o: Overlay[] = [{ label: "none", evaluation: ev(null) }]
    expect(performanceSeries(ev(), o).torque).toHaveLength(1)
    expect(performanceSeries(ev(null)).torque).toHaveLength(0)
  })
})

const currents = Array.from({ length: 20 }, (_, k) => k)
const map = {
  angles: [0, Math.PI / 180, Math.PI / 90],
  currents,
  psi: [],
  torque: [0, 1, 2].map((a) => currents.map((i) => (a === 1 && i === 5 ? null : a * i))),
} as MapArrays

describe("torqueCurves", () => {
  it("picks at most 6 currents, ends with the largest, skips zero current", () => {
    const t = torqueCurves(map)
    expect(t).toHaveLength(6)
    expect(t[5].name).toBe("19 A")
    expect(t.every((x) => x.name !== "0 A")).toBe(true)
    expect(new Set(t.map((x) => x.name)).size).toBe(6)
    expect(t[5].x[1]).toBeCloseTo(1)
    expect(t[5].y).toEqual([0, 19, 38])
  })
  it("uses all currents when there are few, nulls stay null", () => {
    const small = { ...map, currents: [0, 5], torque: [[0, 1], [0, null], [0, 3]] } as MapArrays
    const t = torqueCurves(small)
    expect(t).toHaveLength(1)
    expect(t[0].y).toEqual([1, null, 3])
  })
})

const curves = {
  currents: [1, 2, 3],
  inductance: [[1e-3, 2e-3, null], [3e-3, 4e-3, 5e-3]],
  la_sat: [1e-3, 2e-3, null],
  lu: [5e-4, 5e-4, 5e-4],
  la_unsat: 3e-3,
  k2: [0.5, 0.75, null],
  b_sp: [0.1, 0.2, 0.3],
  b_sp_k2: [0.05, 0.15, null],
  la_lu: [2, 4, null],
} as MapCurves

describe("inductanceCurves", () => {
  it("L in mH against mechanical degrees, one trace per current", () => {
    const t = inductanceCurves(curves, [0, Math.PI / 180])
    expect(t).toHaveLength(3)
    expect(t[0].x[1]).toBeCloseTo(1)
    expect(t[0].y).toEqual([1, 3])
    expect(t[2].y).toEqual([null, 5])
  })
})

describe("designFactorTraces", () => {
  const cases = [{ label: "a", curves }, { label: "b", curves }]
  it("keeps every series as long as the currents, in UI units", () => {
    const d = designFactorTraces([{ label: "a", curves }])
    for (const t of [...d.inductance, ...d.factors]) expect(t.x).toHaveLength(3)
    const [laSat, lu, laUnsat] = d.inductance
    expect(laSat.y).toEqual([1, 2, null])
    expect(lu.y[0]).toBeCloseTo(0.5)
    expect(laUnsat.y).toEqual([3, 3, 3])
    expect(d.factors.map((t) => t.name)).toEqual(["k2", "B_sp", "B_sp·k2"])
    expect(d.bspK2VsRatio[0].x).toEqual([2, 4, null])
    expect(d.bspK2VsRatio[0].y).toEqual([0.05, 0.15, null])
  })
  it("a missing La_unsat gives gaps, not zeros", () => {
    const d = designFactorTraces([{ label: "a", curves: { ...curves, la_unsat: null } }])
    expect(d.inductance[2].y).toEqual([null, null, null])
  })
  it("overlays: case label in names, colour and dash per case", () => {
    const d = designFactorTraces(cases)
    expect(d.inductance).toHaveLength(6)
    expect(d.inductance[0].name).toBe("a La_sat")
    expect(d.inductance[3].line.dash).toBe("dash")
    expect(d.inductance[3].line.color).not.toBe(d.inductance[0].line.color)
    expect(d.bspK2VsRatio.map((t) => t.line.dash)).toEqual(["solid", "dash"])
  })
  it("skips a case without curves", () => {
    expect(designFactorTraces([{ label: "a", curves: null }]).bspK2VsRatio).toHaveLength(0)
  })
})
