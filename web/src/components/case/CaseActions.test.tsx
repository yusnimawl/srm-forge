// @vitest-environment jsdom
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Case } from "@/api/types"

vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }))

import { CaseActions } from "./CaseActions"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: ReturnType<typeof createRoot> | null = null
afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
})

async function reportButton(evaluation: unknown) {
  const host = document.createElement("div")
  document.body.append(host)
  await act(async () => {
    root = createRoot(host)
    root.render(
      <QueryClientProvider client={new QueryClient()}>
        <CaseActions data={{ id: "c", label: "x", jobs: [], evaluation } as unknown as Case} editable={false} ready savedText="" flush={async () => true} />
      </QueryClientProvider>,
    )
  })
  const buttons = () => Array.from(document.body.querySelectorAll("button"))
  await act(async () => {
    buttons().find((b) => b.textContent === "Export")!.click()
  })
  return buttons().find((b) => b.textContent === "Run report (HTML)")!
}

describe("CaseActions run report", () => {
  it("run report disabled without evaluation", async () => expect((await reportButton(null)).disabled).toBe(true))
  it("enabled with evaluation", async () => expect((await reportButton({ status: "ok" })).disabled).toBe(false))
})
