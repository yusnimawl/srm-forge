import { afterEach, describe, expect, it, vi } from "vitest"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { SrmLogo } from "./SrmLogo"
import { SrmSpinner } from "./SrmSpinner"

function mockMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: reduce && q.includes("prefers-reduced-motion"),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLElement
let root: Root | null = null

function render(el: React.ReactElement) {
  container = document.createElement("div")
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => root!.render(el))
  return {
    container,
    unmount: () => {
      act(() => root!.unmount())
      root = null
    },
  }
}

afterEach(() => {
  if (root) act(() => root!.unmount())
  root = null
  container?.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("SrmLogo", () => {
  it("is hidden from assistive tech when decorative", () => {
    const { container } = render(<SrmLogo decorative />)
    const svg = container.querySelector("svg")!
    expect(svg.getAttribute("aria-hidden")).toBe("true")
    expect(svg.getAttribute("role")).toBeNull()
    expect(container.querySelector("title")).toBeNull()
  })
  it("has an accessible title", () => {
    const { container } = render(<SrmLogo title="SRM designer" />)
    const svg = container.querySelector("svg")!
    expect(svg.getAttribute("role")).toBe("img")
    const id = svg.getAttribute("aria-labelledby")!
    expect(container.querySelector(`title[id="${id}"]`)?.textContent).toBe("SRM designer")
  })
})

describe("SrmSpinner", () => {
  it("is a labelled status", () => {
    mockMotion(true)
    const { container } = render(<SrmSpinner label="Loading the case..." />)
    expect(container.querySelector('[role="status"]')?.textContent).toContain("Loading the case...")
  })

  it("holds a still 8/6 and requests no animation frames under reduced motion", () => {
    mockMotion(true)
    const raf = vi.spyOn(window, "requestAnimationFrame")
    const { container } = render(<SrmSpinner label="Loading" />)
    expect(raf).not.toHaveBeenCalled()
    // 8 stator + 6 rotor pole rectangles, plus the mask's background rectangle
    expect(container.querySelectorAll("rect")).toHaveLength(8 + 6 + 1)
  })

  it("animates otherwise and cancels the loop on unmount", () => {
    mockMotion(false)
    const raf = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(7)
    const cancel = vi.spyOn(window, "cancelAnimationFrame")
    const { unmount } = render(<SrmSpinner label="Loading" />)
    expect(raf).toHaveBeenCalled()
    unmount()
    expect(cancel).toHaveBeenCalledWith(7)
  })
})
