import type { JobOut } from "@/api/client"

export type StepState = "done" | "active" | "waiting" | "failed" | "cancelled"
export type StepRow = { id: string; label: string; state: StepState; detail?: string }

const LABELS: Record<string, Record<string, string>> = {
  evaluate: { queued: "Queued", mesh: "Mesh built", mapping: "Mapping", winding: "Choosing the winding", saved: "Saved" },
  validate: { queued: "Queued", map: "Map (cache)", checks: "Checks and budget", saved: "Saved" },
  animate: { queued: "Queued", frames: "Frames", saved: "Saved" },
  search: { queued: "Queued", sampling: "Sampling", designs: "Designs", pareto: "Pareto set", saved: "Saved" },
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null)

/** "42 s" under a minute, else whole minutes. */
export function fmtSpan(seconds: number): string {
  const s = Math.max(0, seconds)
  return s < 60 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`
}

/** "about N min", or "under 1 min" for less than a minute. */
export function fmtAbout(seconds: number): string {
  return seconds < 60 ? "under 1 min" : `about ${Math.round(seconds / 60)} min`
}

function detailOf(job: JobOut, id: string): string | undefined {
  const p = job.progress ?? {}
  const done = num(p.points_done)
  const total = num(p.points_total)
  if (id === "mapping" && done !== null && total) {
    const parts = [`${done} / ${total} points`]
    const elapsed = num(p.elapsed_s)
    if (elapsed !== null) parts.push(`${fmtSpan(elapsed)} elapsed`)
    const eta = num(p.eta_s)
    if (eta !== null) parts.push(`${fmtAbout(eta)} left`)
    return parts.join(" · ")
  }
  if (id === "frames" && done !== null && total) return `${done} / ${total}`
  if (id === "designs") {
    const dd = num(p.designs_done)
    const dt = num(p.designs_total)
    if (dt) {
      const parts = [`${dd ?? 0} / ${dt} designs`]
      if (total) parts.push(`map ${done ?? 0} / ${total} points`)
      return parts.join(" · ")
    }
  }
  // steps that report no counts (mesh, winding, checks) still show the job's running time
  const elapsed = num(p.elapsed_s)
  if (elapsed !== null && id !== "queued" && id !== "saved") return `${fmtSpan(elapsed)} elapsed`
  return undefined
}

/** Whether the job carries the step list; jobs stored before it was added do not. */
export const hasSteps = (job: JobOut): boolean => stepIds(job).length > 0

function stepIds(job: JobOut): string[] {
  const s = job.progress?.steps
  return Array.isArray(s) ? s.filter((x): x is string => typeof x === "string") : []
}

/** One row per step of the job: finished steps done, the current one active (or failed / cancelled when the job
 *  ended in it), the rest waiting. A done job has every step done. Empty for a job without a step list. When the current step is missing or unknown no row is active, failed or cancelled. */
export function stepStates(job: JobOut): StepRow[] {
  const ids = stepIds(job)
  const labels = LABELS[job.kind] ?? {}
  const current = ids.indexOf(String(job.progress?.step ?? ""))
  const stop: StepState | null =
    job.status === "failed" ? "failed" : job.status === "cancelled" || job.status === "interrupted" ? "cancelled" : null
  return ids.map((id, i) => {
    let state: StepState
    if (job.status === "done" || i < current) state = "done"
    else if (i === current) state = stop ?? "active"
    else state = "waiting"
    const detail = state === "active" || state === "failed" || state === "cancelled" ? detailOf(job, id) : undefined
    return { id, label: labels[id] ?? id, state, ...(detail ? { detail } : {}) }
  })
}
