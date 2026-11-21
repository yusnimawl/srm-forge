import { describe, expect, it } from "vitest"
import type { Evaluation } from "@/api/types"
import { curveSpec, tabState, tornadoSpec, type Rating, type ShareRow } from "./thermal"

const ev = (o: object) => o as Evaluation
const sp = (rpm: number) => ({ rpm, nominal_continuous_nm: 10, nominal_peak_nm: 20, rated_continuous_nm: 8, rated_peak_nm: 18 })

describe("tabState", () => {
  it("names the four shapes", () => {
    expect(tabState(ev({}))).toBe("unrated")
    expect(tabState(ev({ thermal_check: { holds: false } }))).toBe("check-only")
    expect(tabState(ev({ rating: { shares: [] } }))).toBe("summary-only")
    expect(tabState(ev({ rating: { shares: [], stress: {} } }))).toBe("full")   // a rating with no shares is still R5d
    expect(tabState(ev({ rating: { shares: [{}], stress: {} }, thermal_check: {} }))).toBe("full")
  })
})

describe("curveSpec", () => {
  it("draws the band and dashed requirement", () => {
    const d = curveSpec({ speeds: [sp(1000), sp(2000)] } as unknown as Rating, {
      speeds: [{ rpm: 1000, need_continuous_nm: 5, need_peak_nm: null }, { rpm: 2000, need_continuous_nm: 6, need_peak_nm: null }],
    } as never) as { name: string; fill?: string; line?: { dash?: string } }[]
    expect(d.filter((t) => t.fill === "tonexty")).toHaveLength(2)
    expect(d.find((t) => t.name === "Required continuous")?.line?.dash).toBe("dash")
    expect(d.some((t) => t.name === "Required peak")).toBe(false)
  })
})

describe("tornadoSpec", () => {
  it("caps a runaway bar and drops zero rows", () => {
    const rows = [
      { row: "contact", label: "Contact gap", k: 1000, runaway: true },
      { row: "iron", label: "Iron loss band", k: 10, runaway: false },
      { row: "liner", label: "Liner", k: 0, runaway: false },
    ] as ShareRow[]
    const [t] = tornadoSpec(rows) as unknown as { x: number[]; text: string[]; y: string[] }[]
    expect(t.y).toEqual(["Contact gap", "Iron loss band"])
    expect(t.x).toEqual([12, 10])
    expect(t.text[0]).toBe("runaway")
  })
})
