import type { JobOut } from "@/api/client"
import { SrmSpinner } from "@/components/brand/SrmSpinner"
import { Bar, fmtElapsed, progressOf } from "@/components/run/RunProgress"
import { cn } from "@/lib/utils"
import { hasSteps, stepStates, type StepState } from "@/lib/steps"

const MARK: Record<StepState, string> = {
  done: "border-foreground bg-foreground text-background",
  active: "border-foreground text-foreground",
  waiting: "border-border text-muted-foreground",
  failed: "border-destructive text-destructive",
  cancelled: "border-muted-foreground text-muted-foreground",
}
const GLYPH: Record<StepState, string> = { done: "✓", active: "", waiting: "", failed: "!", cancelled: "–" }

/**
 * One row per step of the job, joined by a line. A job without a step list (stored before steps existed) shows the
 * map-points bar and the elapsed time instead.
 */
export function JobStepper({ job }: { job: JobOut }) {
  if (!hasSteps(job)) return <LegacyProgress job={job} />
  const rows = stepStates(job)
  return (
    <ol aria-label="Job steps" className="m-0 list-none p-0">
      {rows.map((r, i) => (
        <li key={r.id} data-step={r.id} data-state={r.state} aria-current={r.state === "active" ? "step" : undefined} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span
              aria-hidden
              className={cn("flex size-6 shrink-0 items-center justify-center rounded-full border text-xs", MARK[r.state])}
            >
              {r.state === "active" && job.status === "running" ? (
                <SrmSpinner size={16} label={r.label} />
              ) : (
                GLYPH[r.state]
              )}
            </span>
            {i < rows.length - 1 && (
              <span aria-hidden className={cn("w-px grow min-h-3", r.state === "done" ? "bg-foreground" : "bg-border")} />
            )}
          </div>
          <div className="min-w-0 pb-3">
            <p className={cn("text-sm", r.state === "waiting" ? "text-muted-foreground" : "text-foreground")}>
              {r.label}
              <span data-sr-state className="sr-only"> ({r.state})</span>
              {r.state === "failed" && <span className="text-destructive"> · failed</span>}
              {r.state === "cancelled" && <span className="text-muted-foreground"> · cancelled</span>}
            </p>
            {r.detail && (
              <p aria-live={r.state === "active" ? "polite" : undefined} className="num break-words text-xs text-muted-foreground">
                {r.detail}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

function LegacyProgress({ job }: { job: JobOut }) {
  const p = progressOf(job)
  return (
    <div className="space-y-3">
      {job.kind !== "validate" && <Bar label="Map points" done={p.points_done ?? 0} total={p.points_total ?? 0} />}
      <p aria-live="polite" className="text-sm text-muted-foreground">
        Elapsed <span className="num">{fmtElapsed(p.elapsed_s)}</span>
        {p.message ? ` · ${p.message}` : ""}
      </p>
    </div>
  )
}
