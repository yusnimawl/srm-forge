import type { Data, Layout } from "plotly.js-dist-min"
import { LINE_COLORS, type Trace } from "./analysis"

/** Theme token values the chart theme is built from. */
export interface PlotColors {
  primary: string
  fg: string
  muted: string
  faint: string
  grid: string
  zero: string
  raised: string
  strong: string
}

/** The one chart theme: transparent panels, hairline grid, series palette. */
export function plotTheme(c: PlotColors): Partial<Layout> {
  const axis = {
    gridcolor: c.grid,
    zerolinecolor: c.zero,
    linecolor: c.grid,
    color: c.muted,
    tickfont: { family: "Geist Mono, ui-monospace, monospace", size: 11, color: c.muted },
  }
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Geist, ui-sans-serif, system-ui, sans-serif", color: c.muted },
    xaxis: axis,
    yaxis: axis,
    colorway: LINE_COLORS,
    hoverlabel: { bgcolor: c.raised, bordercolor: c.strong, font: { color: c.fg, family: "Geist, ui-sans-serif, system-ui, sans-serif" } },
    modebar: { bgcolor: "rgba(0,0,0,0)", color: c.muted, activecolor: c.fg },
  }
}

/** Traces as Plotly data. */
export const toPlotData = (traces: Trace[]): Data[] => traces as Data[]

/** A themed line-chart layout with the legend below the axes; `y2Title` adds a right-hand axis. */
export function lineLayout(theme: Partial<Layout>, xTitle: string, yTitle: string, y2Title?: string, legend = true, height = 320): Partial<Layout> {
  const axis = (text: string, extra = {}) => ({ ...theme.xaxis, title: { text }, ...extra })
  return {
    ...theme,
    height,
    margin: { l: 60, r: y2Title ? 60 : 10, t: 10, b: 50 },
    xaxis: axis(xTitle),
    yaxis: axis(yTitle),
    ...(y2Title && { yaxis2: axis(y2Title, { overlaying: "y", side: "right", showgrid: false }) }),
    showlegend: legend,
    legend: { orientation: "h", y: -0.25 },
  } as Partial<Layout>
}
