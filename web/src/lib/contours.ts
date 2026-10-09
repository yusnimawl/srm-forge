/** n levels evenly spaced strictly inside (min, max); none when the field is flat. */
export function contourLevels(values: Float32Array, n = 20): number[] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!(hi > lo)) return [];
  return Array.from({ length: n }, (_, k) => lo + ((hi - lo) * (k + 1)) / (n + 1));
}

/** Marching triangles on P1 values; x0, y0, x1, y1 per segment. A vertex at the level counts as above. */
export function contourSegments(xy: Float32Array, tris: Uint32Array, values: Float32Array, levels: number[]): Float32Array {
  const out: number[] = [];
  for (let t = 0; t < tris.length; t += 3) {
    const v = [tris[t], tris[t + 1], tris[t + 2]];
    for (const level of levels) {
      const up = v.map((i) => values[i] >= level);
      if (up[0] === up[1] && up[1] === up[2]) continue;
      // exactly one vertex sits on the other side from the two others; the contour crosses its two edges
      const odd = up[0] !== up[1] ? (up[0] !== up[2] ? 0 : 1) : 2;
      const p = v[odd];
      const pts: number[] = [];
      for (const q of [v[(odd + 1) % 3], v[(odd + 2) % 3]]) {
        const s = (level - values[p]) / (values[q] - values[p]);
        pts.push(xy[2 * p] + s * (xy[2 * q] - xy[2 * p]), xy[2 * p + 1] + s * (xy[2 * q + 1] - xy[2 * p + 1]));
      }
      if (pts[0] !== pts[2] || pts[1] !== pts[3]) out.push(...pts); // a lone vertex at the level touches, it is not a segment
    }
  }
  return new Float32Array(out);
}
