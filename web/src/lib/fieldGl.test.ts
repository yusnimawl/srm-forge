import { describe, expect, it } from "vitest"
import { viewMatrix } from "./fieldGl"

const sq = { minX: 0, minY: 0, maxX: 1, maxY: 1 }
const clip = (m: Float32Array, x: number, y: number) => [m[0] * x + m[3] * y + m[6], m[1] * x + m[4] * y + m[7]]

describe("viewMatrix", () => {
  it("maps the centre to the origin and keeps the aspect ratio", () => {
    const m = viewMatrix(sq, 200, 100, 1, [0, 0])
    expect(clip(m, 0.5, 0.5)).toEqual([0, 0])
    expect(clip(m, 0, 0.5)[0]).toBeCloseTo(-0.5)
    expect(clip(m, 1, 0.5)[0]).toBeCloseTo(0.5)
    expect(clip(m, 0.5, 1)[1]).toBeCloseTo(1)
  })
  it("zoom 2 halves the visible span, pan shifts in clip units", () => {
    const m = viewMatrix(sq, 200, 100, 2, [0.25, -0.1])
    expect(clip(m, 1, 0.5)[0]).toBeCloseTo(1.25)
    expect(clip(m, 0.5, 0.5)[1]).toBeCloseTo(-0.1)
  })
})
