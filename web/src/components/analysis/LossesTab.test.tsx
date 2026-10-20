// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type PlotProps = { data: unknown[]; onClick?: (e: unknown) => void }
const plots: PlotProps[] = []
vi.mock("@/components/PlotlyPlot", () => ({
  Plot: (p: PlotProps) => {
    plots.push(p)
    return <div data-testid="plot" />
  },
  LinePlot: (p: { yTitle: string }) => <div data-testid="line-plot">{p.yTitle}</div>,
  useColors: () => ({}),
  plotTheme: () => ({}),
}))
vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }))

import LossesTab from "./LossesTab"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const pt = (speed: number, torque: number, eff: number, ac: number | null) => ({
  speed_rpm: speed, torque_nm: torque, reached: true, efficiency: eff, copper_dc_w: 10, copper_ac_w: ac,
  iron: { stator_pole: { hysteresis: 1, classical: 0.1, excess: 0.1 } }, iron_w: 1.2, beyond_fit_range: false,
  current_limit: 50, iron_uncertainty_rel: 0.1, power_w: 100, stroke_key: "k", theta_off: 0, theta_on: 0,
})
const losses = (ac: number | null) => ({
  points: [pt(1000, 1, 0.8, ac), pt(1000, 2, 0.9, ac)], speeds_rpm: [1000], torque_fractions: [0.5, 1],
  n_angles: 60, angle_convergence_rel: 0.01, notes: ["some iron is extrapolated"], srmapp_version: "0.6.0",
  winding_temperature_c: 120,
})
const geometry = { view_box: [-50, -50, 100, 100], stator: "M -50 -50 L 50 -50 L 50 50 Z", rotor: "M 0 0 L 10 0 L 10 10 Z", shaft: "M 0 0 Z", coils: [] }
const caseBody = { id: "c", jobs: [], inputs: { design: { machine: { n_stator_poles: 8 } } } }

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

function mount(routes: Record<string, () => Promise<Response>>) {
  const calls: string[] = []
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    calls.push(url)
    const key = Object.keys(routes).find((k) => url.includes(k))
    return key ? routes[key]() : json({ detail: "no" }, 404)
  }))
  const host = document.createElement("div")
  document.body.append(host)
  const render = async () => {
    await act(async () => {
      createRoot(host).render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <LossesTab caseId="c" />
        </QueryClientProvider>,
      )
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
  }
  return { host, calls, render }
}

beforeEach(() => { plots.length = 0 })
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.innerHTML = ""
})

