import { download } from "@/lib/exports"
import { buildReport } from "./template"
import { collect } from "./collect"
import { renderFrames } from "./frames"

/** Builds the offline run report of a case and saves it as `<fileStem>-report.html`. Loaded on demand: it carries Plotly's source. */
export async function exportReport(caseId: string, fileStem: string, onStep: (msg: string) => void): Promise<void> {
  const plotly = (await import("plotly.js-dist-min/plotly.min.js?raw")).default
  const data = await collect(caseId, onStep, renderFrames)
  onStep("Building the file")
  download(`${fileStem}-report.html`, new Blob([buildReport(data, plotly)], { type: "text/html;charset=utf-8" }))
}
