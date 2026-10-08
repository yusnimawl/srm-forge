import { useEffect, useState } from "react"
import { api, type JobOut } from "./client"

/** Live job state over SSE. On a dropped connection it re-reads the job once, then lets EventSource reconnect. */
export function useJobEvents(jobId: string): { job: JobOut | null; connected: boolean } {
  const [job, setJob] = useState<JobOut | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    setJob(null)
    const es = new EventSource(`/api/jobs/${jobId}/events`)
    const update = (e: Event) => setJob(JSON.parse((e as MessageEvent).data) as JobOut)
    es.onopen = () => setConnected(true)
    es.addEventListener("progress", update)
    es.addEventListener("end", (e) => {
      update(e)
      setConnected(false)
      es.close()
    })
    es.onerror = () => {
      setConnected(false)
      api<JobOut>(`/api/jobs/${jobId}`).then(setJob).catch(() => {})
    }
    return () => es.close()
  }, [jobId])

  return { job, connected }
}
