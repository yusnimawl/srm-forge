import { describe, expect, it } from "vitest"
import { PLAYER_SOURCE, stepFrame } from "./player"

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
