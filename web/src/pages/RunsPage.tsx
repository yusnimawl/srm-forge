import { Link, useNavigate } from "react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, type JobOut } from "@/api/client"
import { toast } from "sonner"
import { errorMessage } from "@/lib/errorMessage"
import { fmtElapsed, isActive, JobStatusBadge, progressOf } from "@/components/run/RunProgress"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

const RESUMABLE = new Set(["interrupted", "cancelled", "failed"])

function Actions({ job }: { job: JobOut }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const refresh = () => qc.invalidateQueries({ queryKey: ["jobs"] })
  const cancel = useMutation({ onError: (e) => toast.error(errorMessage(e)), mutationFn: () => api(`/api/jobs/${job.id}/cancel`, { method: "POST" }), onSuccess: refresh })
  const resume = useMutation({
    onError: (e) => toast.error(errorMessage(e)),
    mutationFn: () => api<{ id: string }>(`/api/jobs/${job.id}/resume`, { method: "POST" }),
    onSuccess: ({ id }) => {
      refresh()
      navigate(`/runs/${id}`)
    },
  })
  const del = useMutation({ onError: (e) => toast.error(errorMessage(e)), mutationFn: () => api(`/api/jobs/${job.id}`, { method: "DELETE" }), onSuccess: refresh })
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" className="min-h-11" render={<Link to={`/runs/${job.id}`} />}>
        Open
      </Button>
      {isActive(job.status) && (
        <Button variant="outline" className="min-h-11" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
          Cancel
        </Button>
      )}
      {RESUMABLE.has(job.status) && (
        <Button variant="outline" className="min-h-11" onClick={() => resume.mutate()} disabled={resume.isPending}>
          Resume
        </Button>
      )}
      {!isActive(job.status) && (
        <Button
          variant="outline"
          className="min-h-11 text-destructive"
          onClick={() => window.confirm(`Delete run ${job.id}? This cannot be undone.`) && del.mutate()}
          disabled={del.isPending}
        >
          Delete
        </Button>
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
    refetchInterval: (q) => (q.state.data?.some((j) => isActive(j.status)) ? 5000 : false),
  })
  const list = jobs.data ?? []

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-primary">Runs</h1>
      {jobs.isError && <p className="text-destructive">Could not load the runs.</p>}
      {jobs.isSuccess && list.length === 0 && (
        <div className="space-y-3 rounded-lg border border-border p-6 text-center">
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
                    <TableCell>{when(j.created)}</TableCell>
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
              <li key={j.id} className="space-y-2 rounded-lg border border-border p-3 text-sm">
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
