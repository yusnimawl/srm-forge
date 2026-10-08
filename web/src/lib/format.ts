import { fromSI, type Unit } from "./units"

const THIN_SPACE = " "

/**
 * `digits` significant digits, never in exponent form for ordinary magnitudes.
 * Values with |v| >= 10000 get a thin space between groups of three digits in
 * the integer part; smaller values (years, rpm below 10 000) stay ungrouped.
 */
export function fmt(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—"
  const text = String(Number(value.toPrecision(digits)))
  if (Math.abs(value) < 1e4) return text
  const [int, frac] = text.split(".")
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, THIN_SPACE)
  return frac ? `${grouped}.${frac}` : grouped
}

export const fmtSI = (value: number | null | undefined, unit: Unit, digits = 3): string =>
  fmt(value == null ? value : fromSI(value, unit), digits)
