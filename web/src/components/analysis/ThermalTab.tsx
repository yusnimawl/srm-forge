import { Fragment, useMemo, useState, type ReactNode } from "react"
import type { Data, Layout } from "plotly.js-dist-min"
import type { Evaluation } from "@/api/types"
import { Plot, plotTheme, useColors } from "@/components/PlotlyPlot"
import ThermalMap from "./ThermalMap"
import { fmt } from "@/lib/format"
import { coolingText, curveSpec, passedSpeeds, tabState, tornadoSpec, type Rating } from "@/lib/thermal"

const HEADING = "text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground"
const CFG = { responsive: true, displaylogo: false }
const SMALL_GAP_M = 0.0003
// Hidden at 640 px and below; the row expands there instead.
const WIDE = "max-[640px]:hidden"

const temp = (c: number | null | undefined) => (c == null || !Number.isFinite(c) ? "no steady state" : `${fmt(c, 3)} °C`)

/** Open content at 641 px and wider; a closed disclosure below. */
function Collapsible({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <div className="max-[640px]:hidden">{children}</div>
      <details className="min-[641px]:hidden"><summary className="text-sm text-muted-foreground">{title}</summary>{children}</details>
    </>
  )
}

function Verdict({ text }: { text: string }) {
  const bad = text.startsWith("✗")
  return <p role="status" className={`text-sm font-medium ${bad ? "text-destructive" : "text-foreground"}`}>{text}</p>
}

