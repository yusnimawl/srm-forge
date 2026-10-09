import type { FieldFrameData, FieldMeshData } from "./fieldWire";

/** Node coordinates with the rotor (index >= nStatorNodes) turned counter-clockwise by `angle`. */
export function positions(mesh: FieldMeshData, angle: number): Float32Array {
  const out = new Float32Array(mesh.nodes);
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  for (let i = mesh.nStatorNodes; i < out.length / 2; i++) {
    const x = mesh.nodes[2 * i];
    const y = mesh.nodes[2 * i + 1];
    out[2 * i] = c * x - s * y;
    out[2 * i + 1] = s * x + c * y;
  }
  return out;
}

/** The static triangles followed by the band. */
export function allTriangles(mesh: FieldMeshData, frame: FieldFrameData): Uint32Array {
  const out = new Uint32Array(mesh.triangles.length + frame.band.length);
  out.set(mesh.triangles);
  out.set(frame.band, mesh.triangles.length);
  return out;
}

/** Index of the first triangle containing (x, y), edges included; -1 when none. */
export function pickTriangle(xy: Float32Array, tris: Uint32Array, x: number, y: number): number {
  const eps = 1e-9;
  for (let t = 0; t < tris.length / 3; t++) {
    const [a, b, c] = [tris[3 * t], tris[3 * t + 1], tris[3 * t + 2]];
    const x0 = xy[2 * a], y0 = xy[2 * a + 1];
    const d = (xy[2 * b + 1] - xy[2 * c + 1]) * (x0 - xy[2 * c]) + (xy[2 * c] - xy[2 * b]) * (y0 - xy[2 * c + 1]);
    if (d === 0) continue;
    const l1 = ((xy[2 * b + 1] - xy[2 * c + 1]) * (x - xy[2 * c]) + (xy[2 * c] - xy[2 * b]) * (y - xy[2 * c + 1])) / d;
    const l2 = ((xy[2 * c + 1] - y0) * (x - xy[2 * c]) + (x0 - xy[2 * c]) * (y - xy[2 * c + 1])) / d;
    if (l1 >= -eps && l2 >= -eps && 1 - l1 - l2 >= -eps) return t;
  }
  return -1;
}

/** Node pairs of the edges between two regions, plus the boundary edges. */
export function regionEdges(tris: Uint32Array, region: Uint8Array): Uint32Array {
  const seen = new Map<number, { a: number; b: number; r: number; n: number; differ: boolean }>();
  for (let t = 0; t < tris.length / 3; t++) {
    const r = region[t] ?? 255; // triangles beyond `region` (the band) form one region of their own
    for (let k = 0; k < 3; k++) {
      const p = tris[3 * t + k];
      const q = tris[3 * t + ((k + 1) % 3)];
      const [a, b] = p < q ? [p, q] : [q, p];
      const key = a * 4294967296 + b;
      const e = seen.get(key);
      if (e) {
        e.n++;
        if (e.r !== r) e.differ = true;
      } else seen.set(key, { a, b, r, n: 1, differ: false });
    }
  }
  const out: number[] = [];
  for (const e of seen.values()) if (e.n === 1 || e.differ) out.push(e.a, e.b);
  return new Uint32Array(out);
}

/** Electrical degrees from the unaligned position (angle - pi / N_r) * N_r. */
export function electricalDeg(angle: number, nRotorPoles: number): number {
  return ((angle - Math.PI / nRotorPoles) * nRotorPoles * 180) / Math.PI;
}

export function animateEstimate(n: number): string {
  const lo = Math.max(1, Math.round((n * 5) / 60));
  const hi = Math.max(1, Math.round((n * 8) / 60));
  return `${n} solves, about ${lo === hi ? `${lo}` : `${lo}–${hi}`} min`;
}
