import { useState, type ComponentProps } from "react"
import createPlotlyComponent from "react-plotly.js/factory"
import Plotly, { type Data, type Layout } from "plotly.js-dist-min"
import type { Trace } from "@/lib/analysis"

const PlotBase = createPlotlyComponent(Plotly)

type PlotProps = ComponentProps<typeof PlotBase>

/** Fills its container and follows resizes; the clipping wrapper keeps a stale wide svg from holding the page wide. */
export function Plot({ layout, style, ...rest }: PlotProps) {
  return (
    <div className="w-full min-w-0 overflow-hidden">
      <PlotBase {...rest} layout={{ ...(layout as object), autosize: true }} useResizeHandler style={{ width: "100%", ...style }} />
    </div>
  )
}

const readColors = () => {
  const s = getComputedStyle(document.documentElement)
  const v = (n: string) => s.getPropertyValue(n).trim()
  return {
    primary: v("--primary"),
    fg: v("--foreground"),
    muted: v("--muted-foreground"),
    faint: v("--faint"),
    grid: v("--border"),
    zero: v("--border-strong"),
  }
}

/** Theme tokens, read from the document once. */
export function useColors() {
  return useState(readColors)[0]
}

interface LinePlotProps {
  data: Trace[]
  /** The legend is dropped for a single series. */
  legend?: boolean
  xTitle: string
  yTitle: string
  /** Title of the right-hand axis, for traces with `yaxis: "y2"`. */
  y2Title?: string
  height?: number
}

/** A themed line chart with the legend below the axes, readable from 375 px up. */
export function LinePlot({ data, xTitle, yTitle, y2Title, legend = true, height = 320 }: LinePlotProps) {
  const c = useColors()
  const axis = (text: string, extra = {}) => ({ title: { text }, gridcolor: c.grid, color: c.fg, ...extra })
  const layout = {
    height,
    margin: { l: 60, r: y2Title ? 60 : 10, t: 10, b: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Geist, sans-serif", color: c.fg },
    xaxis: axis(xTitle),
    yaxis: axis(yTitle),
    ...(y2Title && { yaxis2: axis(y2Title, { overlaying: "y", side: "right", showgrid: false }) }),
    showlegend: legend,
    legend: { orientation: "h", y: -0.25 },
  }
  return <Plot data={data as Data[]} layout={layout as Partial<Layout>} config={{ responsive: true, displaylogo: false }} />
}
