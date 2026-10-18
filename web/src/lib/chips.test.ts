import { describe, expect, it } from "vitest"
import { jLimitChip, lossChips, madeWithText, verifiedChip } from "./chips"

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
  it("shows the winding temperature, the friction exclusion and the label", () => {
    expect(lossChips(120).map((c) => c.text)).toEqual(["Winding 120 °C", "Excludes friction and windage", "Unvalidated"])
    expect(lossChips(87.5)[0].text).toBe("Winding 87.5 °C")
    expect(lossChips(null)[0].text).toBe("Winding temperature not recorded")
  })
})

describe("madeWithText", () => {
  it("names the srmapp version or says the evaluation is older", () => {
    expect(madeWithText("0.6.0")).toBe("made with srmapp 0.6.0")
    expect(madeWithText(null)).toBe("made before 0.6.0")
    expect(madeWithText(undefined)).toBe("made before 0.6.0")
  })
})
