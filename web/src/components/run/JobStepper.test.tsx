import { afterEach, describe, expect, it } from "vitest"
import type { JobOut } from "@/api/client"
import { JobStepper } from "./JobStepper"

import { act } from "react"
import { createRoot, type Root } from "react-dom/client"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const roots: Root[] = []

function render(el: React.ReactElement): HTMLElement {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(el))
  return container
}

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

const base: JobOut = {
  id: "j1", kind: "evaluate", status: "running", active: true, resumable: false, created: "2026-10-18T10:00:00",
  lane: "main", queue_position: null,
}

describe("JobStepper", () => {
  it("renders one row per step with its state", () => {
    const container = render(
      <JobStepper job={{ ...base, progress: { steps: ["queued", "mesh", "mapping", "winding", "saved"], step: "mesh" } }} />,
    )
    const rows = Array.from(container.querySelectorAll("li")).map((li) => li.getAttribute("data-state"))
    expect(rows).toEqual(["done", "active", "waiting", "waiting", "waiting"])
    expect(container.textContent).toContain("Choosing the winding")
  })
  it("falls back to the old bar for a job without steps", () => {
    const c = render(<JobStepper job={{ ...base, progress: { points_done: 3, points_total: 10, elapsed_s: 5 } }} />)
    expect(c.textContent).toContain("Map points")
    expect(c.textContent).toContain("Elapsed")
    expect(c.querySelector("ol")).toBeNull()
  })
  it("does not crash without progress", () => {
    expect(render(<JobStepper job={{ ...base, progress: null }} />).textContent).toContain("Elapsed")
  })
  it("exposes step state to assistive tech", () => {
    const c = render(
      <JobStepper
        job={{ ...base, progress: { steps: ["queued", "mesh", "mapping", "winding", "saved"], step: "mapping", points_done: 1, points_total: 10 } }}
      />,
    )
    const items = Array.from(c.querySelectorAll("li"))
    expect(items.map((li) => li.getAttribute("aria-current"))).toEqual([null, null, "step", null, null])
    expect(items[0].querySelector("[data-sr-state]")?.textContent).toContain("done")
    expect(items[2].querySelector("[data-sr-state]")?.textContent).toContain("active")
    expect(items[3].querySelector("[data-sr-state]")?.textContent).toContain("waiting")
    expect(items[2].querySelector("[aria-live=polite]")?.textContent).toContain("1 / 10 points")
  })
})
