import { describe, expect, it } from "vitest"
import type { CaseSummary } from "@/api/types"
import { canShowMore, caseStatus, estimateText, filterByFlag, MAX_SHOWN, toCaseRows } from "./cases"
import { fmt } from "./format"

const summary = (id: string, extra: Partial<CaseSummary> = {}): CaseSummary => ({
  id,
  label: `case ${id}`,
  origin: "candidate",
  parent_case_id: null,
  flag: null,
  comment: null,
  show_in_graphs: false,
  stale: false,
  created: "2026-10-08T00:00:00Z",
  preset: "full",
  poles: "8/6",
  status: "ok",
  torque_ratio: 1.2,
  power_ratio: 1.1,
  peak_power_w: 2500,
  mass_kg: 3,
  power_density_kw_per_kg: 0.8,
  efficiency_base: 0.9,
  feasible: true,
  validated: false,
  ...extra,
})

describe("caseStatus", () => {
  it("is Draft for a stale case, whatever else it carries", () => {
    expect(caseStatus(summary("a", { stale: true, validated: true, status: null }))).toBe("Draft")
  })
  it("is Failed when the evaluation status is not ok", () => {
    expect(caseStatus(summary("a", { status: "no_winding" }))).toBe("Failed")
  })
  it("is 2D-verified when validated, else Evaluated", () => {
    expect(caseStatus(summary("a", { validated: true }))).toBe("2D-verified")
    expect(caseStatus(summary("a"))).toBe("Evaluated")
  })
})

describe("toCaseRows", () => {
  it("converts W to kW and keeps the label, flag and comment", () => {
    const [r] = toCaseRows([summary("a", { flag: "keep", comment: "hi" })])
    expect(r).toMatchObject({ id: "a", label: "case a", flag: "keep", comment: "hi", peak_power_kw: 2.5, status: "Evaluated" })
  })
  it("gives a draft nulls that print as a dash", () => {
    const [r] = toCaseRows([summary("d", { stale: true, status: null, torque_ratio: null, peak_power_w: null, mass_kg: null })])
    expect(r.status).toBe("Draft")
    expect(r.peak_power_kw).toBeNull()
    expect(fmt(r.torque_ratio)).toBe("—")
  })
  it("falls back to the id when there is no label", () => {
    expect(toCaseRows([summary("z", { label: null })])[0].label).toBe("z")
  })
})

describe("filterByFlag", () => {
  const rows = toCaseRows([summary("a", { flag: "keep" }), summary("b", { flag: "drop" }), summary("c")])
  it("keeps only matching flags", () => {
    expect(filterByFlag(rows, "keep").map((r) => r.id)).toEqual(["a"])
  })
  it("keeps all for null", () => {
    expect(filterByFlag(rows, null)).toHaveLength(3)
  })
})

describe("canShowMore", () => {
  const shown = (n: number) => toCaseRows(Array.from({ length: n }, (_, k) => summary(String(k), { show_in_graphs: true })))
  it("is true below the limit and false at it", () => {
    expect(MAX_SHOWN).toBe(6)
    expect(canShowMore(shown(5))).toBe(true)
    expect(canShowMore(shown(6))).toBe(false)
  })
  it("counts only shown rows", () => {
    expect(canShowMore(toCaseRows([...Array.from({ length: 8 }, (_, k) => summary(String(k)))]))).toBe(true)
  })
})

describe("estimateText", () => {
  it("reads the estimate", () => {
    expect(estimateText({ new_map: false, seconds: 30, basis: "history" })).toBe("No new map — about a minute")
    expect(estimateText({ new_map: false, seconds: 450, basis: "budget" })).toBe("No new map — about 8 min")
    expect(estimateText({ new_map: true, seconds: 2010, basis: "budget" })).toBe("1 new map, about 34 min")
    expect(estimateText({ new_map: true, seconds: 20, basis: "history" })).toBe("1 new map, about a minute")
  })
  it("says a minute only below 90 s", () => {
    expect(estimateText({ new_map: false, seconds: 89, basis: "history" })).toBe("No new map — about a minute")
    expect(estimateText({ new_map: false, seconds: 91, basis: "history" })).toBe("No new map — about 2 min")
  })
})
