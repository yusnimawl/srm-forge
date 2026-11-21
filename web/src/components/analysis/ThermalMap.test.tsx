// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { act } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

const fetchMock = vi.fn()
vi.mock("@/lib/thermalWire", () => ({ fetchThermalFields: (...a: unknown[]) => fetchMock(...a) }))
vi.mock("@/lib/fieldGl", async (orig) => ({ ...(await orig<object>()), canRender: () => "canvas2d", draw2d: vi.fn() }))
globalThis.ResizeObserver = class { observe() {} disconnect() {} unobserve() {} } as unknown as typeof ResizeObserver
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

import ThermalMap from "./ThermalMap"

const data = {
  rpm: [1000], kinds: ["coil"], nodes: new Float32Array([0, 0, 1, 0, 0, 1]), triangles: new Uint32Array([0, 1, 2]),
  kind: new Uint8Array([0]), steady: [new Float32Array([20, 60, 40])], peak: [new Float32Array([NaN, NaN, NaN])],
  endWindingSteadyC: [null], endWindingPeakC: [null],
}
async function mount(rpm = 1000) {
  const host = document.createElement("div")
  document.body.append(host)
  await act(async () => { createRoot(host).render(<ThermalMap caseId="c" rpm={rpm} state="steady" />) })
  return host
}
afterEach(() => { document.body.innerHTML = ""; fetchMock.mockReset() })

describe("ThermalMap", () => {
  it("renders the canvas and a °C bar", async () => {
    fetchMock.mockResolvedValue(data)
    const h = await mount()
    expect(h.querySelector("canvas")).not.toBeNull()
    expect(h.textContent).toContain("°C")
  })
  it("says so for a speed without a map", async () => {
    fetchMock.mockResolvedValue(data)
    expect((await mount(5000)).textContent).toContain("No map for this speed")
  })
  it("shows the error state", async () => {
    fetchMock.mockRejectedValue(new Error("x"))
    expect((await mount()).textContent).toContain("could not be loaded")
  })
})
