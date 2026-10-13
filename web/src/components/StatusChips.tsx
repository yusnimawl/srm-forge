import { jLimitChip, verifiedChip, type ChipTone } from "@/lib/chips"
import { cn } from "@/lib/utils"

const DOT: Record<ChipTone, string> = { ok: "bg-feasible", warn: "bg-warn", none: "" }

function Chip({ text, tone }: { text: string; tone: ChipTone }) {
  return (
    <span className="inline-flex items-center gap-[7px] rounded-md border border-border px-2.5 py-1 text-[12.5px] text-muted-foreground">
      {tone !== "none" && <span aria-hidden className={cn("size-1.5 rounded-full", DOT[tone])} />}
      {text}
    </span>
  )
}

/**
 * Shown under a result header: whether the case is 2D-verified, and, once an evaluation exists, that its numbers are
 * peak-only at an assumed j_limit (an evaluation stored without the field reads "not recorded").
 */
export function StatusChips({
  engineVersion,
  evaluation,
}: {
  engineVersion?: string | null
  evaluation?: { j_limit?: number | null } | null
}) {
  return (
    <div role="note" className="flex flex-wrap gap-2">
      <Chip {...verifiedChip(engineVersion)} />
      {evaluation && <Chip {...jLimitChip(evaluation.j_limit)} />}
    </div>
  )
}
