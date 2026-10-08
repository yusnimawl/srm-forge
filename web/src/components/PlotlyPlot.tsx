import { useEffect, useState } from "react"
import createPlotlyComponent from "react-plotly.js/factory"
import Plotly from "plotly.js-dist-min"

export const Plot = createPlotlyComponent(Plotly)

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
