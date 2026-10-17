import { useId } from "react"
import { MotorGlyph } from "./MotorGlyph"

/** The 8/6 switched reluctance motor outline in the current text colour. A decorative logo is hidden from assistive tech. */
export function SrmLogo({ size = 20, title = "SRM designer", decorative = false }: { size?: number; title?: string; decorative?: boolean }) {
  const titleId = useId()
  return (
    <svg
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-labelledby": titleId })}
      width={size}
      height={size}
      viewBox="-50 -50 100 100"
      className="shrink-0"
    >
      {!decorative && <title id={titleId}>{title}</title>}
      <MotorGlyph ns={8} nr={6} />
    </svg>
  )
}
