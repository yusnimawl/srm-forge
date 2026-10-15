// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

const navigate = vi.fn()
vi.mock("react-router", () => ({ useNavigate: () => navigate }))

import { DxfImportDialog, showInGraphs } from "./DxfImportDialog"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

async function pick(fetchMock: typeof fetch) {
  vi.stubGlobal("fetch", fetchMock)
  const host = document.createElement("div")
  document.body.append(host)
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  await act(async () => {
    createRoot(host).render(
      <QueryClientProvider client={qc}>
        <DxfImportDialog caseId="p1" open onOpenChange={() => {}} />
      </QueryClientProvider>,
    )
  })
  const input = document.body.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(["0\nEOF"], "m.dxf")
  Object.defineProperty(input, "files", { value: [file] })
  await act(async () => {
    input.dispatchEvent(new Event("change", { bubbles: true }))
  })
  await act(async () => {
    ;(Array.from(document.body.querySelectorAll("button")).find((b) => b.textContent === "Import") as HTMLButtonElement).click()
  })
  await act(async () => {})
}

afterEach(() => {
  document.body.innerHTML = ""
  navigate.mockReset()
  vi.unstubAllGlobals()
})

describe("DxfImportDialog", () => {
  it("lists every rejection message and stays on the page", async () => {
    await pick(() => json(422, { errors: [{ loc: ["iron"], msg: "first problem" }, { loc: ["iron"], msg: "second problem" }], warnings: [] }) as never)
    expect(document.body.textContent).toContain("first problem")
    expect(document.body.textContent).toContain("second problem")
    expect(navigate).not.toHaveBeenCalled()
  })
  it("opens the new case on success", async () => {
    const made = { id: "c2", show_in_graphs: false }
    await pick(((url: string, init?: RequestInit) => {
      if (url.endsWith("/dxf")) return json(201, { case: made, warnings: [] })
      if (url === "/api/cases" && !init?.method) return json(200, [])
      return json(200, {})
    }) as never)
    expect(navigate).toHaveBeenCalledWith("/cases/c2")
  })
})

describe("showInGraphs", () => {
  it("does not count a case that is already shown twice", async () => {
    const list = ["p1", "a", "b", "c", "d"].map((id) => ({ id, show_in_graphs: true })).concat([{ id: "new", show_in_graphs: false }])
    const calls: string[] = []
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") calls.push(url)
      return json(200, init?.method ? {} : list)
    })
    await showInGraphs(["p1", "new"])
    expect(calls).toEqual(["/api/cases/new"])
  })
})
