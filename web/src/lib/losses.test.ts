import { describe, expect, it } from "vitest"
import type { components } from "@/api/schema"
import { bestPoint, contourData, envelopeEdge, lossKeyNumbers, ratedPoint, splitBars, svgToMetres } from "./losses"

type R = components["schemas"]["LossesOut"]
type P = components["schemas"]["OperatingLossOut"]

const iron = (h: number) => ({
  stator_pole: { hysteresis: h, classical: 0.1, excess: 0.05 },
  stator_yoke: { hysteresis: h, classical: 0.1, excess: 0.05 },
})
const point = (speed: number, torque: number, eff: number | null, reached = true, ac: number | null = 2): P => ({
  speed_rpm: speed, torque_nm: torque, reached, efficiency: eff,
  copper_dc_w: reached ? 10 : null, copper_ac_w: reached ? ac : null,
  iron: reached ? iron(1) : {}, iron_w: reached ? 2.3 : null,
  beyond_fit_range: false, current_limit: null, iron_uncertainty_rel: null, power_w: null,
  stroke_key: reached ? "k" : "", theta_off: null, theta_on: null,
})
// 2 speeds x 3 torque levels, speed-major; the top level at the top speed is not reached.
const result = (ac: number | null = 2): R => ({
  points: [
    point(1000, 1, 0.8, true, ac), point(1000, 2, 0.85, true, ac), point(1000, 3, 0.9, true, ac),
    point(2000, 1, 0.7, true, ac), point(2000, 2, 0.75, true, ac), point(2000, 3, null, false),
  ],
  speeds_rpm: [1000, 2000], torque_fractions: [0.2, 0.6, 1], n_angles: 60, angle_convergence_rel: null,
  notes: [], srmapp_version: "0.6.0", winding_temperature_c: 120,
})

describe("contourData", () => {
  it("is a torque-level by speed grid in percent with null for unreached points", () => {
    const c = contourData(result())
    expect(c.x).toEqual([1000, 2000])
    expect(c.y).toEqual([0.2, 0.6, 1])
    expect(c.z).toHaveLength(3)
    expect(c.z[0]).toEqual([80, 70])
    expect(c.z[2]).toEqual([90, null])
  })
})

describe("splitBars", () => {
  it("splits by region and the components sum to the total loss of every reached point", () => {
    const r = result()
    const b = splitBars(r)
    expect(b.series.map((s) => s.name)).toEqual(["Copper DC", "Copper AC", "Iron stator pole", "Iron stator yoke"])
    r.points.forEach((p, k) => {
      if (!p.reached) {
        expect(b.totals[k]).toBeNull()
        b.series.forEach((s) => expect(s.values[k]).toBeNull())
        return
      }
      const sum = b.series.reduce((s, c) => s + (c.values[k] ?? 0), 0)
      expect(sum).toBeCloseTo(b.totals[k]!, 12)
      expect(b.totals[k]).toBeCloseTo(p.copper_dc_w! + p.copper_ac_w! + p.iron_w!, 9)
    })
  })
  it("keeps the hysteresis, classical and excess split as hover text", () => {
    const h = splitBars(result()).series[2].hover!
    expect(h[0]).toBe("hysteresis 1 W, classical 0.1 W, excess 0.05 W")
    expect(h[5]).toBe("")
  })
  it("counts missing AC copper as zero", () => {
    const b = splitBars(result(null))
    expect(b.series[1].values[0]).toBe(0)
    expect(b.totals[0]).toBeCloseTo(10 + 2.3, 9)
  })
})

describe("lossKeyNumbers and envelopeEdge", () => {
  it("gives the best efficiency and the rated-point loss", () => {
    const k = lossKeyNumbers(result())
    expect(k.best?.efficiency).toBe(0.9)
    expect(k.rated?.totalW).toBeCloseTo(14.3, 9)
    expect(lossKeyNumbers({ ...result(), points: result().points.map((p) => ({ ...p, reached: false })) })).toEqual({ best: null, rated: null })
  })
  it("takes the top reached torque level per speed", () => {
    expect(envelopeEdge(result())).toEqual({ x: [1000, 2000], y: [1, 0.6] })
  })
})

describe("picking points", () => {
  it("finds the best efficiency", () => {
    expect(bestPoint(result())).toBe(2)
  })
  it("rated is the highest-speed reached point at the top torque level", () => {
    expect(ratedPoint(result())).toBe(2)
    const r = result()
    r.points[5] = point(2000, 3, 0.6)
    expect(ratedPoint(r)).toBe(5)
  })
})

describe("svgToMetres", () => {
  const box = { left: 10, top: 20, width: 200, height: 200 }
  const vb: [number, number, number, number] = [-50, -50, 100, 100]
  it("maps the box centre to the origin and flips y", () => {
    expect(svgToMetres(box, vb, 110, 120)).toEqual({ x: 0, y: 0 })
    const right = svgToMetres(box, vb, 210, 120)
    expect(right.x).toBeCloseTo(0.05, 12)
    expect(right.y).toBeCloseTo(0, 12)
    const top = svgToMetres(box, vb, 110, 20)
    expect(top.y).toBeCloseTo(0.05, 12)
  })
  it("allows for the letterbox of a non-square box", () => {
    const wide = { left: 0, top: 0, width: 400, height: 200 }
    expect(svgToMetres(wide, vb, 200, 100).x).toBeCloseTo(0, 12)
    expect(svgToMetres(wide, vb, 300, 100).x).toBeCloseTo(0.05, 12)
  })
})
