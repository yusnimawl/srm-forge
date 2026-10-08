export const BANNER_TEXT = "Unvalidated, peak-only"

/** Shown on every result page. */
export function Banner() {
  return (
    <div
      role="note"
      className="rounded-md border border-border bg-muted px-3 py-2 text-sm font-medium text-muted-foreground"
    >
      {BANNER_TEXT}
    </div>
  )
}