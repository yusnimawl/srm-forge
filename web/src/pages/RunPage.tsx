import { lazy, Suspense, useEffect, useMemo } from "react"
import { Link, useNavigate, useParams } from "react-router"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/api/client"
import { useRunResult } from "@/api/useRunResult"
import { toast } from "sonner"
import { errorMessage } from "@/lib/errorMessage"
import { useJobEvents } from "@/api/useJobEvents"
import { Banner } from "@/components/Banner"
import { CandidateTable } from "@/components/run/CandidateTable"
import { isActive, JobStatusBadge, RunProgress } from "@/components/run/RunProgress"
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
  const navigate = useNavigate()
  const { job } = useJobEvents(jobId)
  const status = job?.status
  const terminal = status != null && !isActive(status)

  // The SSE end event delivers the terminal status; refetch so results appear without a reload.
  useEffect(() => {
    if (terminal) qc.invalidateQueries({ queryKey: ["result", jobId] })
  }, [terminal, jobId, qc])

  const result = useRunResult(jobId, terminal)
  const rows = useMemo(() => (result.data ? toRows(result.data) : []), [result.data])
  const cancel = useMutation({ onError: (e) => toast.error(errorMessage(e)), mutationFn: () => api(`/api/jobs/${jobId}/cancel`, { method: "POST" }) })
  const resume = useMutation({
    onError: (e) => toast.error(errorMessage(e)),
    mutationFn: () => api<{ id: string }>(`/api/jobs/${jobId}/resume`, { method: "POST" }),
    onSuccess: ({ id }) => navigate(`/runs/${id}`),
  })

  const r = result.data
  const dropped = Object.entries(r?.dropped ?? {})
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-primary">Run</h1>
        <span className="num text-sm text-muted-foreground">{jobId}</span>
        {status && <JobStatusBadge status={status} />}
        {status && isActive(status) && (
          <Button variant="outline" className="min-h-11" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
            Cancel
          </Button>
        )}
        {(status === "cancelled" || status === "failed" || status === "interrupted") && (
          <Button className="min-h-11" onClick={() => resume.mutate()} disabled={resume.isPending}>
            Resume
          </Button>
        )}
      </div>
      <Banner />
      {job && isActive(job.status) && <RunProgress job={job} />}
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
