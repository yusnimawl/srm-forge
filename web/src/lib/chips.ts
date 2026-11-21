export type ChipTone = "ok" | "warn" | "none"

/** The name of the label a case carries once every validation check passes. */
export const VERIFIED_LABEL = "2D-verified"

/** The verification chip: names the engine version when the case carries the 2D-verified label. */
export function verifiedChip(engineVersion: string | null | undefined): { text: string; tone: "ok" | "none" } {
  return engineVersion
    ? { text: `${VERIFIED_LABEL} · srmcore ${engineVersion}`, tone: "ok" }
    : { text: "Unvalidated", tone: "none" }
}

/** The peak-only chip: j_limit comes in A/m² and is shown in A/mm² with up to 3 significant figures. */
export function jLimitChip(jLimit: number | null | undefined): { text: string; tone: "warn" } {
  const known = jLimit != null && Number.isFinite(jLimit)
  const tail = known ? `assumes j_limit ${Number((jLimit / 1e6).toPrecision(3))} A/mm²` : "j_limit not recorded"
  return { text: `Peak only · ${tail}`, tone: "warn" }
}

type RatedFields = {
  j_limit?: number | null
  rating?: { insulation_class: string; limit_c: number | null; cooling?: { kind: string; placeholder: boolean } | null } | null
  thermal_summary?: { iron_band?: (number | null)[] | null } | null
}

/** The chips of an evaluation: the thermal rating (class and limit, cooling, iron-loss band) once rated; else the
 *  peak-only chip with "Not thermally rated". A rating stored as the summary only has no cooling or band to show. */
export function thermalChips(ev: RatedFields): { text: string; tone: ChipTone }[] {
  const r = ev.rating
  if (!r) return [jLimitChip(ev.j_limit), { text: "Not thermally rated", tone: "warn" }]
  const limit = r.limit_c == null ? "" : ` ${r.limit_c} °C`
  const [lo, hi] = ev.thermal_summary?.iron_band ?? []
  return [
    { text: `Rated · class ${r.insulation_class}${limit}`, tone: "ok" as ChipTone },
    ...(r.cooling ? [{ text: `Cooling: ${r.cooling.kind}${r.cooling.placeholder ? " (placeholder)" : ""}`, tone: (r.cooling.placeholder ? "warn" : "none") as ChipTone }] : []),
    ...(lo != null && hi != null ? [{ text: `Iron ×${lo}–${hi} band`, tone: "warn" as ChipTone }] : []),
  ]
}

/** What a losses result says about friction and windage: `none` for a result made before they were added, else
 *  whether the bearing input was the unchosen default (`placeholder`) or was set (`set`). */
export type MechanicalState = "none" | "placeholder" | "set"

export function mechanicalState(windageIncluded: boolean, bearingPlaceholder: boolean | null | undefined): MechanicalState {
  return !windageIncluded ? "none" : bearingPlaceholder === false ? "set" : "placeholder"
}

const MECHANICAL_CHIP: Record<MechanicalState, string> = {
  none: "Excludes friction and windage",
  placeholder: "Bearing is a placeholder · windage of a smooth rotor",
  set: "Windage of a smooth rotor (lower bound)",
}

/** The chips of a losses result: the winding temperature the copper loss assumes, what the friction and windage
 *  terms are (or that the result has none), and the label (losses are never validated). */
export function lossChips(windingTemperatureC: number | null | undefined, mechanical: MechanicalState = "none"): { text: string; tone: ChipTone }[] {
  const known = windingTemperatureC != null && Number.isFinite(windingTemperatureC)
  return [
    { text: known ? `Winding ${windingTemperatureC} °C` : "Winding temperature not recorded", tone: "warn" },
    { text: MECHANICAL_CHIP[mechanical], tone: "warn" },
    verifiedChip(null),
  ]
}

/** Which srmapp version made an evaluation; evaluations stored before 0.6.0 did not record it. */
export const madeWithText = (srmappVersion: string | null | undefined): string =>
  srmappVersion ? `made with srmapp ${srmappVersion}` : "made before 0.6.0"
