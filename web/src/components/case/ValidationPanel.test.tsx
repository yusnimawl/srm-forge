import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { Validation } from "@/api/types"
import { ValidationPanel } from "./ValidationPanel"

const validation = (label: string | null): Validation => ({
  label,
  engine_version: "0.4.0",
  material_grades: {},
  reference_turns: 20,
  checks: [
    { name: "a", status: "pass", value: 1, limit: 2, detail: "" },
    { name: "b", status: "warn", value: 1, limit: 2, detail: "" },
    { name: "c", status: "fail", value: 1, limit: 2, detail: "" },
  ],
  budget: { rows: [], total: { la: 0.1 }, values: { la: 1 }, values_2d: { la: 1 } },
})

const html = (label: string | null) => renderToStaticMarkup(<ValidationPanel validation={validation(label)} />)

describe("ValidationPanel", () => {
  it("shows the 2D-verified name for a label stored under the old name", () => {
    const out = html("EM-validated")
    expect(out).toContain("2D-verified")
    expect(out).not.toContain("EM-validated")
  })
  it("shows not validated without a label", () => expect(html(null)).toContain("not validated"))
  it("styles each check status through the badge variants", () => {
    const out = html("2D-verified")
    expect(out).toContain("text-feasible")
    expect(out).toContain("text-warn")
    expect(out).toContain("text-destructive")
  })
})
