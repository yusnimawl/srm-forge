// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { BeforeAfterTable, COMPARE_POLL_MS } from "./BeforeAfterTable"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ""
})

describe("BeforeAfterTable", () => {
  it("refetches while the parent is not evaluated and then shows the rows", async () => {
    vi.useFakeTimers()
    let evaluated = false
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({
        parent_id: "p", parent_evaluated: evaluated,
        rows: evaluated ? [{ name: "Peak torque", unit: "N·m", before: 1, after: 2 }] : [],
      }), { status: 200, headers: { "Content-Type": "application/json" } })))
    vi.stubGlobal("fetch", fetchMock)
    const host = document.createElement("div")
    document.body.append(host)
    await act(async () => {
      createRoot(host).render(
        <QueryClientProvider client={new QueryClient()}>
          <BeforeAfterTable caseId="c" evaluated={false} />
        </QueryClientProvider>,
      )
    })
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })
    expect(host.textContent).toContain("Parent not evaluated")
    evaluated = true
    await act(async () => { await vi.advanceTimersByTimeAsync(COMPARE_POLL_MS + 100) })
    expect(host.textContent).toContain("Peak torque")
    expect(host.textContent).not.toContain("Parent not evaluated")
  })
})
