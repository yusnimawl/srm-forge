import { describe, expect, it } from "vitest"
import { thermalChips, jLimitChip, lossChips, madeWithText, mechanicalState, verifiedChip } from "./chips"

describe("verifiedChip", () => {
  it("names the engine version when verified", () => {
    expect(verifiedChip("0.4.0")).toEqual({ text: "2D-verified · srmcore 0.4.0", tone: "ok" })
  })
  it("reads Unvalidated without a version", () => {
    expect(verifiedChip(null)).toEqual({ text: "Unvalidated", tone: "none" })
    expect(verifiedChip(undefined)).toEqual({ text: "Unvalidated", tone: "none" })
  })
})

describe("jLimitChip", () => {
  it("converts A/m² to A/mm² with up to 3 significant figures", () => {
    expect(jLimitChip(20e6).text).toBe("Peak only · assumes j_limit 20 A/mm²")
    expect(jLimitChip(12.5e6).text).toBe("Peak only · assumes j_limit 12.5 A/mm²")
    expect(jLimitChip(7.123456e6).text).toBe("Peak only · assumes j_limit 7.12 A/mm²")
    expect(jLimitChip(20e6).tone).toBe("warn")
  })
  it("says not recorded when missing", () => {
    expect(jLimitChip(null).text).toBe("Peak only · j_limit not recorded")
    expect(jLimitChip(undefined).text).toBe("Peak only · j_limit not recorded")
    expect(jLimitChip(NaN).text).toBe("Peak only · j_limit not recorded")
  })
})

describe("lossChips", () => {
  it("says friction and windage are excluded for results made before they were added", () => {
    expect(lossChips(120).map((c) => c.text)).toEqual(["Winding 120 °C", "Excludes friction and windage", "Unvalidated"])
    expect(lossChips(87.5)[0].text).toBe("Winding 87.5 °C")
    expect(lossChips(null)[0].text).toBe("Winding temperature not recorded")
  })
  it("names the placeholder bearing and the smooth-rotor windage instead of the exclusion", () => {
    expect(lossChips(120, "placeholder").map((c) => c.text)).toEqual(["Winding 120 °C", "Bearing is a placeholder · windage of a smooth rotor", "Unvalidated"])
    expect(lossChips(120, "set")[1].text).toBe("Windage of a smooth rotor (lower bound)")
    expect(lossChips(120, "set").map((c) => c.text).join(" ")).not.toContain("Excludes")
  })
  it("derives the state from the result", () => {
    expect(mechanicalState(false, null)).toBe("none")
    expect(mechanicalState(true, true)).toBe("placeholder")
    expect(mechanicalState(true, false)).toBe("set")
    expect(mechanicalState(true, null)).toBe("placeholder")
  })
})

describe("madeWithText", () => {
  it("names the srmapp version or says the evaluation is older", () => {
    expect(madeWithText("0.6.0")).toBe("made with srmapp 0.6.0")
    expect(madeWithText(null)).toBe("made before 0.6.0")
    expect(madeWithText(undefined)).toBe("made before 0.6.0")
  })
})

describe("thermalChips", () => {
  const rated = (rating: object, extra = {}) => ({ j_limit: 20e6, rating, ...extra }) as never
  it("describes a full rating", () => {
    const ev = rated(
      { insulation_class: "H", limit_c: 160, cooling: { kind: "jacket", placeholder: true } },
      { thermal_summary: { iron_band: [3.2, 7] } },
    )
    expect(thermalChips(ev)).toEqual([
      { text: "Rated · class H 160 °C", tone: "ok" },
      { text: "Cooling: jacket (placeholder)", tone: "warn" },
      { text: "Iron ×3.2–7 band", tone: "warn" },
    ])
  })
  it("rounds the limit like the server", () => {
    expect(thermalChips(rated({ insulation_class: "H", limit_c: 152.5 })).map((c) => c.text)).toEqual(["Rated · class H 153 °C"])
  })
  it("drops the placeholder note when set", () => {
    const t = thermalChips(rated({ insulation_class: "F", limit_c: 140, cooling: { kind: "end_spray", placeholder: false } }))
    expect(t.map((c) => c.text)).toEqual(["Rated · class F 140 °C", "Cooling: end_spray"])
  })
  it("shows only the rated chip for a pre-R5d summary", () => {
    expect(thermalChips(rated({ insulation_class: "H", limit_c: 160 })).map((c) => c.text)).toEqual(["Rated · class H 160 °C"])
  })
  it("keeps the j_limit chip when unrated", () => {
    expect(thermalChips({ j_limit: 20e6, rating: null } as never)).toEqual([
      jLimitChip(20e6),
      { text: "Not thermally rated", tone: "warn" },
    ])
  })
})
