import { describe, expect, it } from "vitest"
import { srmGlyph, spinnerFrame, SET_SECONDS, MORPH_SECONDS } from "./srmGlyph"

describe("srmGlyph", () => {
  it("gives 8 stator and 6 rotor poles at 45 and 60 degree steps", () => {
    const g = srmGlyph(8, 6)
    expect(g.stator).toHaveLength(8)
    expect(g.rotor).toHaveLength(6)
    expect(g.stator.map((r) => r.angle)).toEqual([0, 45, 90, 135, 180, 225, 270, 315])
    expect(g.rotor.map((r) => r.angle)).toEqual([0, 60, 120, 180, 240, 300])
  })

  it("places stator poles at r 26-41 and rotor poles at r 0-24", () => {
    const g = srmGlyph(8, 6)
    expect(g.stator[0].x).toBe(26)
    expect(g.stator[0].width).toBe(15)
    expect(g.rotor[0].x).toBe(0)
    expect(g.rotor[0].width).toBe(24)
  })

  it("scales the pole width and not the radial extent", () => {
    const full = srmGlyph(8, 6, 1)
    const half = srmGlyph(8, 6, 0.5)
    expect(half.stator[0].height).toBeCloseTo(full.stator[0].height / 2)
    expect(half.stator[0].width).toBe(full.stator[0].width)
    expect(half.rotor[0].y).toBeCloseTo(full.rotor[0].y / 2)
  })
})

describe("spinnerFrame", () => {
  it("turns the stator clockwise and the rotor counter-clockwise", () => {
    const a = spinnerFrame(0.5)
    const b = spinnerFrame(1.5)
    expect(b.statorAngle - a.statorAngle).toBeCloseTo(30)
    expect(b.rotorAngle - a.rotorAngle).toBeCloseTo(-80)
  })

  it("steps 6/4, 8/6, 12/8 and shrinks to nothing between sets", () => {
    expect(spinnerFrame(1).poles).toEqual([6, 4])
    expect(spinnerFrame(SET_SECONDS + 1).poles).toEqual([8, 6])
    expect(spinnerFrame(2 * SET_SECONDS + 1).poles).toEqual([12, 8])
    expect(spinnerFrame(3 * SET_SECONDS + 1).poles).toEqual([6, 4])
    expect(spinnerFrame(1).scale).toBe(1)
    expect(spinnerFrame(SET_SECONDS).scale).toBe(0)
    expect(spinnerFrame(SET_SECONDS - MORPH_SECONDS / 2).scale).toBeCloseTo(0.5)
    expect(spinnerFrame(MORPH_SECONDS / 2).scale).toBeCloseTo(0.5)
  })
})
