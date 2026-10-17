import { useId } from "react"
import { MotorGlyph } from "./MotorGlyph"

/** The 8/6 switched reluctance motor outline in the current text colour. */
export function SrmLogo({ size = 20, title = "SRM designer" }: { size?: number; title?: string }) {
  const titleId = useId()
  return (
    <svg
      role="img"
      aria-labelledby={titleId}
      width={size}
      height={size}
      viewBox="-50 -50 100 100"
      className="shrink-0"
    >
      <title id={titleId}>{title}</title>
      <MotorGlyph ns={8} nr={6} />
    </svg>
  )
}
