import { describe, expect, it } from "vitest"
import { progressLines } from "./RunProgress"

describe("progressLines", () => {
  it("shows the sampling message once", () => {
    expect(progressLines("running", { message: "Sampling 200 candidates" })).toEqual({ line: "Sampling 200 candidates", note: null })
  })
  it("falls back to a default while sampling without a message", () => {
    expect(progressLines("running", {})).toEqual({ line: "Sampling candidates…", note: null })
  })
  it("reports the design and map position, with the message as a note", () => {
    expect(progressLines("running", { designs_done: 1, designs_total: 5, points_done: 3, points_total: 10, message: "stage 2" })).toEqual({
      line: "Design 2 of 5, map 3 of 10 points",
      note: "stage 2",
    })
  })
  it("queued keeps its message as the note", () => {
    expect(progressLines("queued", { message: "waiting" })).toEqual({ line: "Queued", note: "waiting" })
  })
})
