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
