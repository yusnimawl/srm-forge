export const BANNER_TEXT = "Unvalidated, peak-only"

/** Shown on every result page: unvalidated unless the case carries the EM-validated label (`engineVersion` is then set). */
export function Banner({ engineVersion }: { engineVersion?: string | null }) {
  return (
    <div
      role="note"
      className={
        engineVersion
          ? "rounded-md border border-feasible bg-feasible/10 px-3 py-2 text-sm font-medium text-foreground"
          : "rounded-md border border-border bg-muted px-3 py-2 text-sm font-medium text-muted-foreground"
      }
    >
      {engineVersion ? `EM-validated · srmcore ${engineVersion}` : BANNER_TEXT}
    </div>
  )
}
