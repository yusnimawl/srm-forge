import { useId } from "react"
import {
  SHAFT_HOLE_R,
  SHAFT_R,
  STATOR_RING_R,
  STATOR_RING_STROKE,
  srmGlyph,
  type Rect,
} from "@/lib/srmGlyph"

function PoleRects({ rects }: { rects: Rect[] }) {
  return (
    <>
      {rects.map((r, i) => (
        <rect key={i} x={r.x} y={r.y} width={r.width} height={r.height} transform={`rotate(${r.angle})`} />
      ))}
    </>
  )
}

type Props = {
  ns: number
  nr: number
  poleScale?: number
  statorAngle?: number
  rotorAngle?: number
}

/** Stator ring with inward poles and a rotor with a shaft hole, in a 100 x 100 viewBox centred at 0, filled with currentColor. */
export function MotorGlyph({ ns, nr, poleScale = 1, statorAngle = 0, rotorAngle = 0 }: Props) {
  const maskId = useId()
  const { stator, rotor } = srmGlyph(ns, nr, poleScale)
  return (
    <>
      <g transform={`rotate(${statorAngle})`}>
        <circle r={STATOR_RING_R} fill="none" stroke="currentColor" strokeWidth={STATOR_RING_STROKE} />
        <g fill="currentColor">
          <PoleRects rects={stator} />
        </g>
      </g>
      <mask id={maskId} maskUnits="userSpaceOnUse" x={-50} y={-50} width={100} height={100}>
        <rect x={-50} y={-50} width={100} height={100} fill="white" />
        <circle r={SHAFT_HOLE_R} fill="black" />
      </mask>
      <g transform={`rotate(${rotorAngle})`} mask={`url(#${maskId})`} fill="currentColor">
        <circle r={SHAFT_R} />
        <PoleRects rects={rotor} />
      </g>
    </>
  )
}
