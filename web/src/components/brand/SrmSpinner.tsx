import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { spinnerFrame } from "@/lib/srmGlyph"
import { MotorGlyph } from "./MotorGlyph"

const STILL = { statorAngle: 0, rotorAngle: 0, poles: [8, 6] as [number, number], scale: 1 }

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

/**
 * A turning motor for loading states: the stator clockwise, the rotor counter-clockwise, the pole counts
 * stepping 6/4, 8/6, 12/8. Under reduced motion it holds a still 8/6 and requests no animation frames.
 * `label` is the accessible name (and the visible caption when `showLabel`).
 */
export function SrmSpinner({
  size = 28,
  label,
  showLabel = false,
  className,
}: {
  size?: number
  label: string
  showLabel?: boolean
  className?: string
}) {
  const [frame, setFrame] = useState(STILL)

  useEffect(() => {
    if (prefersReducedMotion()) return
    let raf = 0
    let start: number | null = null
    const tick = (now: number) => {
      start ??= now
      setFrame(spinnerFrame((now - start) / 1000))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <div role="status" aria-busy="true" className={cn("flex items-center gap-2 text-muted-foreground", className)}>
      <svg aria-hidden width={size} height={size} viewBox="-50 -50 100 100" className="shrink-0">
        <MotorGlyph
          ns={frame.poles[0]}
          nr={frame.poles[1]}
          poleScale={frame.scale}
          statorAngle={frame.statorAngle}
          rotorAngle={frame.rotorAngle}
        />
      </svg>
      <span className={showLabel ? "text-sm" : "sr-only"}>{label}</span>
    </div>
  )
}