function SpeedTable({ ev, expanded, onToggle }: { ev: Evaluation; expanded: number | null; onToggle: (rpm: number) => void }) {
  const rating = ev.rating!
  const need = new Map((ev.thermal_summary?.speeds ?? []).map((s) => [s.rpm, s]))
  const th = "px-2 py-1 text-left font-medium"
  const lock = "sticky left-0 bg-card"
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-muted-foreground">
          <tr>
            <th className={`${th} ${lock}`}>Speed (r/min)</th>
            <th className={`${th} ${WIDE}`}>Need cont/peak (N·m)</th>
            <th className={th}>Cont</th>
            <th className={th}>Peak</th>
            <th className={th}>Binds cont/peak</th>
            <th className={`${th} ${WIDE}`}>Hot spot</th>
            <th className={`${th} ${WIDE}`}>Rotor</th>
          </tr>
        </thead>
        <tbody>
          {rating.speeds.map((s) => {
            const n = need.get(s.rpm)
            const open = expanded === s.rpm
            const rotor = temp(s.rated?.rotor_c)
            const hot = n?.hot_spot_text || temp(s.hot_spot_c)
            return (
              <Fragment key={s.rpm}>
                <tr data-speed={s.rpm} className="cursor-pointer border-t border-border" onClick={() => onToggle(s.rpm as number)}>
                  <td className={`px-2 py-1 font-mono ${lock}`}>{fmt(s.rpm)}</td>
                  <td className={`px-2 py-1 font-mono ${WIDE}`}>{n?.need_continuous_nm != null ? fmt(n.need_continuous_nm) : "–"} / {n?.need_peak_nm != null ? fmt(n.need_peak_nm) : "–"}</td>
                  <td className="px-2 py-1 font-mono">{fmt(s.rated_continuous_nm ?? null)}</td>
                  <td className="px-2 py-1 font-mono">{fmt(s.rated_peak_nm ?? null)}</td>
                  <td className="px-2 py-1">{n ? `${n.binds_continuous} / ${n.binds_peak}` : "–"}</td>
                  <td className={`px-2 py-1 ${WIDE}`}>{hot}{n?.headroom_k != null && ` · ${fmt(n.headroom_k, 2)} K headroom`}</td>
                  <td className={`px-2 py-1 font-mono ${WIDE}`}>{rotor}</td>
                </tr>
                {open && (
                  <tr className="min-[641px]:hidden">
                    <td colSpan={4} className="px-2 pb-2 text-muted-foreground">
                      Need {n?.need_continuous_nm != null ? fmt(n.need_continuous_nm) : "–"} / {n?.need_peak_nm != null ? fmt(n.need_peak_nm) : "–"} N·m · hot spot {hot}
                      {n?.headroom_k != null && ` (${fmt(n.headroom_k, 2)} K headroom)`} · rotor {rotor}
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function RotorLine({ rating }: { rating: Rating }) {
  const st = rating.stress
  const gap = rating.gap
  const air = gap?.air_gap_m
  const cases = Object.entries(gap?.cases ?? {}).filter(([, c]) => c.closure != null)
  const mm = (m: number) => fmt(m * 1000, 2)
  return (
    <p className="text-sm">
      Rotor:{" "}
      {st?.status === "ok" || st?.status == null
        ? <>SF {fmt(st?.safety_factor ?? rating.stress_safety_factor, 2)} at {fmt(st?.check_speed_rpm)} r/min · speed limit {fmt(st?.speed_limit_rpm)} r/min</>
        : <>stress {st.status.replaceAll("_", " ")}</>}
      {air != null && cases.length > 0 && (
        <> · gap closure {cases.map(([k, c]) => `${k.replaceAll("_", " ")} ${mm(c.closure as number)}`).join(", ")} mm of {mm(air)} mm
          (against {mm(SMALL_GAP_M)} mm: {cases.map(([k, c]) => `${k.replaceAll("_", " ")} ${fmt(((c.closure as number) / SMALL_GAP_M) * 100, 2)} %`).join(", ")})</>
      )}
    </p>
  )
}

function Rated({ ev, caseId }: { ev: Evaluation; caseId?: string }) {
  const rating = ev.rating!
  const summary = ev.thermal_summary
  const full = tabState(ev) === "full"
  const [expanded, setExpanded] = useState<number | null>(null)
  const [picked, setPicked] = useState<number | null>(null)
  const [state, setState] = useState<"steady" | "peak">("steady")
  const rpm = picked ?? summary?.least_margin_rpm ?? rating.speeds[0]?.rpm
  const colors = useColors()
  const theme = plotTheme(colors)
  const curves = useMemo(() => curveSpec(rating, summary), [rating, summary])
  const share = summary?.shares.find((s) => s.rpm === rpm)
  const rows = share?.rows ?? []
  const tornado = useMemo(() => tornadoSpec(rows), [rows])
  const axis = (text: string) => ({ ...theme.xaxis, title: { text } })
  const runaway = rows.filter((r) => r.runaway)
  const top = rows[0]
  const at = rating.speeds.find((s) => s.rpm === rpm)
  const sumSpeed = summary?.speeds.find((s) => s.rpm === rpm)
  const endHot = state === "steady" ? (sumSpeed?.hot_spot_text?.startsWith("end winding") || at?.hot_spot_at?.startsWith("end_")) : at?.peak_hot_spot_at?.startsWith("end_")
  const endC = state === "steady" ? at?.hot_spot_c : at?.peak_hot_spot_c
  const endNote = endHot ? `hot spot: end winding (lumped, not in this section)${endC != null && Number.isFinite(endC) ? ` ${fmt(endC, 3)} °C` : ""}` : null
  return (
    <div className="@container space-y-4 pt-2">
      <h2 className={HEADING}>Thermal · rated (every input at its unfavourable end) · class {rating.insulation_class}, limit {fmt(rating.limit_c, 3)} °C</h2>
      {full && summary && <Verdict text={summary.verdict.text} />}
      <SpeedTable ev={ev} expanded={expanded} onToggle={(r) => setExpanded(expanded === r ? null : r)} />
      <Plot
        data={curves as Data[]}
        layout={{ ...theme, height: 320, margin: { l: 60, r: 10, t: 10, b: 90 }, xaxis: axis("Speed (r/min)"), yaxis: axis("Torque (N·m)"), legend: { orientation: "h", y: -0.3 } } as Partial<Layout>}
        config={CFG}
      />
      {full ? (
        <div className="grid gap-6 @3xl:grid-cols-2">
          <section data-testid="thermal-map-slot" className="space-y-2">
            <h3 className={HEADING}>Temperature at {fmt(rpm)} r/min</h3>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <label className="flex items-center gap-2">Speed
                <select className="rounded border border-border bg-card px-2 py-1" value={rpm ?? ""} onChange={(e) => setPicked(Number(e.target.value))}>
                  {rating.speeds.map((s) => <option key={s.rpm} value={s.rpm ?? ""}>{fmt(s.rpm)} r/min</option>)}
                </select>
              </label>
              <div role="group" aria-label="Thermal state" className="flex gap-1">
                {(["steady", "peak"] as const).map((k) => (
                  <button key={k} type="button" aria-pressed={state === k} onClick={() => setState(k)}
                    className={`rounded border border-border px-2 py-1 ${state === k ? "bg-muted font-medium" : ""}`}>
                    {k === "steady" ? "Steady" : "Peak end"}
                  </button>
                ))}
              </div>
            </div>
            {caseId && rpm != null && <ThermalMap caseId={caseId} rpm={rpm} state={state} />}
            {endNote && <p className="text-sm">{endNote}</p>}
          </section>
          <section className="space-y-2">
            <h3 className={HEADING}>Biggest uncertainties at {fmt(rpm)} r/min, K</h3>
            <Plot
              data={tornado as Data[]}
              layout={{ ...theme, height: 300, margin: { l: 150, r: 60, t: 10, b: 40 }, xaxis: axis("Hot-spot rise (K)"), yaxis: { ...theme.yaxis, autorange: "reversed" } } as Partial<Layout>}
              config={{ ...CFG, displayModeBar: false }}
            />
            {runaway.length > 0 && <p className="text-sm text-muted-foreground">Shown as runaway (no steady state): {runaway.map((r) => r.label).join(", ")}</p>}
            {top?.hint && <p className="text-sm">{top.hint}</p>}
          </section>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Edit, then Evaluate, for full detail</p>
      )}
      {full && (
        <Collapsible title="Rotor and cooling">
          <RotorLine rating={rating} />
          {rating.cooling && <p className="text-sm">Cooling: {coolingText(rating.cooling)}</p>}
        </Collapsible>
      )}
      {rating.notes.length > 0 && (
        <details className="text-sm text-muted-foreground">
          <summary>Notes ({rating.notes.length})</summary>
          <ul className="list-disc space-y-1 pl-5">{rating.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </details>
      )}
    </div>
  )
}

function FailedCheck({ ev }: { ev: Evaluation }) {
  const c = ev.thermal_check
  const hot = ev.thermal_summary?.verdict.hot_spot_c ?? c?.hot_c
  const passed = c ? passedSpeeds(c) : 0
  return (
    <>
      {hot != null && Number.isFinite(hot) && <p className="text-sm">Hot spot at the required torque: {fmt(hot, 3)} °C</p>}
      <p className="text-sm">{passed} {passed === 1 ? "speed" : "speeds"} passed before the failing speed</p>
    </>
  )
}

export default function ThermalTab({ evaluation, caseId }: { evaluation: Evaluation; caseId?: string }) {
  const state = tabState(evaluation)
  if (state === "unrated") return <p className="pt-2 text-sm text-muted-foreground">{evaluation.error || "Not thermally rated."}</p>
  if (state === "check-only") {
    return (
      <div className="space-y-2 pt-2">
        <Verdict text={evaluation.thermal_summary?.verdict.text ?? "✗ The thermal check failed"} />
        <FailedCheck ev={evaluation} />
        {(evaluation.thermal_check?.notes ?? []).map((n) => <p key={n} className="text-sm text-muted-foreground">{n}</p>)}
        <p className="text-sm text-muted-foreground">Make a case and Evaluate for the full rating</p>
      </div>
    )
  }
  return <Rated ev={evaluation} caseId={caseId} />
}
