import { inferno } from "@/lib/inferno"

const GRADIENT = `linear-gradient(to top, ${Array.from({ length: 9 }, (_, i) => {
  const [r, g, b] = inferno(i / 8)
  return `rgb(${r},${g},${b})`
}).join(", ")})`

/** Vertical inferno bar from `lo` to bMax (default |B| in T from 0), with an optional mark at the last B-H point. */
export default function ColorBar({ bMax, bLast, lo = 0, unit = "T", label = "|B|" }: { bMax: number; bLast?: number; lo?: number; unit?: string; label?: string }) {
  const at = (v: number) => `${(100 * (v - lo)) / (bMax - lo)}%`
  const dec = unit === "T" ? 2 : 0
  return (
    <div className="flex h-64 shrink-0 gap-2 text-xs text-foreground" role="img"
      aria-label={`${label} colour scale, ${lo.toFixed(dec)} to ${bMax.toFixed(dec)} ${unit}${bLast == null ? "" : `; last B-H point ${bLast.toFixed(2)} T`}`}>
      <div className="relative w-4 rounded border border-border" style={{ background: GRADIENT }}>
        {bLast != null && <div className="absolute left-0 right-0 border-t-2 border-foreground" style={{ bottom: at(bLast) }} />}
      </div>
      <div className="relative w-28">
        {(bLast == null || bLast < 0.93 * bMax) && <span className="absolute top-0 -translate-y-1/2">{bMax.toFixed(dec)} {unit}</span>}
        <span className="absolute bottom-0 translate-y-1/2">{lo.toFixed(dec)} {unit}</span>
        {bLast != null && <span className="absolute translate-y-1/2" style={{ bottom: at(bLast) }}>last B-H point {bLast.toFixed(2)} T</span>}
      </div>
    </div>
  )
}
