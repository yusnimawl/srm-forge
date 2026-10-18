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

/** The chips of a losses result: the winding temperature the copper loss assumes, what the loss leaves out, and the
 *  label (losses are never validated). */
export function lossChips(windingTemperatureC: number | null | undefined): { text: string; tone: ChipTone }[] {
  const known = windingTemperatureC != null && Number.isFinite(windingTemperatureC)
  return [
    { text: known ? `Winding ${windingTemperatureC} °C` : "Winding temperature not recorded", tone: "warn" },
    { text: "Excludes friction and windage", tone: "warn" },
    verifiedChip(null),
  ]
}

/** Which srmapp version made an evaluation; evaluations stored before 0.6.0 did not record it. */
export const madeWithText = (srmappVersion: string | null | undefined): string =>
  srmappVersion ? `made with srmapp ${srmappVersion}` : "made before 0.6.0"
