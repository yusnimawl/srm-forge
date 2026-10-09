import { describe, expect, it } from "vitest"
import { frameInterval, nextFrame, probeSeries } from "./playback"
import { electricalDeg } from "./fieldView"
import type { FieldFrameData } from "./fieldWire"

const frame = (angle: number, p: number): FieldFrameData => ({
  angle, currentA: 5, psi: 0, torque: 0, status: "ok",
  probes: { stator_pole: p, stator_yoke: p / 2, rotor_pole: p / 4 },
  band: new Uint32Array(), b: new Float32Array(), a: new Float32Array(),
})

describe("playback", () => {
  it("wraps the frame index", () => {
    expect(nextFrame(35, 36)).toBe(0)
    expect(nextFrame(3, 36)).toBe(4)
  })
  it("gives ms per frame", () => {
    expect(frameInterval(1)).toBe(100)
    expect(frameInterval(2)).toBe(50)
    expect(frameInterval(0.5)).toBe(200)
  })
  it("builds three probe traces against electrical degrees", () => {
    const t = probeSeries([frame(0.1, 2), frame(0.2, 4)], 6)
    expect(t.map((s) => s.name)).toEqual(["stator pole", "stator yoke", "rotor pole"])
    expect(t[0].x).toEqual([0.1, 0.2].map((a) => electricalDeg(a, 6)))
    expect(t[0].y).toEqual([2, 4])
    expect(t[2].y).toEqual([0.5, 1])
  })
})
