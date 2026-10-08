// The one conversion table between the UI units and SI (the API is SI).
export type Unit =
  | "mm" | "rpm" | "kW" | "Nm" | "V" | "A" | "A/mm2"
  | "kg" | "mH" | "mOhm" | "mWb" | "deg" | "m" | "W" | "%" | "T"

/** SI value = UI value * FACTOR. */
const FACTOR: Record<Unit, number> = {
  mm: 1e-3,
  rpm: 1,
  kW: 1e3,
  Nm: 1,
  V: 1,
  A: 1,
  "A/mm2": 1e6,
  kg: 1,
  mH: 1e-3,
  mOhm: 1e-3,
  mWb: 1e-3,
  deg: Math.PI / 180,
  m: 1,
  W: 1,
  "%": 1e-2,
  T: 1,
}

export const UNIT_LABEL: Record<Unit, string> = {
  mm: "mm",
  rpm: "rpm",
  kW: "kW",
  Nm: "N·m",
  V: "V",
  A: "A",
  "A/mm2": "A/mm²",
  kg: "kg",
  mH: "mH",
  mOhm: "mΩ",
  mWb: "mWb",
  deg: "°",
  m: "m",
  W: "W",
  "%": "%",
  T: "T",
}

export const toSI = (value: number, unit: Unit): number => value * FACTOR[unit]
export const fromSI = (value: number, unit: Unit): number => value / FACTOR[unit]
