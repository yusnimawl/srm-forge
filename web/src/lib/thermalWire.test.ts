import { describe, expect, it } from "vitest"
import { buildScalarScene } from "./fieldGl"
import { inferno } from "./inferno"
import { decodeThermalFields } from "./thermalWire"

function pack(meta: unknown, arrays: { name: string; dtype: string; shape: number[]; bytes: Uint8Array }[]): ArrayBuffer {
  let offset = 0
  const entries = arrays.map((a) => {
    const e = { name: a.name, dtype: a.dtype, shape: a.shape, offset }
    offset += Math.ceil(a.bytes.length / 8) * 8
    return e
  })
  let header = JSON.stringify({ meta, arrays: entries })
  while ((4 + header.length) % 8) header += " "
  const out = new Uint8Array(4 + header.length + offset)
  new DataView(out.buffer).setUint32(0, header.length, true)
  out.set(new TextEncoder().encode(header), 4)
  arrays.forEach((a, i) => out.set(a.bytes, 4 + header.length + entries[i].offset))
  return out.buffer
}
const f32 = (v: number[]) => new Uint8Array(new Float32Array(v).buffer)

describe("decodeThermalFields", () => {
  it("splits the per-speed rows", () => {
    const buf = pack(
      { rpm: [1000, 2000], end_winding_steady_c: [100, null], end_winding_peak_c: [120, 130], kinds: ["coil", "iron"] },
      [
        { name: "nodes", dtype: "float32", shape: [3, 2], bytes: f32([0, 0, 1, 0, 0, 1]) },
        { name: "triangles", dtype: "uint32", shape: [1, 3], bytes: new Uint8Array(new Uint32Array([0, 1, 2]).buffer) },
        { name: "kind", dtype: "uint8", shape: [1], bytes: new Uint8Array([1]) },
        { name: "steady", dtype: "float32", shape: [2, 3], bytes: f32([10, 20, 30, 11, 21, 31]) },
        { name: "peak", dtype: "float32", shape: [2, 3], bytes: f32([1, 2, 3, NaN, NaN, NaN]) },
      ],
    )
    const d = decodeThermalFields(buf)
    expect(d.rpm).toEqual([1000, 2000])
    expect(d.kinds).toEqual(["coil", "iron"])
    expect(d.steady).toHaveLength(2)
    expect(Array.from(d.steady[1])).toEqual([11, 21, 31])
    expect(Number.isNaN(d.peak[1][0])).toBe(true)
    expect(d.endWindingSteadyC).toEqual([100, null])
    expect(Array.from(d.triangles)).toEqual([0, 1, 2])
  })
})

describe("buildScalarScene", () => {
  const xy = new Float32Array([0, 0, 1, 0, 0, 1, 1, 1])
  const tris = new Uint32Array([0, 1, 2, 1, 3, 2])
  const region = new Uint8Array([0, 1])
  it("colours the extremes with inferno ends and keeps the scale", () => {
    const s = buildScalarScene(xy, tris, region, new Float32Array([20, 60, 40, 60]), 20, 60)
    const rgb = (k: number) => Array.from(s.triRgb.slice(3 * k, 3 * k + 3)).map((v) => Math.round(v * 255))
    expect(rgb(0)).toEqual(Array.from(inferno(0)))
    expect(rgb(1)).toEqual(Array.from(inferno(1)))
    expect(s.bMax).toBe(60)
    expect(s.lines[0].xy.length).toBeGreaterThan(0)
  })
  it("draws NaN nodes in the background colour", () => {
    const s = buildScalarScene(xy, tris, region, new Float32Array([NaN, 60, 40, 60]), 20, 60)
    expect(Array.from(s.triRgb.slice(0, 3))).not.toEqual(Array.from(inferno(0)).map((v) => v / 255))
    expect(Number.isNaN(s.triRgb[0])).toBe(false)
  })
})