describe("LossesTab", () => {
  it("offers Run losses with the estimate when there is no result", async () => {
    const m = mount({
      "/losses/estimate": () => json({ basis: "history", per_solve_s: 3, seconds: 900, solves: 300 }),
      "/losses": () => json({ detail: "no losses for this case" }, 404),
      "/api/cases/c": () => json(caseBody),
    })
    await m.render()
    expect(m.host.textContent).toContain("Run losses")
    expect(m.host.textContent).toContain("300 solves")
    expect(m.host.textContent).toContain("about 15 min")
  })

  it("shows the chips, the notes and the density-mode AC message", async () => {
    const m = mount({
      "/losses": () => json(losses(null)),
      "/api/geometry": () => json(geometry),
      "/api/cases/c": () => json(caseBody),
    })
    await m.render()
    const t = m.host.textContent ?? ""
    expect(t).toContain("Winding 120 °C")
    expect(t).toContain("Excludes friction and windage")
    expect(t).toContain("Unvalidated")
    expect(t).toContain("some iron is extrapolated")
    expect(t).toContain("AC not computed (no wire chosen)")
  })

  it("shows the iron uncertainty, the beyond-range marker with its reason and the angle convergence", async () => {
    const r = losses(2)
    r.points = r.points.map((p) => ({ ...p, beyond_fit_range: true }))
    r.notes = ["more than 5 % of the iron loss of a side comes from iron below the flux density range of the loss data", "other"]
    r.angle_convergence_rel = 0.02
    const m = mount({ "/losses": () => json(r), "/api/geometry": () => json(geometry), "/api/cases/c": () => json(caseBody) })
    await m.render()
    const t = m.host.textContent ?? ""
    expect(t).toContain("± 10 %")
    expect(t).toContain("Beyond the fit range of the loss data")
    expect(t).toContain("flux density range of the loss data")
    expect(t).toContain("Angle convergence 2 % (placeholder until measured)")
  })

  it("shows the cut-edge range and the process, and renders without them", async () => {
    const r = { ...losses(2), cut_process: "unspecified" }
    r.points = r.points.map((p) => ({ ...p, cut_edge_rel: [-0.03, 0.21], cut_edge_factor: { stator_pole: 1.05 } }))
    const m = mount({ "/losses": () => json(r), "/api/geometry": () => json(geometry), "/api/cases/c": () => json(caseBody) })
    await m.render()
    const t = m.host.textContent ?? ""
    expect(t).toContain("cut edge −3 / +21 %")
    expect(t).toContain("Cut process: unspecified (range over all processes)")
    expect(t).toContain("stator pole ×1.05")
    document.body.innerHTML = ""
    const m2 = mount({ "/losses": () => json(losses(2)), "/api/geometry": () => json(geometry), "/api/cases/c": () => json(caseBody) })
    await m2.render()
    expect(m2.host.textContent).not.toContain("Cut process")
    expect(m2.host.textContent).toContain("Efficiency")
  })

  it("names a specified cutting process", async () => {
    const r = { ...losses(2), cut_process: "laser" }
    r.points = r.points.map((p) => ({ ...p, cut_edge_rel: [0.12, 0.12], cut_edge_factor: { stator_pole: 1 } }))
    const m = mount({ "/losses": () => json(r), "/api/geometry": () => json(geometry), "/api/cases/c": () => json(caseBody) })
    await m.render()
    expect(m.host.textContent).toContain("Cut process: laser")
  })

  it("loads B(t) at the picked element in metres", async () => {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue(
      { left: 0, top: 0, width: 200, height: 200, right: 200, bottom: 200, x: 0, y: 0, toJSON: () => ({}) })
    const m = mount({
      "/losses/b": () => json({ t: [0, 1], b_r: [0.1, 0.2], b_t: [0, 0.1], region: "stator_pole", side: "stator" }),
      "/losses": () => json(losses(2)),
      "/api/geometry": () => json(geometry),
      "/api/cases/c": () => json(caseBody),
    })
    await m.render()
    const svg = m.host.querySelector("svg[aria-label='Pick an iron element']")!
    expect(svg).toBeTruthy()
    // the picture centre is the origin; x is right of it and y above it
    await act(async () => {
      svg.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 150, clientY: 50 }))
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
    const call = m.calls.find((u) => u.includes("/losses/b"))!
    const q = new URL(call, "http://x").searchParams
    expect(q.get("point")).toBe("1")
    expect(Number(q.get("x"))).toBeCloseTo(0.025, 9)
    expect(Number(q.get("y"))).toBeCloseTo(0.025, 9)
    expect(m.host.querySelector("[data-testid=line-plot]")?.textContent).toContain("B (T)")
  })
})

describe("LossesTab grid and job", () => {
  it("posts the grid from the inputs", async () => {
    const m = mount({
      "/losses/estimate": () => json({ basis: "budget", per_solve_s: 3, seconds: 100, solves: 10 }),
      "/losses": () => json({ detail: "no losses for this case" }, 404),
      "/api/cases/c": () => json(caseBody),
    })
    await m.render()
    const set = async (id: string, v: string) => {
      const el = m.host.querySelector<HTMLInputElement>(`#${id}`)!
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, v)
        el.dispatchEvent(new Event("input", { bubbles: true }))
      })
    }
    await set("losses-speeds", "4")
    await set("losses-torques", "3")
    const fetchMock = vi.mocked(globalThis.fetch)
    fetchMock.mockClear()
    const btn = Array.from(m.host.querySelectorAll("button")).find((b) => b.textContent === "Run losses")!
    await act(async () => { btn.click() })
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST")
    expect(post?.[0]).toContain("/losses")
    expect(JSON.parse((post![1] as RequestInit).body as string)).toEqual({ n_speeds: 4, n_torques: 3 })
  })

  it("shows one line, not a stepper, while a losses job runs", async () => {
    const m = mount({
      "/losses": () => json({ detail: "none" }, 404),
      "/api/cases/c": () => json({ ...caseBody, jobs: [{ id: "j", kind: "losses", active: true }] }),
    })
    await m.render()
    expect(m.host.textContent).toContain("Losses job running — progress above.")
    expect(m.host.querySelector("[aria-label='Job steps']")).toBeNull()
  })

  it("hides the point and B(t) sections when nothing was reached", async () => {
    const none = { ...losses(2), points: losses(2).points.map((p) => ({ ...p, reached: false })) }
    const m = mount({ "/losses": () => json(none), "/api/geometry": () => json(geometry), "/api/cases/c": () => json(caseBody) })
    await m.render()
    expect(m.host.textContent).toContain("No operating point was reached.")
    expect(m.host.querySelector("svg[aria-label='Pick an iron element']")).toBeNull()
  })
})
