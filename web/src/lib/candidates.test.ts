import { describe, expect, it } from "vitest"
import type { Evaluation } from "@/api/types"
import { AXES, toRows } from "./candidates"
import { fmt } from "./format"

// Only the fields toRows reads are filled; the full generated design has many more.
const ev = (id: string, status: string, extra = {}) => ({
  id,
  design: { machine: { n_stator_poles: 8, n_rotor_poles: 6, stator_outer_diameter: 0.12 } },
  status,
  error: status === "ok" ? null : "boom",
  mass_kg: 3,
  winding: null,
  torque_ratio: 1.2,
  power_ratio: 1.1,
  peak_power_w: 2500,
  power_density_kw_per_kg: 0.8,
  efficiency_base: 0.9,
  feasible: true,
  ...extra,
}) as unknown as Evaluation

const result = {
  evaluations: [
    ev("a", "ok"),
    ev("b", "no_winding", { torque_ratio: null, power_ratio: null, feasible: false, peak_power_w: null }),
  ],
  pareto_ids: ["a"],
}

describe("toRows", () => {
  const rows = toRows(result)
  it("maps an ok evaluation", () => {
    expect(rows[0]).toMatchObject({ id: "a", poles: "8/6", od_mm: 120, peak_power_kw: 2.5, power_density: 0.8, pareto: true })
  })
  it("marks failed rows", () => {
    expect(rows[1].feasible).toBe(false)
    expect(rows[1].torque_ratio).toBeNull()
    expect(fmt(rows[1].torque_ratio)).toBe("—")
    expect(rows[1].pareto).toBe(false)
    expect(rows[1].status).toBe("no_winding")
  })
  it("names the axes", () => expect(AXES.mass_kg).toBe("Mass (kg)"))
})
