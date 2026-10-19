import { describe, expect, it } from "vitest"
import { defaultIsrHz, defaultScenario, MAX_STEPS, rpmToRadS, scenarioErrors, scopesFromWire } from "./control"

/** Packs arrays like srmweb/frames.py: u32 header length, JSON header, 8-byte aligned data. */
function pack(meta: unknown, arrays: Record<string, Float32Array>): ArrayBuffer {
  let offset = 0
  const entries = Object.entries(arrays).map(([name, a]) => {
    const e = { name, dtype: "float32", shape: [a.length], offset }
    offset += Math.ceil(a.byteLength / 8) * 8
    return e
  })
  const head = new TextEncoder().encode(JSON.stringify({ meta, arrays: entries }))
  const buf = new ArrayBuffer(4 + head.length + offset)
  new DataView(buf).setUint32(0, head.length, true)
  new Uint8Array(buf, 4, head.length).set(head)
  // the data offset is 4 + head.length, which need not be 4-aligned, so copy bytes
  entries.forEach((e) => new Uint8Array(buf, 4 + head.length + e.offset, e.shape[0] * 4).set(new Uint8Array(arrays[e.name].buffer)))
  return buf
}

describe("scopesFromWire", () => {
  it("pairs t.<name> with y.<name>", () => {
    const buf = pack({ n_phases: 1, controller: "tsf" }, {
      "t.i.0": new Float32Array([0, 1, 2]), "y.i.0": new Float32Array([5, 6, 7]),
      "t.torque": new Float32Array([0, 1]), "y.torque": new Float32Array([1, 2]),
    })
    const { meta, channels } = scopesFromWire(buf)
    expect(meta.controller).toBe("tsf")
    expect(Object.keys(channels).sort()).toEqual(["i.0", "torque"])
    expect(Array.from(channels["i.0"].y)).toEqual([5, 6, 7])
    expect(Array.from(channels.torque.t)).toEqual([0, 1])
  })
})

describe("scenarioErrors", () => {
  it("accepts the default", () => expect(scenarioErrors(defaultScenario(48))).toEqual({}))
  it("flags duration / dt over MAX_STEPS", () => {
    const s = { ...defaultScenario(), duration: (MAX_STEPS + 10) * 1e-6, dt: 1e-6 }
    expect(scenarioErrors(s).duration).toMatch(/exceed/)
  })
  it("flags non-positive times", () => {
    const e = scenarioErrors({ ...defaultScenario(), duration: 0, dt: -1, inertia: 0, pwm_hz: 0 })
    expect(Object.keys(e)).toEqual(expect.arrayContaining(["duration", "dt", "inertia", "pwm_hz"]))
  })
  it("flags a pwm rate above 1 / dt", () => {
    expect(scenarioErrors({ ...defaultScenario(), dt: 1e-4, pwm_hz: 20000 }).pwm_hz).toBeDefined()
  })
})

describe("units", () => {
  it("converts rpm to rad/s", () => expect(rpmToRadS(60)).toBeCloseTo(2 * Math.PI))
})

describe("defaults from the case", () => {
  it("commands 30 % of the peak torque at the base speed", () => {
    const s = defaultScenario(48, 4.37, 3000)
    expect(s.command_value).toBe(1.3)
    expect(s.speed_rpm).toBe(3000)
    expect(defaultScenario(48).command_value).toBe(0)
    expect(defaultScenario(48).speed_rpm).toBe(1000)
  })
  it("uses a 50 kHz ISR for hysteresis only", () => {
    expect(defaultIsrHz("hysteresis")).toBe(50000)
    expect(defaultIsrHz("tsf")).toBeNull()
  })
})
