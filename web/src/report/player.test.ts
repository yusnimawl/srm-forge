import { describe, expect, it } from "vitest"
import { PLAYER_SOURCE, PRINT_AXIS, PRINT_LINE_COLORS, SCREEN_AXIS, stepFrame, themeUpdate } from "./player"

describe("stepFrame", () => {
  it("wraps both ways", () => {
    expect(stepFrame(35, 36, 1)).toBe(0)
    expect(stepFrame(0, 36, -1)).toBe(35)
    expect(stepFrame(3, 36, 1)).toBe(4)
  })
})

describe("PLAYER_SOURCE", () => {
  it("is self-contained", () => {
    expect(PLAYER_SOURCE).not.toMatch(/\bimport\b|fetch|http/)
  })
  it("embeds a working stepFrame", () => {
    const m = /var stepFrame = (\(function[\s\S]*?\));\n/.exec(PLAYER_SOURCE)
    expect(m).not.toBeNull()
    const f = new Function(`return ${m![1]}`)() as typeof stepFrame
    expect(f(35, 36, 1)).toBe(0)
    expect(f(0, 36, -1)).toBe(35)
  })
  it("parses", () => {
    expect(() => new Function(PLAYER_SOURCE)).not.toThrow()
  })
})

describe("print theme", () => {
  it("lightens only the axes a layout has", () => {
    const u = themeUpdate({ xaxis: {}, yaxis: {} }, PRINT_AXIS)
    expect(u["xaxis.gridcolor"]).toBe(PRINT_AXIS.grid)
    expect(u["font.color"]).toBe("#333333")
    expect(Object.keys(u).some((k) => k.startsWith("yaxis2"))).toBe(false)
    expect(themeUpdate({ xaxis: {}, yaxis2: {} }, SCREEN_AXIS)["yaxis2.color"]).toBe(SCREEN_AXIS.font)
  })
  it("has a print colour per series colour, no hue of the screen palette", () => {
    expect(PRINT_LINE_COLORS).toHaveLength(7)
    PRINT_LINE_COLORS.forEach((c) => {
      const [r, g, b] = [1, 3, 5].map((k) => parseInt(c.slice(k, k + 2), 16))
      expect(b > r + 40 && b > g + 40).toBe(false)
    })
  })
  it("handles print events and guards JSON", () => {
    expect(PLAYER_SOURCE).toContain("beforeprint")
    expect(PLAYER_SOURCE).toContain("afterprint")
    expect(PLAYER_SOURCE).toMatch(/try \{ return JSON\.parse/)
  })
})
