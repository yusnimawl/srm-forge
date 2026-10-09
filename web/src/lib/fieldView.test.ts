import { describe, expect, it } from "vitest";
import type { FieldFrameData, FieldMeshData } from "./fieldWire";
import { allTriangles, animateEstimate, electricalDeg, pickTriangle, positions, regionEdges } from "./fieldView";

const mesh = {
  nodes: new Float32Array([1, 0, 0, 0, 1, 0]),
  nStatorNodes: 1,
  triangles: new Uint32Array([0, 1, 2]),
} as unknown as FieldMeshData;

describe("fieldView", () => {
  it("positions rotate rotor nodes counter-clockwise", () => {
    const p = positions(mesh, Math.PI / 2);
    expect([p[0], p[1]]).toEqual([1, 0]);
    expect(p[2]).toBeCloseTo(0);
    expect(p[3]).toBeCloseTo(0);
    expect(p[4]).toBeCloseTo(0);
    expect(p[5]).toBeCloseTo(1);
    const q = positions({ ...mesh, nodes: new Float32Array([5, 5, 1, 0]) } as FieldMeshData, Math.PI / 2);
    expect(q[2]).toBeCloseTo(0);
    expect(q[3]).toBeCloseTo(1);
  });

  it("allTriangles appends the band", () => {
    const t = allTriangles(mesh, { band: new Uint32Array([2, 1, 0]) } as FieldFrameData);
    expect(Array.from(t)).toEqual([0, 1, 2, 2, 1, 0]);
  });

  it("pickTriangle", () => {
    const xy = new Float32Array([0, 0, 1, 0, 0, 1]);
    const t = new Uint32Array([0, 1, 2]);
    expect(pickTriangle(xy, t, 0.2, 0.2)).toBe(0);
    expect(pickTriangle(xy, t, 0.8, 0.8)).toBe(-1);
    expect(pickTriangle(xy, t, 0.5, 0)).toBe(0);
  });

  it("regionEdges includes shared and boundary edges", () => {
    const tris = new Uint32Array([0, 1, 2, 0, 2, 3]);
    const e = Array.from(regionEdges(tris, new Uint8Array([0, 1])));
    const pairs = new Set<string>();
    for (let i = 0; i < e.length; i += 2) pairs.add([e[i], e[i + 1]].sort().join("-"));
    expect(pairs.has("0-2")).toBe(true);
    expect(pairs.size).toBe(5);
    expect(regionEdges(tris, new Uint8Array([0, 0])).length).toBe(8);
  });

  it("electricalDeg", () => {
    expect(electricalDeg(0, 6)).toBeCloseTo(-180);
    expect(electricalDeg(Math.PI / 6, 6)).toBeCloseTo(0);
  });

  it("animateEstimate", () => {
    expect(animateEstimate(36)).toBe("36 solves, about 2–3 min");
    expect(animateEstimate(12)).toBe("12 solves, about 1 min");
  });
});
