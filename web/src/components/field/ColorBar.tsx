import { viridis } from "@/lib/viridis"

const GRADIENT = `linear-gradient(to top, ${Array.from({ length: 9 }, (_, i) => {
  const [r, g, b] = viridis(i / 8)
  return `rgb(${r},${g},${b})`
}).join(", ")})`

/** Vertical viridis bar for |B| in T from 0 to bMax, with a mark at the last B-H point. */
export default function ColorBar({ bMax, bLast }: { bMax: number; bLast: number }) {
  const at = (v: number) => `${(100 * v) / bMax}%`
  return (
    <div className="flex h-64 shrink-0 gap-2 text-xs text-foreground" role="img"
      aria-label={`|B| colour scale, 0 to ${bMax.toFixed(2)} T; last B-H point ${bLast.toFixed(2)} T`}>
      <div className="relative w-4 rounded border border-border" style={{ background: GRADIENT }}>
        <div className="absolute left-0 right-0 border-t-2 border-foreground" style={{ bottom: at(bLast) }} />
      </div>
      <div className="relative w-28">
        {bLast < 0.93 * bMax && <span className="absolute top-0 -translate-y-1/2">{bMax.toFixed(2)} T</span>}
        <span className="absolute bottom-0 translate-y-1/2">0 T</span>
        <span className="absolute translate-y-1/2" style={{ bottom: at(bLast) }}>last B-H point {bLast.toFixed(2)} T</span>
      </div>
    </div>
  )
}
