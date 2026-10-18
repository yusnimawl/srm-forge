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
    await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
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
    await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
    const call = m.calls.find((u) => u.includes("/losses/b"))!
    const q = new URL(call, "http://x").searchParams
    expect(q.get("point")).toBe("1")
    expect(Number(q.get("x"))).toBeCloseTo(0.025, 9)
    expect(Number(q.get("y"))).toBeCloseTo(0.025, 9)
    expect(m.host.querySelector("[data-testid=line-plot]")?.textContent).toContain("B (T)")
  })
})
