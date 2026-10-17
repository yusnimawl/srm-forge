import { Link } from "react-router"
import type { JobOut } from "@/api/client"
import { JobStatusBadge } from "@/components/run/RunProgress"
import { fmtAbout } from "@/lib/steps"

const LANE_LABEL = { main: "main lane", quick: "quick lane" } as const

/** Search jobs have a run page; every other kind belongs to a case. A case job without a case falls back to the run list. */
export function jobHref(job: JobOut): string {
  if (job.kind === "search") return `/runs/${job.id}`
  return job.case_id ? `/cases/${job.case_id}` : "/runs"
}

export type QueueRow = { job: JobOut; place: string; startsIn: string | null }

const etaOf = (j: JobOut): number | null => {
  const e = j.progress?.eta_s
  return typeof e === "number" && Number.isFinite(e) ? e : null
}

/** Running jobs first (oldest start first), then queued jobs by lane and position. Only the job at position 1 gets a
 *  start estimate, the time left of the running job in its lane: a job carries no duration of its own, so the wait
 *  behind deeper positions is unknown and left out, as is an unknown time left. */
export function queueRows(jobs: JobOut[]): QueueRow[] {
  const running = jobs.filter((j) => j.status === "running")
  const queued = jobs.filter((j) => j.status === "queued")
  const byStart = (a: JobOut, b: JobOut) => (a.started ?? a.created).localeCompare(b.started ?? b.created)
  const laneOrder = (a: JobOut, b: JobOut) =>
    a.lane === b.lane ? (a.queue_position ?? 1e9) - (b.queue_position ?? 1e9) : a.lane === "main" ? -1 : 1
  const rows: QueueRow[] = running.sort(byStart).map((job) => ({ job, place: `running · ${LANE_LABEL[job.lane]}`, startsIn: null }))
  for (const job of queued.sort(laneOrder)) {
    const pos = job.queue_position
    const ahead = running.find((r) => r.lane === job.lane)
    const eta = pos === 1 && ahead ? etaOf(ahead) : null
    rows.push({
      job,
      place: pos ? `#${pos} in ${LANE_LABEL[job.lane]}` : LANE_LABEL[job.lane],
      startsIn: eta === null ? null : `starts in ${fmtAbout(eta)}`,
    })
  }
  return rows
}

/** The jobs that hold or wait for a lane. */
export function QueuePanel({ jobs }: { jobs: JobOut[] }) {
  const rows = queueRows(jobs)
  if (rows.length === 0) return null
  return (
    <section aria-label="Queue" className="space-y-2 rounded-[10px] border border-border bg-card p-4">
      <h2 className="text-sm font-medium">Queue</h2>
      <ul className="m-0 list-none space-y-2 p-0">
        {rows.map(({ job, place, startsIn }) => (
          <li key={job.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <Link to={jobHref(job)} className="num min-w-0 break-all underline-offset-2 hover:underline">
              {job.id}
            </Link>
            <span className="text-muted-foreground">{job.kind}</span>
            <JobStatusBadge status={job.status} />
            <span className="text-muted-foreground">{place}</span>
            {startsIn && <span className="num text-muted-foreground">{startsIn}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}
