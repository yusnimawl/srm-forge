import type { JobOut } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import { cn } from "@/lib/utils"

export type JobProgress = {
  designs_done?: number
  designs_total?: number
  points_done?: number
  points_total?: number
  elapsed_s?: number
  message?: string
}

export const progressOf = (job: JobOut): JobProgress => (job.progress ?? {}) as JobProgress

/** h:mm:ss */
export function fmtElapsed(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.floor(seconds ?? 0))
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${Math.floor(s / 3600)}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`
}

const STATUS_CLASS: Record<string, string> = {
  done: "bg-feasible/15 text-feasible",
  failed: "bg-destructive/15 text-destructive",
  running: "bg-secondary text-secondary-foreground",
}

export function JobStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("capitalize", STATUS_CLASS[status])}>
      {status}
    </Badge>
  )
}

function Bar({ label, done, total }: { label: string; done: number; total: number }) {
  return (
    <Progress value={total > 0 ? done : null} max={Math.max(total, 1)}>
      <ProgressLabel>{label}</ProgressLabel>
      <ProgressValue>{() => `${done} / ${total}`}</ProgressValue>
    </Progress>
  )
}

export function RunProgress({ job }: { job: JobOut }) {
  const p = progressOf(job)
  const dd = p.designs_done ?? 0
  const dt = p.designs_total ?? 0
  const pd = p.points_done ?? 0
  const pt = p.points_total ?? 0
  const line =
    job.status === "queued"
      ? "Queued"
      : dt === 0
        ? (p.message ?? "Sampling candidates…")
        : `Design ${Math.min(dd + 1, Math.max(dt, 1))} of ${dt}, map ${pd} of ${pt} points`
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <Bar label="Designs" done={dd} total={dt} />
      <Bar label="Map points (current design)" done={pd} total={pt} />
      <p aria-live="polite" className="text-sm">
        {line}
      </p>
      <p className="text-sm text-muted-foreground">
        Elapsed <span className="num">{fmtElapsed(p.elapsed_s)}</span>
        {p.message ? ` · ${p.message}` : ""}
      </p>
    </div>
  )
}
