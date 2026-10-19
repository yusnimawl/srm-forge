import { afterEach, describe, expect, it, vi } from "vitest"
import { collect } from "./collect"

const geometry = { view_box: [-50, -50, 100, 100], stator: "M 0 0 Z", rotor: "M 0 0 Z", shaft: "M 0 0 Z", coils: [] }
const caseBody = (parent: string | null) => ({ id: "c", parent_case_id: parent, inputs: { design: { machine: { n: 1 } } } })
const reportBody = (job: string | null) => ({
  findings: [{ id: "animation_missing", level: "missing", topic: "data", text: "Animation unavailable: nothing run", unit: "", value: null }],
  versions: {},
  generated: "now",
  animation_job_id: job,
  animation_current_a: null,
})

type Table = Record<string, () => { status: number; body: unknown }>
function mockFetch(table: Table) {
  const urls: string[] = []
  vi.stubGlobal("fetch", async (url: string) => {
    urls.push(url)
    const key = Object.keys(table).find((k) => url.endsWith(k))
    const r = key ? table[key]() : { status: 404, body: { detail: "none" } }
    return new Response(JSON.stringify(r.body), { status: r.status, headers: { "Content-Type": "application/json" } })
  })
  return urls
}
const ok = (body: unknown) => () => ({ status: 200, body })
const base = (over: Table = {}, parent: string | null = null, job: string | null = null): Table => ({
  "/api/cases/c": ok(caseBody(parent)),
  "/api/cases/c/report": ok(reportBody(job)),
  "/api/cases/c/losses": ok({ points: [] }),
  "/api/geometry": ok(geometry),
  "/api/cases/c/compare": ok({}),
  ...over,
})
const render = async () => ["data:image/png;base64,AA"]

afterEach(() => vi.unstubAllGlobals())

describe("collect", () => {
  it("required parts propagate errors", async () => {
    mockFetch(base({ "/api/cases/c/report": () => ({ status: 409, body: { detail: "not evaluated" } }) }))
    await expect(collect("c", () => {}, render)).rejects.toThrow()
  })
  it("missing losses becomes a part", async () => {
    mockFetch(base({ "/api/cases/c/losses": () => ({ status: 404, body: { detail: "x" } }) }))
    const d = await collect("c", () => {}, render)
    expect(d.losses.ok).toBe(false)
    if (!d.losses.ok) expect(d.losses.reason).toContain("not run")
    expect(d.outline.ok).toBe(true)
  })
  it("frames cleared becomes a part", async () => {
    mockFetch(base({ "/api/jobs/j/frames": () => ({ status: 410, body: { detail: "gone" } }) }, null, "j"))
    const d = await collect("c", () => {}, render)
    expect(d.animation.ok).toBe(false)
  })
  it("no animation job skips frame fetch", async () => {
    const urls = mockFetch(base())
    const d = await collect("c", () => {}, render)
    expect(urls.some((u) => u.includes("/frames"))).toBe(false)
    expect(d.animation).toEqual({ ok: false, reason: "Animation unavailable: nothing run" })
  })
  it("compare only for child cases", async () => {
    const urls = mockFetch(base())
    expect((await collect("c", () => {}, render)).compare).toBeNull()
    expect(urls.some((u) => u.includes("/compare"))).toBe(false)
    const urls2 = mockFetch(base({}, "p"))
    expect((await collect("c", () => {}, render)).compare?.ok).toBe(true)
    expect(urls2.some((u) => u.includes("/compare"))).toBe(true)
  })
})
