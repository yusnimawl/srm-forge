import { describe, expect, it } from "vitest";
import { decode, frameFromWire, framesFromWire, meshFromWire } from "./fieldWire";

function pack(meta: unknown, arrays: { name: string; dtype: string; shape: number[]; bytes: Uint8Array }[]): ArrayBuffer {
  let offset = 0;
  const entries = arrays.map((a) => {
    const e = { name: a.name, dtype: a.dtype, shape: a.shape, offset };
    offset += Math.ceil(a.bytes.length / 8) * 8;
    return e;
  });
  let header = JSON.stringify({ meta, arrays: entries });
  while ((4 + header.length) % 8) header += " ";
  const out = new Uint8Array(4 + header.length + offset);
  new DataView(out.buffer).setUint32(0, header.length, true);
  out.set(new TextEncoder().encode(header), 4);
  arrays.forEach((a, i) => out.set(a.bytes, 4 + header.length + entries[i].offset));
  return out.buffer;
}
const f32 = (v: number[]) => new Uint8Array(new Float32Array(v).buffer);
const u32 = (v: number[]) => new Uint8Array(new Uint32Array(v).buffer);

describe("decode", () => {
  it("reads meta and arrays", () => {
    const buf = pack({ k: 1 }, [
      { name: "x", dtype: "float32", shape: [2, 2], bytes: f32([1, 2, 3, 4.5]) },
      { name: "y", dtype: "uint8", shape: [3], bytes: new Uint8Array([7, 8, 9]) },
    ]);
    const d = decode(buf);
    expect(d.meta).toEqual({ k: 1 });
    expect(Array.from(d.arrays.x.data)).toEqual([1, 2, 3, 4.5]);
    expect(d.arrays.x.shape).toEqual([2, 2]);
    expect(Array.from(d.arrays.y.data)).toEqual([7, 8, 9]);
  });
});

describe("typed wrappers", () => {
  it("meshFromWire", () => {
    const buf = pack(
      {
        n_stator_nodes: 1,
        regions: [{ name: "r", kind: "iron", part: "stator", phase: null, sign: 0 }],
        b_last: 2,
        n_rotor_poles: 6,
        aligned_angle: 0.5,
        unaligned_angle: 0.1,
        winding_current: 3,
        i_max: 4,
      },
      [
        { name: "nodes", dtype: "float32", shape: [3, 2], bytes: f32([0, 0, 1, 0, 0, 1]) },
        { name: "triangles", dtype: "uint32", shape: [1, 3], bytes: u32([0, 1, 2]) },
        { name: "region", dtype: "uint8", shape: [1], bytes: new Uint8Array([0]) },
        { name: "probe.stator_pole", dtype: "uint32", shape: [1], bytes: u32([0]) },
        { name: "probe.stator_yoke", dtype: "uint32", shape: [1], bytes: u32([0]) },
        { name: "probe.rotor_pole", dtype: "uint32", shape: [1], bytes: u32([0]) },
      ],
    );
    const m = meshFromWire(buf);
    expect(m.nStatorNodes).toBe(1);
    expect(m.nRotorPoles).toBe(6);
    expect(m.iMax).toBe(4);
    expect(m.nodes.length).toBe(6);
    expect(Array.from(m.probes.rotor_pole)).toEqual([0]);
  });

  it("frameFromWire and framesFromWire", () => {
    const one = frameFromWire(
      pack({ angle: 0.3, current_a: 5, psi: 0.1, torque: 2, status: "ok", probes: { stator_pole: 1.5 } }, [
        { name: "band", dtype: "uint32", shape: [1, 3], bytes: u32([0, 1, 2]) },
        { name: "b", dtype: "float32", shape: [1], bytes: f32([1]) },
        { name: "a", dtype: "float32", shape: [3], bytes: f32([1, 2, 3]) },
      ]),
    );
    expect(one.currentA).toBe(5);
    expect(one.probes).toEqual({ stator_pole: 1.5 });
    expect(Array.from(one.a)).toEqual([1, 2, 3]);

    const many = framesFromWire(
      pack(
        {
          case_id: "c",
          current_a: 5,
          angles: [0.1, 0.2],
          psi: [1, 2],
          torque: [3, 4],
          status: ["ok", "ok"],
          probes: { stator_pole: [7, 8] },
        },
        [0, 1].flatMap((n) => [
          { name: `band.${n}`, dtype: "uint32", shape: [1, 3], bytes: u32([0, 1, 2]) },
          { name: `b.${n}`, dtype: "float32", shape: [1], bytes: f32([n]) },
          { name: `a.${n}`, dtype: "float32", shape: [3], bytes: f32([n, n, n]) },
        ]),
      ),
    );
    expect(many.frames).toHaveLength(2);
    expect(many.frames[1]).toMatchObject({ angle: 0.2, psi: 2, torque: 4, currentA: 5, probes: { stator_pole: 8 } });
    expect(many.frames[1].b[0]).toBe(1);
  });
});
