import { MemoryRouter } from "react-router"
import { describe, expect, it } from "vitest"
import type { JobOut } from "@/api/client"
import { QueuePanel, queueRows } from "./QueuePanel"

import { act } from "react"
import { createRoot } from "react-dom/client"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function render(el: React.ReactElement): HTMLElement {
  const container = document.createElement("div")
  document.body.appendChild(container)
  act(() => createRoot(container).render(el))
  return container
}

const job = (id: string, over: Partial<JobOut>): JobOut => ({
  id, kind: "evaluate", status: "queued", active: true, resumable: false, created: "2026-10-18T10:00:00",
  lane: "main", queue_position: null, progress: null, ...over,
})
const JOBS = [
  job("q2", { queue_position: 2, created: "2026-10-18T10:02:00" }),
  job("quick1", { lane: "quick", kind: "animate", queue_position: 1 }),
  job("q1", { queue_position: 1, created: "2026-10-18T10:01:00" }),
  job("r1", { status: "running", started: "2026-10-18T10:00:00", progress: { eta_s: 540 } }),
  job("d1", { status: "done", active: false }),
]

describe("queueRows", () => {
  it("orders running first, then queued by lane and position, and skips ended jobs", () => {
    expect(queueRows(JOBS).map((r) => r.job.id)).toEqual(["r1", "q1", "q2", "quick1"])
  })
  it("estimates the start of the next job from the running job in its lane only", () => {
    const rows = queueRows(JOBS)
    expect(rows.find((r) => r.job.id === "q1")?.startsIn).toBe("starts in about 9 min")
    expect(rows.find((r) => r.job.id === "q2")?.startsIn).toBeNull()
    expect(rows.find((r) => r.job.id === "quick1")?.startsIn).toBeNull()
  })
})

describe("QueuePanel", () => {
  it("shows position per lane and the start estimate", () => {
    const text = render(<MemoryRouter><QueuePanel jobs={JOBS} /></MemoryRouter>).textContent
    expect(text).toContain("#2 in main lane")
    expect(text).toContain("#1 in quick lane")
    expect(text).toContain("starts in about 9 min")
  })
  it("renders nothing when no job is active", () => {
    expect(render(<MemoryRouter><QueuePanel jobs={[JOBS[4]]} /></MemoryRouter>).firstChild).toBeNull()
  })
})
