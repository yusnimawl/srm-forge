// Decoder for the binary field frames (src/srmweb/frames.py): uint32 header length, JSON header, 8-byte aligned arrays.

type Data = Float32Array | Uint32Array | Uint8Array;
export type WireArray = { data: Data; shape: number[] };

export function decode(buf: ArrayBuffer): { meta: any; arrays: Record<string, WireArray> } {
  const headerLength = new DataView(buf).getUint32(0, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, headerLength)));
  const base = 4 + headerLength;
  const arrays: Record<string, WireArray> = {};
  for (const e of header.arrays as { name: string; dtype: string; shape: number[]; offset: number }[]) {
    const count = e.shape.reduce((a, b) => a * b, 1);
    const Type = { float32: Float32Array, uint32: Uint32Array, uint8: Uint8Array }[e.dtype];
    if (!Type) throw new Error(`unsupported dtype ${e.dtype}`);
    // slice copies, so the new view starts at byte 0 whatever the source alignment
    const bytes = buf.slice(base + e.offset, base + e.offset + count * Type.BYTES_PER_ELEMENT);
    arrays[e.name] = { data: new Type(bytes), shape: e.shape };
  }
  return { meta: header.meta, arrays };
}

export type FieldRegion = { name: string; kind: string; part: string; phase: string | null; sign: number | null };

export type FieldMeshData = {
  nodes: Float32Array;
  nStatorNodes: number;
  triangles: Uint32Array;
  region: Uint8Array;
  regions: FieldRegion[];
  bLast: number;
  probes: Record<string, Uint32Array>;
  nRotorPoles: number;
  alignedAngle: number;
  unalignedAngle: number;
  windingCurrent: number;
  iMax: number;
};

export type FieldFrameData = {
  angle: number;
  currentA: number;
  psi: number;
  torque: number;
  status: string;
  probes: Record<string, number>;
  band: Uint32Array;
  b: Float32Array;
  a: Float32Array;
};

const f32 = (w: WireArray) => w.data as Float32Array;
const u32 = (w: WireArray) => w.data as Uint32Array;

export function meshFromWire(buf: ArrayBuffer): FieldMeshData {
  const { meta, arrays } = decode(buf);
  const probes: Record<string, Uint32Array> = {};
  for (const name of Object.keys(arrays)) if (name.startsWith("probe.")) probes[name.slice(6)] = u32(arrays[name]);
  return {
    nodes: f32(arrays.nodes),
    nStatorNodes: meta.n_stator_nodes,
    triangles: u32(arrays.triangles),
    region: arrays.region.data as Uint8Array,
    regions: meta.regions,
    bLast: meta.b_last,
    probes,
    nRotorPoles: meta.n_rotor_poles,
    alignedAngle: meta.aligned_angle,
    unalignedAngle: meta.unaligned_angle,
    windingCurrent: meta.winding_current,
    iMax: meta.i_max,
  };
}

export function frameFromWire(buf: ArrayBuffer): FieldFrameData {
  const { meta, arrays } = decode(buf);
  return {
    angle: meta.angle,
    currentA: meta.current_a,
    psi: meta.psi,
    torque: meta.torque,
    status: meta.status,
    probes: meta.probes,
    band: u32(arrays.band),
    b: f32(arrays.b),
    a: f32(arrays.a),
  };
}

export function framesFromWire(buf: ArrayBuffer): { meta: any; frames: FieldFrameData[] } {
  const { meta, arrays } = decode(buf);
  const frames = (meta.angles as number[]).map((angle, n) => ({
    angle,
    currentA: meta.current_a,
    psi: meta.psi[n],
    torque: meta.torque[n],
    status: meta.status[n],
    probes: Object.fromEntries(Object.entries(meta.probes as Record<string, number[]>).map(([z, v]) => [z, v[n]])),
    band: u32(arrays[`band.${n}`]),
    b: f32(arrays[`b.${n}`]),
    a: f32(arrays[`a.${n}`]),
  }));
  return { meta, frames };
}
