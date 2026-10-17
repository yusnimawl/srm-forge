import { Link } from "react-router"
import { useQuery } from "@tanstack/react-query"
import { api, type JobOut } from "@/api/client"
import { searchJobs } from "@/api/jobs"
import { actionsFor, useJobActions } from "@/api/useJobActions"
import { fmtElapsed, JobStatusBadge, progressOf } from "@/components/run/RunProgress"
import { QueuePanel } from "@/components/run/QueuePanel"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

function Actions({ job }: { job: JobOut }) {
  const { cancel, resume, remove, busy } = useJobActions()
  const outline = "min-h-11"
  return (
    <div className="flex flex-wrap gap-2">
      {actionsFor(job).map((a) =>
        a === "open" ? (
          <Button key={a} variant="outline" className={outline} render={<Link to={`/runs/${job.id}`} />}>
            Open
          </Button>
        ) : a === "cancel" ? (
          <Button key={a} variant="outline" className={outline} onClick={() => cancel(job.id)} disabled={busy}>
            Cancel
          </Button>
        ) : a === "resume" ? (
          <Button key={a} variant="outline" className={outline} onClick={() => resume(job.id)} disabled={busy}>
            Resume
          </Button>
        ) : (
          <Button
            key={a}
            variant="outline"
            className={`${outline} text-destructive`}
            onClick={() => window.confirm(`Delete run ${job.id}? This cannot be undone.`) && remove(job.id)}
            disabled={busy}
          >
            Delete
          </Button>
        ),
      )}
    </div>
  )
}

function JobProgressBar({ job }: { job: JobOut }) {
  if (job.status !== "running") return null
  const p = progressOf(job)
  const total = p.designs_total ?? 0
  return (
    <div className="space-y-1">
      <Progress value={total > 0 ? (p.designs_done ?? 0) : null} max={Math.max(total, 1)} aria-label="Designs done" />
      <span className="num text-xs text-muted-foreground">
        {p.designs_done ?? 0} / {total} · {fmtElapsed(p.elapsed_s)}
      </span>
    </div>
  )
}

const when = (iso: string) => new Date(iso).toLocaleString()

export function RunsPage() {
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<JobOut[]>("/api/jobs"),
    refetchInterval: (q) => (q.state.data?.some((j) => j.active) ? 5000 : false),
  })
  const list = searchJobs(jobs.data ?? [])

  return (
    <div className="space-y-4">
      <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-foreground">Runs</h1>
      <QueuePanel jobs={jobs.data ?? []} />
      {jobs.isError && <p className="text-destructive">Could not load the runs.</p>}
      {jobs.isSuccess && list.length === 0 && (
        <div className="space-y-3 rounded-[10px] border border-border bg-card p-6 text-center">
          <p>No runs yet</p>
          <Button className="min-h-11" render={<Link to="/search" />}>
            Start a search
          </Button>
        </div>
      )}
      {list.length > 0 && (
        <>
          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-48">Progress</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell className="num">{j.id}</TableCell>
                    <TableCell>
                      <JobStatusBadge status={j.status} />
                    </TableCell>
                    <TableCell className="num text-muted-foreground">{when(j.created)}</TableCell>
                    <TableCell>
                      <JobProgressBar job={j} />
                    </TableCell>
                    <TableCell>
                      <Actions job={j} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <ul className="space-y-2 md:hidden">
            {list.map((j) => (
              <li key={j.id} className="space-y-2 rounded-[10px] border border-border bg-card p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="num">{j.id}</span>
                  <JobStatusBadge status={j.status} />
                </div>
                <div className="text-muted-foreground">{when(j.created)}</div>
                <JobProgressBar job={j} />
                <Actions job={j} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
