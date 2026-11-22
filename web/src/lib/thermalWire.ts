import { decode } from "./fieldWire"

export type ThermalFieldsData = {
  rpm: number[]
  kinds: string[]
  nodes: Float32Array
  triangles: Uint32Array
  kind: Uint8Array
  steady: Float32Array[]
  peak: Float32Array[]
  endWindingSteadyC: (number | null)[]
  endWindingPeakC: (number | null)[]
}

const rows = (a: { data: unknown; shape: number[] }): Float32Array[] => {
  const d = a.data as Float32Array
  const n = a.shape[1]
  return Array.from({ length: a.shape[0] }, (_, i) => d.subarray(i * n, (i + 1) * n))
}

export function decodeThermalFields(buf: ArrayBuffer): ThermalFieldsData {
  const { meta, arrays } = decode(buf)
  return {
    rpm: meta.rpm,
    kinds: meta.kinds,
    nodes: arrays.nodes.data as Float32Array,
    triangles: arrays.triangles.data as Uint32Array,
    kind: arrays.kind.data as Uint8Array,
    steady: rows(arrays.steady),
    peak: rows(arrays.peak),
    endWindingSteadyC: meta.end_winding_steady_c,
    endWindingPeakC: meta.end_winding_peak_c,
  }
}

export async function fetchThermalFields(caseId: string): Promise<ThermalFieldsData | "gone"> {
  const res = await fetch(`/api/cases/${caseId}/thermal/fields`, { credentials: "same-origin" })
  if (res.status === 410) return "gone"
  if (!res.ok) throw new Error(`temperature fields: ${res.status}`)
  return decodeThermalFields(await res.arrayBuffer())
}
