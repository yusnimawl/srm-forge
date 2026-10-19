// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }))
vi.mock("./ControlScopes", () => ({ default: () => <div data-testid="scopes" /> }))

import ControlTab from "./ControlTab"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

const CONTROLLERS = [
  { name: "hysteresis", params: [{ name: "band", unit: "A", default: "0.05 * SRM_I_MAX_A" }] },
  { name: "tsf", params: [] },
]

class FakeEventSource {
  static last: FakeEventSource
  listeners: Record<string, (e: Event) => void> = {}
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor() { FakeEventSource.last = this }
  addEventListener(n: string, f: (e: Event) => void) { this.listeners[n] = f }
  close() {}
  emit(n: string, data: unknown) { this.listeners[n](new MessageEvent(n, { data: JSON.stringify(data) })) }
}

const posts: { url: string; body: unknown }[] = []

let caseJobs: unknown[] = []

const waitFor = (f: () => void) => act(async () => { await vi.waitFor(f) })

const roots: { unmount: () => void }[] = []

async function mount() {
  vi.stubGlobal("EventSource", FakeEventSource)
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (url === "/api/control/controllers") return json(200, CONTROLLERS)
    if (url === "/api/cases/c1/control" && init?.method === "POST") {
      posts.push({ url, body: JSON.parse(init.body as string) })
      return json(201, { job_id: "j1" })
    }
    if (url === "/api/cases/c1") return json(200, { id: "c1", jobs: caseJobs })
    return json(200, {})
  })
  const host = document.createElement("div")
  document.body.append(host)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const root = createRoot(host)
  roots.push(root)
  await act(async () => {
    root.render(<QueryClientProvider client={qc}><ControlTab caseId="c1" busVoltage={48} /></QueryClientProvider>)
  })
  await waitFor(() => expect(document.getElementById('ctl-p-band')).not.toBeNull())
}

const button = (text: string) => Array.from(document.body.querySelectorAll("button")).find((b) => b.textContent === text) as HTMLButtonElement

afterEach(async () => {
  await act(async () => { roots.splice(0).forEach((r) => r.unmount()) })
  document.body.innerHTML = ""
  posts.length = 0
  caseJobs = []
  vi.unstubAllGlobals()
})

describe("ControlTab", () => {
  it("lists the reference controllers and a custom folder entry", async () => {
    await mount()
    const options = Array.from(document.querySelectorAll("#ctl-controller option")).map((o) => o.textContent)
    expect(options).toEqual(["hysteresis", "tsf", "Custom folder…"])
    expect(document.getElementById("ctl-p-band")).not.toBeNull()
  })

  it("shows the folder input when Custom folder is chosen", async () => {
    await mount()
    expect(document.getElementById("ctl-folder")).toBeNull()
    const select = document.getElementById("ctl-controller") as HTMLSelectElement
    await act(async () => {
      select.value = "__custom__"
      select.dispatchEvent(new Event("change", { bubbles: true }))
    })
    expect(document.getElementById("ctl-folder")).not.toBeNull()
    expect(button("Run").disabled).toBe(true)
  })

  it("posts the controller and scenario in server units", async () => {
    await mount()
    await act(async () => { button("Run").click() })
    expect(posts).toHaveLength(1)
    const body = posts[0].body as { controller: string; scenario: { speed_rpm: number; duration: number; bus_voltage: number; params: object } }
    expect(body.controller).toBe("hysteresis")
    expect(body.scenario).toMatchObject({ speed_rpm: 1000, duration: 0.02, bus_voltage: 48, params: {} })
  })

  it("shows the compiler log of a failed job", async () => {
    await mount()
    await act(async () => { button("Run").click() })
    await act(async () => {
      FakeEventSource.last.emit("end", { id: "j1", kind: "control", status: "failed", active: false, error: "ctrl.c:3: error: expected ';'", progress: { steps: ["queued", "compile", "simulate", "saved"], step: "compile" } })
    })
    expect(document.body.querySelector("pre")?.textContent).toContain("expected ';'")
  })

  const type = async (el: HTMLInputElement, value: string) => {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, value)
      el.dispatchEvent(new Event("input", { bubbles: true }))
    })
  }
  const chooseCustom = async () => {
    const select = document.getElementById("ctl-controller") as HTMLSelectElement
    await act(async () => {
      select.value = "__custom__"
      select.dispatchEvent(new Event("change", { bubbles: true }))
    })
    await type(document.getElementById("ctl-folder") as HTMLInputElement, "C:/ctl")
    await act(async () => { button("Add parameter").click() })
  }

  it("posts a typed custom parameter and blocks a non-number", async () => {
    await mount()
    await chooseCustom()
    await type(document.querySelector('[aria-label="Parameter 1 name"]') as HTMLInputElement, "kp")
    await type(document.querySelector('[aria-label="Parameter 1 value"]') as HTMLInputElement, "abc")
    expect(button("Run").disabled).toBe(true)
    await type(document.querySelector('[aria-label="Parameter 1 value"]') as HTMLInputElement, "2.5")
    await act(async () => { button("Run").click() })
    expect(posts[0].body).toMatchObject({ controller: "C:/ctl", scenario: { params: { kp: 2.5 } } })
  })

  it("attaches to an active job after a reload and re-enables Run when it ends", async () => {
    caseJobs = [{ id: "j9", kind: "control", status: "running", active: true, created: "2026-10-20" }]
    await mount()
    await waitFor(() => expect(button("Run").disabled).toBe(true))
    const progress = { steps: ["queued", "compile", "simulate", "saved"], step: "simulate" }
    await act(async () => { FakeEventSource.last.emit("progress", { id: "j9", kind: "control", status: "running", active: true, progress }) })
    expect(document.querySelector('[aria-label="Job steps"]')).not.toBeNull()
    caseJobs = []
    await act(async () => {
      FakeEventSource.last.emit("end", { id: "j9", kind: "control", status: "failed", active: false, error: "x", progress: { steps: ["queued", "compile", "simulate", "saved"], step: "compile" } })
    })
    expect(button("Run").disabled).toBe(false)
  })
})
