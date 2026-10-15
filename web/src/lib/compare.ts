import type { CompareRow } from "@/api/types"

export type DeltaRow = CompareRow & { delta: number | null; deltaPct: number | null }

/** Rows with the absolute and relative change from before to after; null where either value is missing
 *  (the relative change is also null when before is 0). */
export function compareRows(rows: CompareRow[]): DeltaRow[] {
  return rows.map((r) => {
    const delta = r.before == null || r.after == null ? null : r.after - r.before
    const deltaPct = delta == null || !r.before ? null : (delta / Math.abs(r.before)) * 100
    return { ...r, delta, deltaPct }
  })
}
