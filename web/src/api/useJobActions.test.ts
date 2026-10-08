import { describe, expect, it } from "vitest"
import { actionsFor } from "./useJobActions"
import { searchJobs } from "./jobs"

describe("actionsFor", () => {
  it("an active job can be cancelled", () => expect(actionsFor({ active: true, resumable: false })).toEqual(["open", "cancel"]))
  it("a resumable job can be resumed or deleted", () =>
    expect(actionsFor({ active: false, resumable: true })).toEqual(["open", "resume", "delete"]))
  it("a finished job can be deleted", () => expect(actionsFor({ active: false, resumable: false })).toEqual(["open", "delete"]))
})

describe("searchJobs", () => {
  it("keeps only search jobs", () => {
    const jobs = [{ id: "a", kind: "search" }, { id: "b", kind: "evaluate" }, { id: "c", kind: "validate" }]
    expect(searchJobs(jobs).map((j) => j.id)).toEqual(["a"])
  })
})
