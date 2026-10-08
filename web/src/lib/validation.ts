export type KeyValues = Record<string, number | null>

/** Power of the turn scale each absolute key number follows: L goes with turns², ψ with turns; torque does not change. */
const TURN_POWER: Record<string, number> = { la: 2, lu: 2, psi_max: 1 }

/** Scale from the reference winding the map was built at to a winding of `turns` per pole in `paths` parallel paths
 *  (a path of N turns acts as N / paths turns on the map). */
export const turnsScale = (w: { turns: number; paths: number }, referenceTurns: number): number =>
  w.turns / (w.paths * referenceTurns)

/** Key numbers of the reference winding as they read at the scaled winding. */
export function atScale(values: KeyValues, k: number): KeyValues {
  return Object.fromEntries(Object.entries(values).map(([key, v]) => [key, v == null ? null : v * k ** (TURN_POWER[key] ?? 0)]))
}
