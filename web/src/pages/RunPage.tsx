import { lazy, Suspense, useEffect, useMemo } from "react"
import { Link, useParams } from "react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useJobActions } from "@/api/useJobActions"
import { useRunResult } from "@/api/useRunResult"
import { useJobEvents } from "@/api/useJobEvents"
import { Banner } from "@/components/Banner"
import { CandidateTable } from "@/components/run/CandidateTable"
import { JobStatusBadge, RunProgress } from "@/components/run/RunProgress"
import { Button } from "@/components/ui/button"
import { toRows } from "@/lib/candidates"
import { fmt } from "@/lib/format"

const ParetoPlot = lazy(() => import("@/components/run/ParetoPlot"))

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="num text-xl">{fmt(value, 6)}</div>
    </div>
  )
}

export function RunPage() {
  const { jobId = "" } = useParams()
  const qc = useQueryClient()
  const actions = useJobActions()
  const { job } = useJobEvents(jobId)
  const status = job?.status
  const terminal = job != null && !job.active

  // The SSE end event delivers the terminal status; refetch so results appear without a reload.
  useEffect(() => {
    if (terminal) qc.invalidateQueries({ queryKey: ["result", jobId] })
  }, [terminal, jobId, qc])

  const result = useRunResult(jobId, terminal)
  const rows = useMemo(() => (result.data ? toRows(result.data) : []), [result.data])
  const r = result.data
  const dropped = Object.entries(r?.dropped ?? {})
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-primary">Run</h1>
        <span className="num text-sm text-muted-foreground">{jobId}</span>
        {status && <JobStatusBadge status={status} />}
        {job?.active && (
          <Button variant="outline" className="min-h-11" onClick={() => actions.cancel(jobId)} disabled={actions.busy}>
            Cancel
          </Button>
        )}
        {job?.resumable && (
          <Button className="min-h-11" onClick={() => actions.resume(jobId)} disabled={actions.busy}>
            Resume
          </Button>
        )}
      </div>
      <Banner />
      {job?.active && <RunProgress job={job} />}
      {job?.error && <p className="text-destructive">{job.error}</p>}
      {result.isError && <p className="text-destructive">Could not load the result.</p>}
      {result.data === null && (
        <p className="text-sm text-muted-foreground">No result: the run stopped before any design was evaluated.</p>
      )}
      {r && (
        <>
          {(r.cancelled || status === "cancelled") && <p className="text-sm text-muted-foreground">Cancelled: partial result.</p>}
          {status === "interrupted" && (
            <p className="text-sm text-muted-foreground">Interrupted: partial result. Resume to continue.</p>
          )}
          <section aria-label="Counts" className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <Count label="Sampled" value={r.sampled ?? 0} />
            <Count label="Stage-1 rejected" value={r.stage1_rejected ?? 0} />
            <Count label="Evaluated" value={r.evaluations.length} />
          </section>
          {dropped.length > 0 && (
            <p className="text-sm text-muted-foreground">
              Dropped: {dropped.map(([reason, n]) => `${reason} ${n}`).join(", ")}
            </p>
          )}
          {rows.length > 0 ? (
            <>
              <Suspense fallback={<div className="h-[460px]" aria-busy="true" />}>
                <ParetoPlot rows={rows} />
              </Suspense>
              <CandidateTable rows={rows} jobId={jobId} />
            </>
          ) : (
            <p>No candidates were evaluated.</p>
          )}
        </>
      )}
      <Link to="/runs" className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-2">
        All runs
      </Link>
    </div>
  )
}
