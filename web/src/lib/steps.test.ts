import { describe, expect, it } from "vitest"
import type { JobOut } from "@/api/client"
import { stepStates } from "./steps"

const EVAL = ["queued", "mesh", "mapping", "winding", "saved"]
const job = (over: Partial<JobOut> = {}, progress: Record<string, unknown> = {}): JobOut => ({
  id: "j1", kind: "evaluate", status: "running", active: true, resumable: false, created: "2026-10-18T10:00:00",
  lane: "main", queue_position: null,
  progress: { steps: EVAL, step: "mapping", ...progress },
  ...over,
})
const states = (j: JobOut) => stepStates(j).map((r) => r.state)

describe("stepStates", () => {
  it("marks earlier steps done, the current active, later waiting", () => {
    expect(states(job())).toEqual(["done", "done", "active", "waiting", "waiting"])
  })
  it("queued job: first step active, rest waiting", () => {
    expect(states(job({ status: "queued" }, { step: "queued" }))).toEqual(["active", "waiting", "waiting", "waiting", "waiting"])
  })
  it("done job has every step done", () => {
    expect(states(job({ status: "done", active: false }, { step: "saved" }))).toEqual(Array(5).fill("done"))
  })
  it("failed job marks the step it stopped in", () => {
    expect(states(job({ status: "failed", active: false }))).toEqual(["done", "done", "failed", "waiting", "waiting"])
  })
  it("cancelled job marks the step it stopped in", () => {
    expect(states(job({ status: "cancelled", active: false }, { step: "mesh" }))).toEqual(["done", "cancelled", "waiting", "waiting", "waiting"])
  })
  it("uses the spec labels per kind", () => {
    expect(stepStates(job()).map((r) => r.label)).toEqual(["Queued", "Mesh built", "Mapping", "Choosing the winding", "Saved"])
    expect(stepStates(job({ kind: "validate" }, { steps: ["queued", "map", "checks", "saved"], step: "map" })).map((r) => r.label)).toEqual([
      "Queued", "Map (cache)", "Checks and budget", "Saved",
    ])
    expect(stepStates(job({ kind: "animate" }, { steps: ["queued", "frames", "saved"], step: "frames" })).map((r) => r.label)).toEqual([
      "Queued", "Frames", "Saved",
    ])
    expect(
      stepStates(job({ kind: "search" }, { steps: ["queued", "sampling", "designs", "pareto", "saved"], step: "designs" })).map((r) => r.label),
    ).toEqual(["Queued", "Sampling", "Designs", "Pareto set", "Saved"])
  })
  it("a step without counts shows the elapsed time", () => {
    const r = stepStates(job({}, { step: "winding", elapsed_s: 125 }))[3]
    expect(r.state).toBe("active")
    expect(r.detail).toBe("2 min elapsed")
  })
  it("a failed step without counts shows no elapsed time", () => {
    const r = stepStates(job({ status: "failed", active: false }, { step: "winding", elapsed_s: 125 }))[3]
    expect(r.state).toBe("failed")
    expect(r.detail).toBeUndefined()
  })
  it("mapping detail with points, elapsed and time left", () => {
    const r = stepStates(job({}, { points_done: 412, points_total: 960, elapsed_s: 420, eta_s: 540 }))[2]
    expect(r.detail).toBe("412 / 960 points · 7 min elapsed · about 9 min left")
  })
  it("mapping detail leaves out the time left when eta is null", () => {
    const r = stepStates(job({}, { points_done: 10, points_total: 960, elapsed_s: 30, eta_s: null }))[2]
    expect(r.detail).toBe("10 / 960 points · 30 s elapsed")
  })
  it("frames and designs details", () => {
    const f = stepStates(job({ kind: "animate" }, { steps: ["queued", "frames", "saved"], step: "frames", points_done: 3, points_total: 12 }))[1]
    expect(f.detail).toBe("3 / 12")
    const d = stepStates(
      job({ kind: "search" }, { steps: ["queued", "sampling", "designs", "pareto", "saved"], step: "designs", designs_done: 2, designs_total: 5, points_done: 3, points_total: 10 }),
    )[2]
    expect(d.detail).toBe("2 / 5 designs · map 3 / 10 points")
  })
  it("returns no rows for a job stored without steps", () => {
    expect(stepStates(job({}, { steps: undefined, step: undefined }))).toEqual([])
    expect(stepStates(job({ progress: null }))).toEqual([])
  })
  it("marks no step active or failed when the current step is missing or unknown", () => {
    expect(states(job({ status: "failed" }, { step: undefined }))).toEqual(["waiting", "waiting", "waiting", "waiting", "waiting"])
    expect(states(job({ status: "failed" }, { step: "nope" }))).toEqual(["waiting", "waiting", "waiting", "waiting", "waiting"])
    expect(states(job({ status: "done" }, { step: undefined }))).toEqual(["done", "done", "done", "done", "done"])
  })
})

describe("losses job steps", () => {
  it("labels the five steps", () => {
    const j = job({ kind: "losses" }, { steps: ["queued", "strokes", "fields", "losses", "saved"], step: "fields", points_done: 10, points_total: 60 })
    expect(stepStates(j).map((r) => r.label)).toEqual(["Queued", "Stroke choices", "Field solves", "Losses", "Saved"])
    expect(stepStates(j)[2].detail).toContain("10 / 60")
  })
})
