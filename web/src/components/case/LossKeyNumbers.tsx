import { useLosses } from "@/api/losses"
import { fmt } from "@/lib/format"
import { lossKeyNumbers } from "@/lib/losses"

/** Best efficiency and the total loss at the rated point of a case's losses result; nothing without a result. */
export function LossKeyNumbers({ caseId }: { caseId: string }) {
  const losses = useLosses(caseId)
  if (!losses.data) return null
  const k = lossKeyNumbers(losses.data)
  return (
    <dl aria-label="Losses key numbers" className="grid grid-cols-[auto_auto] justify-start gap-x-4 text-sm">
      <dt className="text-muted-foreground">Best efficiency</dt>
      <dd className="num">{k.best ? `${fmt(k.best.efficiency * 100, 3)} % at ${k.best.label}` : "—"}</dd>
      <dt className="text-muted-foreground">Total loss at the rated point</dt>
      <dd className="num">{k.rated ? `${fmt(k.rated.totalW, 3)} W at ${k.rated.label}` : "—"}</dd>
    </dl>
  )
}
