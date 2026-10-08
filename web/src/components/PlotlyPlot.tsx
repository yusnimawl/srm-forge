import { useEffect, useState, type ComponentProps } from "react"
import createPlotlyComponent from "react-plotly.js/factory"
import Plotly from "plotly.js-dist-min"

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
  return { primary: v("--primary"), fg: v("--foreground"), muted: v("--muted-foreground"), grid: v("--border") }
}

/** Theme tokens are read from the document so plots follow light and dark. */
export function useColors() {
  const [colors, setColors] = useState(readColors)
  useEffect(() => {
    const obs = new MutationObserver(() => setColors(readColors()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] })
    return () => obs.disconnect()
  }, [])
  return colors
}
