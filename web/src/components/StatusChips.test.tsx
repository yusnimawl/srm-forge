import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { StatusChips } from "./StatusChips"

const html = (el: React.ReactElement) => renderToStaticMarkup(el)

describe("StatusChips", () => {
  it("shows no j_limit chip without an evaluation", () => {
    for (const evaluation of [undefined, null]) {
      const out = html(<StatusChips evaluation={evaluation} />)
      expect(out).toContain("Unvalidated")
      expect(out).not.toContain("j_limit")
    }
  })
  it("says not recorded for an evaluation stored without j_limit", () => {
    expect(html(<StatusChips evaluation={{ j_limit: null }} />)).toContain("Peak only · j_limit not recorded")
    expect(html(<StatusChips evaluation={{}} />)).toContain("Peak only · j_limit not recorded")
  })
  it("shows the assumed j_limit and the verified version", () => {
    const out = html(<StatusChips engineVersion="0.4.0" evaluation={{ j_limit: 20e6 }} />)
    expect(out).toContain("2D-verified · srmcore 0.4.0")
    expect(out).toContain("Peak only · assumes j_limit 20 A/mm²")
  })
})
