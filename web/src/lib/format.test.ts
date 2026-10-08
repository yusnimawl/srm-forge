import { describe, expect, it } from "vitest"
import { fmt, fmtSI } from "./format"

describe("fmt", () => {
  it("shows a dash for missing values", () => {
    expect(fmt(NaN)).toBe("—")
    expect(fmt(null)).toBe("—")
    expect(fmt(undefined)).toBe("—")
  })
  it("uses significant digits", () => {
    expect(fmt(12.436, 3)).toBe("12.4")
    expect(fmt(0.0123456, 3)).toBe("0.0123")
  })
  it("groups thousands of large values with thin spaces", () => {
    expect(fmt(1234567, 7)).toBe("1 234 567")
    expect(fmt(1234, 4)).toBe("1234")
  })
  it("converts from SI", () => {
    expect(fmtSI(0.16, "mm", 3)).toBe("160")
  })
})
