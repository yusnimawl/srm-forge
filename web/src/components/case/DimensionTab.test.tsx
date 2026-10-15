// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { act } from "react"
import { describe, expect, it } from "vitest"
import { DimensionTab } from "./DimensionTab"
import { toForm } from "@/lib/caseForm"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

async function render(imported: boolean) {
  const host = document.createElement("div")
  document.body.append(host)
  const form = toForm({ design: { machine: { n_stator_poles: 8, n_rotor_poles: 6, n_phases: 4 } } })
  await act(async () => {
    createRoot(host).render(<DimensionTab form={form} update={() => {}} errors={{}} imported={imported} />)
  })
  return host
}

describe("DimensionTab", () => {
  it("locks the geometry of an imported case but not the preset", async () => {
    const host = await render(true)
    expect(host.textContent).toContain("Geometry comes from the imported DXF. Edit the parent case and import again to change it.")
    const preset = host.querySelector("#preset") as HTMLSelectElement
    expect(preset.disabled).toBe(false)
    const others = Array.from(host.querySelectorAll("input, select")).filter((e) => e !== preset)
    expect(others.length).toBeGreaterThan(3)
    expect(others.every((e) => (e as HTMLInputElement).disabled)).toBe(true)
  })
  it("leaves a normal case editable without the note", async () => {
    const host = await render(false)
    expect(host.textContent).not.toContain("imported DXF")
    expect(Array.from(host.querySelectorAll("input, select")).some((e) => (e as HTMLInputElement).disabled)).toBe(false)
  })
})
