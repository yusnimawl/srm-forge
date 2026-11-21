// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { act } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Evaluation } from "@/api/types"

vi.mock("@/components/PlotlyPlot", () => ({
  Plot: (p: { data: { type?: string }[] }) => <div data-testid={p.data[0]?.type === "bar" ? "tornado" : "curves"} />,
  useColors: () => ({}),
  plotTheme: () => ({}),
}))

import ThermalTab from "./ThermalTab"

vi.mock("@/lib/thermalWire", () => ({ fetchThermalFields: vi.fn(async () => "gone") }))

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const speed = (rpm: number, hot: number | null) => ({
  rpm, nominal_continuous_nm: 10, nominal_peak_nm: 20, rated_continuous_nm: 8, rated_peak_nm: 18,
  hot_spot_c: hot, hot_spot_at: "A", peak_hot_spot_c: 150, peak_hot_spot_at: "A",
  rated: { rotor_c: 92 },
})
const sumSpeed = (rpm: number, text: string, headroom: number | null = null) => ({
  rpm, need_continuous_nm: 7, need_peak_nm: 15, binds_continuous: "heat", binds_peak: "EM", hot_spot_text: text, headroom_k: headroom,
})
const rows = [
  { row: "contact", label: "Contact gap", k: 1000, runaway: true, hint: "The contact gap is the largest." },
  { row: "iron", label: "Iron loss band", k: 9, runaway: false, hint: "Iron loss is the largest." },
]
const full = (hot2: number | null = 150, text2 = "slot winding, A 150 °C", shareRows = rows) => ({
  status: "ok", error: "",
  rating: {
    speeds: [speed(2000, 140), speed(6000, hot2)], limit_c: 160, insulation_class: "H", stress_status: "ok", stress_safety_factor: 1.9,
    notes: ["a note"], shares: [{ row: "iron", rpm: 2000, hot_spot_rise_k: 9 }],
    gap: { air_gap_m: 0.0004, cases: { hot: { closure: 0.00009 } } },
    stress: { status: "ok", safety_factor: 1.9, speed_limit_rpm: 13400, check_speed_rpm: 7200 },
    cooling: { kind: "jacket", placeholder: true, ambient_c: 40, jacket: { flow_m3s: 1.5e-4, inlet_c: 65, coolant: "water_glycol_50" } },
  },
  thermal_check: { holds: true },
  thermal_summary: {
    verdict: { holds: true, text: "✓ Meets the requirement · smallest margin +5 % at 6000 r/min" },
    speeds: [sumSpeed(2000, "end winding 140 °C", 20), sumSpeed(6000, text2)], least_margin_rpm: 6000,
    shares: [{ rpm: 2000, rows }, { rpm: 6000, rows: shareRows }],
  },
}) as unknown as Evaluation

function mount(ev: Evaluation) {
  const host = document.createElement("div")
  document.body.append(host)
  act(() => { createRoot(host).render(<ThermalTab evaluation={ev} caseId="c" />) })
  return host
}
afterEach(() => { document.body.innerHTML = "" })

describe("ThermalTab", () => {
  it("renders a full rating", () => {
    const h = mount(full())
    expect(h.textContent).toContain("✓ Meets the requirement")
    expect(h.querySelectorAll("tbody tr[data-speed]")).toHaveLength(2)
    expect(h.textContent).toContain("heat")
    expect(h.textContent).toContain("EM")
    expect(h.querySelector("[data-testid=tornado]")).not.toBeNull()
    expect(h.querySelector("[data-testid=thermal-map-slot]")).not.toBeNull()
    expect(h.textContent).toContain("The contact gap is the largest.")
    expect(h.textContent).toMatch(/13\s400/)
    expect(h.textContent).toContain("9.0 L/min, water glycol 50, inlet 65 °C, ambient 40 °C (placeholder)")
    expect(h.querySelector(".\\@container")).not.toBeNull()
    expect(h.textContent).toContain("hot 30 %")
  })
  it("renders a pre-R5d summary", () => {
    const ev = full()
    ;(ev.rating as { shares: unknown[] }).shares = []
    ;(ev.thermal_summary as { shares: unknown[] }).shares = []
    const h = mount(ev)
    expect(h.querySelectorAll("tbody tr[data-speed]")).toHaveLength(2)
    expect(h.textContent).toContain("Edit, then Evaluate, for full detail")
    expect(h.querySelector("[data-testid=tornado]")).toBeNull()
  })
  it("renders check-only", () => {
    const h = mount({
      status: "ok", error: "", rating: null,
      thermal_check: { holds: false, which: "continuous", hot_c: 171, peak_hot_c: [140, 150], continuous_hot_c: [130, 140, 171] },
      thermal_summary: { verdict: { holds: false, hot_spot_c: 171, text: "✗ Short at 6000 r/min: HOT_SPOT_ABOVE" }, speeds: [], shares: [] },
    } as unknown as Evaluation)
    expect(h.textContent).toContain("✗ Short at 6000 r/min")
    expect(h.textContent).toContain("Make a case and Evaluate for the full rating")
    expect(h.textContent).toContain("171 °C")
    expect(h.textContent).toContain("2 speeds passed")
  })
  it("renders unrated", () => {
    const h = mount({ status: "ok", error: "No thermal data for this material", rating: null } as unknown as Evaluation)
    expect(h.textContent).toContain("No thermal data for this material")
    expect(h.querySelector("table")).toBeNull()
  })
  it("nan speed row", () => {
    const ev = full(null, "")
    ;(ev.rating!.speeds[1] as { rated: unknown }).rated = null
    const h = mount(ev)
    expect(h.textContent).toContain("no steady state")
  })
  it("runaway share labelled", () => {
    const h = mount(full())
    expect(h.textContent).toContain("Contact gap")
    expect(h.textContent).toContain("runaway")
  })
  it("says so when the map file is gone, table still shown", async () => {
    const h = mount(full())
    await act(async () => { await Promise.resolve() })
    expect(h.textContent).toContain("Re-evaluate to see the map")
    expect(h.querySelectorAll("tbody tr[data-speed]")).toHaveLength(2)
  })
  it("captions a lumped end-winding hot spot", () => {
    const h = mount(full(150, "end winding, A1"))
    expect(h.textContent).toContain("hot spot: end winding (lumped, not in this section)")
  })
  it("captions a lumped end-winding hot spot at the peak end", () => {
    const ev = full()
    ;(ev.rating!.speeds[1] as { peak_hot_spot_at: string }).peak_hot_spot_at = "end_A1"
    const h = mount(ev)
    act(() => { (Array.from(h.querySelectorAll("button")).find((b) => b.textContent === "Peak end") as HTMLElement).click() })
    expect(h.textContent).toContain("hot spot: end winding (lumped, not in this section) 150 °C")
  })
})
