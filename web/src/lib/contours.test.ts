import { describe, expect, it } from "vitest";
import { contourLevels, contourSegments } from "./contours";

const xy = new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]);
const tris = new Uint32Array([0, 1, 2, 0, 2, 3]);
const vals = new Float32Array([0, 1, 1, 0]);

describe("contours", () => {
  it("levels are strictly inside", () => {
    const l = contourLevels(new Float32Array([0, 1]), 4);
    expect(l.map((x) => +x.toFixed(6))).toEqual([0.2, 0.4, 0.6, 0.8]);
    expect(contourLevels(new Float32Array([2, 2]))).toEqual([]);
  });

  it("segments join along x = 0.5", () => {
    const s = contourSegments(xy, tris, vals, [0.5]);
    expect(s.length).toBe(8);
    for (let i = 0; i < s.length; i += 2) expect(s[i]).toBeCloseTo(0.5);
    const ys = [s[1], s[3], s[5], s[7]].sort();
    expect(ys[0]).toBeCloseTo(0);
    expect(ys[3]).toBeCloseTo(1);
  });

  it("level outside the range gives nothing", () => {
    expect(contourSegments(xy, tris, vals, [2]).length).toBe(0);
    expect(contourSegments(xy, tris, vals, [-1]).length).toBe(0);
  });

  it("level equal to a vertex value makes no degenerate segment", () => {
    const s = contourSegments(xy, tris, vals, [1]);
    for (let i = 0; i < s.length; i += 4) expect(Math.hypot(s[i + 2] - s[i], s[i + 3] - s[i + 1])).toBeGreaterThan(0);
  });
});
