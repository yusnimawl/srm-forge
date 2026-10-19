import type { Layout } from "plotly.js-dist-min"
import type { Evaluation, MapArrays } from "@/api/types"
import { caseLine, designFactorTraces, inductanceCurves, performanceSeries, torqueCurves, type Trace } from "@/lib/analysis"
import { jLimitChip, lossChips, madeWithText, VERIFIED_LABEL, verifiedChip } from "@/lib/chips"
import { compareRows } from "@/lib/compare"
import { MACHINE_FIELDS, POLE_KEYS } from "@/lib/caseForm"
import { fmt, fmtSI } from "@/lib/format"
import { INFERNO_SCALE } from "@/lib/inferno"
import { contourData, lossKeyNumbers, pointLabel, ratedPoint, splitBars, type LossesResult } from "@/lib/losses"
import { pickAngles, psiCurves, torqueGrid } from "@/lib/mapCurves"
import { lineLayout, plotTheme, toPlotData, type PlotColors } from "@/lib/plotSpec"
import { SPEEDS } from "@/lib/playback"
import { fromSI, UNIT_LABEL, type Unit } from "@/lib/units"
import { atScale, turnsScale } from "@/lib/validation"
import { defaultSpeedIndex, waveformSeries } from "@/lib/waveforms"
import { PLAYER_SOURCE } from "./player"
import type { Finding, ReportData } from "./types"

/** The Graphite token values of `web/src/index.css` that the chart theme needs. */
const GRAPHITE: PlotColors = {
  primary: "#ededed",
  fg: "#ededed",
  muted: "#8a8a8a",
  faint: "#5c5c5c",
  grid: "#232323",
  zero: "#333333",
  raised: "#181818",
  strong: "#333333",
}

export const escapeHtml = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;")

/** JSON for an inline `<script type="application/json">`: every `<` becomes `\u003c`, which stays valid JSON and cannot
 *  close the tag or open a comment. */
export const jsonScript = (value: unknown): string => JSON.stringify(value).replace(/</g, "\\u003c")

/** Text safe inside an inline `<script>`: closing tags and comment openers are broken up. */
export const scriptSafe = (s: string): string => s.replace(/<\/(script)/gi, "<\\/$1").replace(/<!--/g, "<\\!--")

const e = escapeHtml
type Rec = Record<string, unknown>
const rec = (x: unknown): Rec => (x && typeof x === "object" && !Array.isArray(x) ? (x as Rec) : {})
const num = (x: unknown): number | null => (typeof x === "number" && Number.isFinite(x) ? x : null)
const u = (v: unknown, unit: Unit, digits = 4) => (num(v) == null ? "—" : fmtSI(num(v), unit, digits))
const withUnit = (text: string, unit: Unit) => (text === "—" ? text : `${text} ${UNIT_LABEL[unit]}`)

const CSS = `
:root{color-scheme:dark;--bg:#0a0a0a;--fg:#ededed;--card:#111111;--muted:#8a8a8a;--border:#232323;--border-strong:#333333;--ok:#9bd88a;--warn:#e8b04a;--bad:#f2716b;--iron:#2a2a2a;--iron-edge:#4a4a4a;--plot:#111111}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-sans-serif,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1100px;margin:0 auto;padding:16px}
section{margin:0 0 32px;min-width:0}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:12px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border);padding-bottom:6px;margin:0 0 12px}
h3{font-size:13px;margin:16px 0 6px}
.mono,td.n,th.n{font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums}
.muted{color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.chip{border:1px solid var(--border);border-radius:6px;padding:2px 10px;font-size:12.5px;color:var(--muted)}
.chip.ok::before,.chip.warn::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:7px;vertical-align:middle}
.chip.ok::before{background:var(--ok)}.chip.warn::before{background:var(--warn)}
.scroll{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%}
th,td{padding:5px 10px;text-align:left;border-bottom:1px solid var(--border);vertical-align:top}
th{font-weight:500;color:var(--muted);white-space:nowrap}
td.n,th.n{text-align:right;white-space:nowrap}
tr:last-child td{border-bottom:0}
.grid{display:grid;grid-template-columns:1fr;gap:16px}
@media(min-width:900px){.grid.two{grid-template-columns:1fr 1fr}}
.plot{width:100%;min-height:320px;background:var(--plot);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.outline svg{display:block;margin:0 auto;width:100%;max-width:360px;height:auto}
.not-run{border:1px dashed var(--border-strong);border-radius:10px;padding:12px;color:var(--muted)}
.findings ul{margin:0 0 12px;padding-left:20px}
.findings .warn{color:var(--warn)}.findings .ok{color:var(--ok)}.findings .missing{color:var(--muted)}
.findings li .topic{font-weight:500;margin-right:6px}
.anim img{display:block;width:100%;max-width:560px;margin:0 auto;border-radius:10px;background:#000}
.controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:12px 0}
.controls input[type=range]{flex:1 1 200px;min-width:120px}
button,select{background:var(--card);color:var(--fg);border:1px solid var(--border-strong);border-radius:8px;padding:6px 12px;font:inherit;min-height:36px}
@media print{
:root{color-scheme:light;--bg:#fff;--fg:#111;--card:#f6f6f6;--muted:#555;--border:#ccc;--border-strong:#aaa;--ok:#2d7a1f;--warn:#9a6a00;--bad:#b3261e;--plot:#fff}
.controls{display:none}
section + section{break-before:page}
.plot{break-inside:avoid}
.modebar-container{display:none}
.anim img{max-width:420px}
}
`

type Figure = { id: string; data: unknown[]; layout: unknown }

export function buildReport(data: ReportData, plotlySource: string): string {
  const { caseOut, report } = data
  const ev: Evaluation | null = caseOut.evaluation
  const inputs = rec(caseOut.inputs)
  const req = rec(inputs.requirements)
  const machine = rec(rec(inputs.design).machine)
  const theme = plotTheme(GRAPHITE)
  const figures: Figure[] = []

  /** One plot div; the figure is drawn by the player. */
  const plot = (traces: unknown[], layout: Partial<Layout>) => {
    const id = `p${figures.length + 1}`
    figures.push({ id, data: traces, layout: { ...layout, autosize: true } })
    return `<div class="plot" id="${id}"></div>`
  }
  const line = (traces: Trace[], xTitle: string, yTitle: string, y2Title?: string, legend = traces.length > 1) =>
    plot(toPlotData(traces), lineLayout(theme, xTitle, yTitle, y2Title, legend))
  const axis = (text: string, extra = {}) => ({ ...theme.xaxis, title: { text }, ...extra })
  const panel = { ...theme, height: 360, margin: { l: 60, r: 10, t: 10, b: 50 } }

  const table = (head: string[], rows: string[][], numeric = true) =>
    `<div class="scroll"><table><thead><tr>${head.map((h, k) => `<th${numeric && k > 0 ? ' class="n"' : ""}>${e(h)}</th>`).join("")}</tr></thead><tbody>${rows
      .map((r) => `<tr>${r.map((c, k) => `<td${numeric && k > 0 ? ' class="n"' : ""}>${e(c)}</td>`).join("")}</tr>`)
      .join("")}</tbody></table></div>`
  const kv = (rows: [string, string][]) =>
    `<div class="scroll"><table><tbody>${rows.map(([k, v]) => `<tr><th>${e(k)}</th><td class="n">${e(v)}</td></tr>`).join("")}</tbody></table></div>`
  const section = (id: string, title: string, body: string) => `<section id="${id}"><h2>${e(title)}</h2>${body}</section>`
  const notRun = (hint: string, reason = "") => `<div class="not-run">Not run — ${e(hint)}${reason ? `. ${e(reason)}` : ""}</div>`
  const unavailable = (reason: string) => `<div class="not-run">Unavailable: ${e(reason)}</div>`
  const chip = (c: { text: string; tone: string }) => `<span class="chip ${c.tone}">${e(c.text)}</span>`

  // header
  const validation = caseOut.validation
  const chips = [verifiedChip(validation?.label ? validation.engine_version : null), ...(ev ? [jLimitChip(ev.j_limit)] : [])]
  const v = report.versions
  const header = section(
    "header",
    "Run report",
    `<h1>${e(caseOut.label ?? caseOut.id)}</h1>
<div class="chips" role="note">${chips.map(chip).join("")}</div>
${kv([
  ["Case id", caseOut.id],
  ["Poles", caseOut.poles ?? "—"],
  ["Preset", caseOut.preset ?? "—"],
  ["Origin", caseOut.origin],
  ["Exported", report.generated],
  ["Versions", `srmcore ${v.srmcore ?? "?"}, srmapp ${v.srmapp ?? "?"}, srmweb ${v.srmweb ?? "?"}`],
  ["Evaluation", ev ? madeWithText(ev.srmapp_version) : "not evaluated"],
  ...(caseOut.comment ? ([["Comment", caseOut.comment]] as [string, string][]) : []),
])}`,
  )

  // findings
  const LEVELS: [Finding["level"], string][] = [["warn", "Warnings"], ["note", "Notes"], ["ok", "Passed"], ["missing", "Missing"]]
  const findings = section(
    "findings",
    "Findings",
    `<div class="findings">${
      report.findings.length === 0
        ? '<p class="muted">No findings.</p>'
        : LEVELS.map(([level, title]) => [title, report.findings.filter((f) => f.level === level), level] as const)
            .filter(([, fs]) => fs.length > 0)
            .map(([title, fs, level]) => `<h3>${e(title)}</h3><ul class="${level}">${fs.map((f) => `<li><span class="topic">${e(f.topic)}</span>${e(f.text)}</li>`).join("")}</ul>`)
            .join("")
    }</div>`,
  )

  // inputs
  const wires = (Array.isArray(req.wires) ? req.wires : []).map((w) => {
    const r = rec(w)
    const dims = Object.entries(r).filter(([, x]) => typeof x === "number").map(([k, x]) => `${k.replaceAll("_", " ")} ${fmtSI(x as number, "mm", 4)} mm`)
    return `${String(r.kind ?? "wire")}: ${dims.join(", ")}`
  })
  const reqRows: [string, string][] = [
    ["Peak power", withUnit(u(req.peak_power_w, "kW"), "kW")],
    ["Peak torque", withUnit(u(req.peak_torque_nm, "Nm"), "Nm")],
    ["Base speed", withUnit(u(req.base_speed_rpm, "rpm"), "rpm")],
    ["Max speed", withUnit(u(req.max_speed_rpm, "rpm"), "rpm")],
    ["Bus voltage", withUnit(u(req.bus_voltage_v, "V"), "V")],
    ["Max slot fill", fmt(num(req.max_slot_fill), 3)],
    ["Winding temperature", `${fmt(num(req.winding_temperature_c), 3)} °C`],
    ["Phase current", withUnit(u(req.phase_current_a, "A"), "A")],
    ["Max mass", withUnit(u(req.max_mass_kg, "kg"), "kg")],
    ["Max outer diameter", withUnit(u(req.max_outer_diameter_m, "mm"), "mm")],
    ["Wires", wires.length ? wires.join("; ") : "—"],
  ]
  const geoRows: [string, string][] = [
    ["Poles (stator/rotor), phases", POLE_KEYS.map((k) => fmt(num(machine[k]), 3)).join(" / ")],
    ...MACHINE_FIELDS.map((f): [string, string] => [f.label, f.unit ? withUnit(u(machine[f.key], f.unit), f.unit) : fmt(num(machine[f.key]), 4)]),
    ...(machine.iron ? ([["Iron", "imported from DXF"]] as [string, string][]) : []),
  ]
  const mats = rec(machine.materials)
  const matRows: [string, string][] = ["stator", "rotor", "shaft", "coil"].map((k) => [`${k[0].toUpperCase()}${k.slice(1)}`, String(mats[k] ?? "—")])
  const fixed = rec(inputs.winding)
  const windRows: [string, string][] =
    inputs.winding === "auto" || inputs.winding == null
      ? [["Winding", "chosen by the search"]]
      : [["Turns per pole", fmt(num(fixed.turns), 4)], ["Strands", fmt(num(fixed.strands), 4)], ["Paths", fmt(num(fixed.paths), 4)], ["Wire", fixed.wire == null ? "—" : String(fixed.wire)]]
  const jA = (x: unknown) => withUnit(u(x, "A/mm2"), "A/mm2")
  const driveRows: [string, string][] = [
    ["j_limit (RMS)", jA(inputs.j_limit)],
    ["j_peak", jA(inputs.j_peak)],
    ["j_peak_max", jA(inputs.j_peak_max)],
    ["Margin", fmt(num(inputs.margin), 3)],
  ]
  const inputsSection = section(
    "inputs",
    "Inputs",
    `<div class="grid two"><div><h3>Requirements</h3>${kv(reqRows)}</div><div><h3>Geometry</h3>${kv(geoRows)}</div>
<div><h3>Materials</h3>${kv(matRows)}</div><div><h3>Winding</h3>${kv(windRows)}<h3>Drive limits</h3>${kv(driveRows)}</div></div>`,
  )

  // outline
  const outline = section("outline", "Outline", data.outline.ok ? `<div class="outline">${data.outline.value}</div>` : unavailable(data.outline.reason))

  // key numbers
  const needEval = notRun("press Evaluate on the case")
  const key = ev?.key
  const w = ev?.winding
  const keyNumbers = section(
    "key-numbers",
    "Key numbers and winding",
    !ev
      ? needEval
      : `<div class="grid two"><div>${kv([
          ["La", withUnit(u(key?.la, "mH"), "mH")],
          ["Lu", withUnit(u(key?.lu, "mH"), "mH")],
          ["La/Lu", fmt(key?.la_lu, 4)],
          ["Peak torque", withUnit(u(key?.peak_torque, "Nm"), "Nm")],
          ["ψ max", withUnit(u(key?.psi_max, "mWb"), "mWb")],
          ["I max", withUnit(u(key?.i_max, "A"), "A")],
        ])}</div><div>${kv([
          ["Turns per pole", w ? String(w.turns) : "—"],
          ["Strands", w ? String(w.strands) : "—"],
          ["Paths", w ? String(w.paths) : "—"],
          ["Wire diameter", withUnit(u(w?.wire, "mm"), "mm")],
          ["Resistance", withUnit(u(w?.resistance, "mOhm"), "mOhm")],
          ["Copper mass", withUnit(u(w?.copper_mass, "kg"), "kg")],
        ])}</div><div>${kv([
          ["Mass", withUnit(u(ev.mass_kg, "kg"), "kg")],
          ["Torque ratio", fmt(ev.torque_ratio, 4)],
          ["Power ratio", fmt(ev.power_ratio, 4)],
          ["Peak power", withUnit(u(ev.peak_power_w, "kW"), "kW")],
          ["Power density", `${fmt(ev.power_density_kw_per_kg, 4)} kW/kg`],
          ["Efficiency at base speed", ev.efficiency_base == null ? "—" : `${fmt(ev.efficiency_base * 100, 4)} %`],
        ])}</div></div>`,
  )

  // map plots
  const map: MapArrays | null | undefined = ev?.map
  const mapBody = (() => {
    if (!ev || !map) return ev ? '<p class="muted">No map for this case.</p>' : needEval
    const all = psiCurves(map)
    const lines = pickAngles(map.angles, ev.key?.unaligned_angle ?? null).map((k, n) => ({
      type: "scatter", mode: "lines", name: `${fmt(all[k].angleDeg, 3)}°`, x: all[k].i, y: all[k].psi_mWb, line: caseLine(n),
    }))
    const grid = torqueGrid(map)
    const heat = {
      type: "heatmap", x: grid.i, y: grid.angleDeg, z: grid.torque, colorscale: INFERNO_SCALE,
      colorbar: { title: { text: "N·m", side: "right" }, tickfont: { color: GRAPHITE.muted } },
      hovertemplate: "i %{x:.3g} A<br>θ %{y:.3g}°<br>T %{z:.3g} N·m<extra></extra>",
    }
    const angleX = `Rotor angle (${UNIT_LABEL.deg} mechanical)`
    const parts = [
      `<h3>Flux linkage vs current</h3>${plot(lines, { ...panel, xaxis: axis("Current (A)"), yaxis: axis("ψ (mWb)"), legend: { title: { text: "Rotor angle" } } } as Partial<Layout>)}`,
      `<h3>Torque map</h3>${plot([heat], { ...panel, xaxis: axis("Current (A)"), yaxis: axis("Rotor angle (° mechanical)") } as Partial<Layout>)}`,
      `<h3>Torque vs rotor angle</h3>${line(torqueCurves(map), angleX, `Torque (${UNIT_LABEL.Nm})`)}`,
    ]
    if (ev.curves) {
      const c = ev.curves
      const d = designFactorTraces([{ label: "this case", curves: c }])
      parts.push(
        `<h3>Inductance vs rotor angle</h3>${line(inductanceCurves(c, map.angles), angleX, `L = ψ/i (${UNIT_LABEL.mH})`)}`,
        `<h3>Inductance vs current</h3>${line(d.inductance, `Current (${UNIT_LABEL.A})`, `L (${UNIT_LABEL.mH})`, undefined, true)}`,
        `<h3>k2 and pole flux density vs current</h3>${line(d.factors, `Current (${UNIT_LABEL.A})`, "k2", `B_sp (${UNIT_LABEL.T})`, true)}`,
        `<h3>B_sp·k2 vs La_sat/Lu</h3>${line(d.bspK2VsRatio, "La_sat / Lu", `B_sp·k2 (${UNIT_LABEL.T})`, undefined, false)}`,
        '<p class="muted">k2 = 1 − Lu/La_sat (Krishnan ch. 3).</p>',
      )
    }
    return `<div class="grid two">${parts.map((p) => `<div>${p}</div>`).join("")}</div>`
  })()
  const mapSection = section("map", "Map plots", mapBody)

  // performance and waveforms
  const perfBody = (() => {
    if (!ev) return needEval
    const s = performanceSeries(ev)
    if (s.torque.length === 0) return '<p class="muted">No performance data for this case.</p>'
    const x = "Speed (rpm)"
    const parts = [
      line(s.torque, x, `Torque (${UNIT_LABEL.Nm})`),
      line(s.power, x, `Power (${UNIT_LABEL.kW})`),
      line(s.efficiency, x, `Efficiency (${UNIT_LABEL["%"]})`),
      line(s.current, x, `Phase current, RMS (${UNIT_LABEL.A})`),
      line(s.lineCurrent, x, `Line current (${UNIT_LABEL.A})`, undefined, true),
      line(s.powerFactor, x, "Power factor"),
    ]
    let out = `<div class="grid two">${parts.map((p) => `<div>${p}</div>`).join("")}</div><p class="muted">Efficiency and power factor count copper loss only.</p>`
    const base = num(req.base_speed_rpm) ?? undefined
    const k = defaultSpeedIndex(ev, base)
    const wf = waveformSeries(ev, k)
    if (wf) {
      const X = "Rotor angle (° electrical, 0 = unaligned)"
      const speed = ev.envelope?.speeds_rpm[k]
      const wparts = [
        line(wf.current, X, `Phase current (${UNIT_LABEL.A})`, undefined, false),
        line(wf.psi, X, `Flux linkage (${UNIT_LABEL.mWb})`, undefined, false),
        line(wf.voltage, X, `Phase voltage (${UNIT_LABEL.V})`, undefined, false),
        line(wf.torque, X, `Phase torque (${UNIT_LABEL.Nm})`, undefined, false),
        line(wf.line, X, `Line current (${UNIT_LABEL.A})`, undefined, false),
        line(wf.loop, `Current (${UNIT_LABEL.A})`, `Flux linkage (${UNIT_LABEL.mWb})`, undefined, true),
      ]
      out += `<h3>Waveforms at ${e(speed == null ? "?" : String(Math.round(speed)))} rpm</h3><div class="grid two">${wparts.map((p) => `<div>${p}</div>`).join("")}</div>
<p class="muted">Phase A over one rotor pole pitch; line current sums all phases. Peak-only drive model.</p>`
    }
    return out
  })()
  const performance = section("performance", "Performance and waveforms", perfBody)

  // losses
  const lossesBody = (() => {
    if (!data.losses.ok) {
      const old = ev != null && !ev.srmapp_version
      return notRun(old ? "re-evaluate the case, then run Losses on the Losses tab" : "run Losses on the Losses tab", data.losses.reason)
    }
    return lossesHtml(data.losses.value)
  })()
  function lossesHtml(r: LossesResult) {
    const regions = [...new Set(r.points.flatMap((p) => Object.keys(p.iron)))]
    const rows = r.points.map((p) => [
      p.speed_rpm == null ? "?" : String(Math.round(p.speed_rpm)),
      fmt(p.torque_nm, 3),
      p.reached ? "yes" : "no",
      fmt(p.power_w, 4),
      fmt(p.copper_dc_w, 3),
      p.copper_ac_w == null ? "—" : fmt(p.copper_ac_w, 3),
      ...regions.map((k) => {
        const l = p.iron[k]
        return l ? `${fmt(l.hysteresis, 3)} / ${fmt(l.classical, 3)} / ${fmt(l.excess, 3)}` : "—"
      }),
      fmt(p.iron_w, 3),
      p.efficiency == null ? "—" : fmt(p.efficiency * 100, 3),
      p.iron_uncertainty_rel == null ? "—" : fmt(p.iron_uncertainty_rel * 100, 2),
      p.beyond_fit_range ? "yes" : "no",
    ])
    const head = ["Speed (rpm)", "Torque (N·m)", "Reached", "Power (W)", "Copper DC (W)", "Copper AC (W)", ...regions.map((k) => `Iron ${k.replaceAll("_", " ")} h / c / e (W)`), "Iron (W)", "Efficiency (%)", "Iron ± (%)", "Beyond fit"]
    const c = contourData(r)
    const reached = r.points.map((p, k) => [p, k] as const).filter(([p]) => p.reached)
    const nt = r.torque_fractions.length
    const contour = [
      {
        type: "contour", x: c.x, y: c.y, z: c.z, colorscale: INFERNO_SCALE, connectgaps: false, contours: { coloring: "heatmap" },
        colorbar: { title: { text: "Efficiency (%)" } }, hovertemplate: "%{x} rpm, level %{y}: %{z:.1f} %<extra></extra>",
      },
      {
        type: "scatter", mode: "markers", showlegend: false, hoverinfo: "text", x: reached.map(([p]) => p.speed_rpm),
        y: reached.map(([, k]) => r.torque_fractions[k % nt]), text: reached.map(([p]) => pointLabel(p)),
        marker: { color: "#ededed", size: 7 },
      },
    ]
    const bars = splitBars(r)
    const labels = r.points.map(pointLabel)
    const barData = bars.series.map((s, i) => ({
      type: "bar", name: s.name, x: labels, y: s.values, text: s.hover, hoverinfo: s.hover ? "text+y+name" : "y+name",
      marker: { color: caseLine(i).color },
    }))
    const k = lossKeyNumbers(r)
    const rated = ratedPoint(r)
    return `<div class="chips" role="note">${lossChips(r.winding_temperature_c).map(chip).join("")}</div>
${kv([
  ["Best efficiency", k.best ? `${fmt(k.best.efficiency * 100, 3)} % at ${k.best.label}` : "—"],
  ["Total loss at the rated point", k.rated ? `${fmt(k.rated.totalW, 3)} W at ${k.rated.label}` : rated < 0 ? "— (no rated point reached)" : "—"],
  ...(r.angle_convergence_rel != null ? ([["Angle convergence", `${fmt(r.angle_convergence_rel * 100, 2)} %`]] as [string, string][]) : []),
])}
${r.notes.length ? `<ul class="muted">${r.notes.map((n) => `<li>${e(n)}</li>`).join("")}</ul>` : ""}
<h3>Operating points</h3>${table(head, rows)}
<div class="grid two"><div><h3>Efficiency over speed and torque level</h3>${plot(contour, { ...panel, xaxis: axis("Speed (rpm)"), yaxis: axis("Torque level (fraction of the envelope torque)") } as Partial<Layout>)}</div>
<div><h3>Loss split</h3>${plot(barData, { ...panel, barmode: "stack", xaxis: { ...axis(""), tickangle: -60 }, yaxis: axis("Loss (W)"), legend: { orientation: "h", y: -0.5 } } as Partial<Layout>)}</div></div>`
  }
  const losses = section("losses", "Losses", lossesBody)

  // validation
  const validationBody = (() => {
    if (!validation) return notRun("press Validate (needs the full preset)", caseOut.preset && caseOut.preset !== "full" ? `preset is ${caseOut.preset}` : "no validation stored")
    const { budget } = validation
    const wnd = ev?.winding
    const k = wnd ? turnsScale(wnd, validation.reference_turns) : 1
    const v2 = atScale(budget.values_2d, k)
    const vv = atScale(budget.values, k)
    const KEYS: Record<string, { label: string; unit?: Unit }> = {
      la: { label: "La", unit: "mH" }, lu: { label: "Lu", unit: "mH" }, peak_torque: { label: "Peak torque", unit: "Nm" }, psi_max: { label: "ψ max", unit: "mWb" },
    }
    const keys = Object.keys(budget.values)
    const head = (key: string) => `${KEYS[key]?.label ?? key}${KEYS[key]?.unit ? ` (${UNIT_LABEL[KEYS[key].unit!]})` : ""}`
    const val = (key: string, x: number | null | undefined) => (KEYS[key]?.unit ? fmtSI(x, KEYS[key].unit!, 4) : fmt(x, 4))
    const pct = (x: number | null | undefined) => (x == null ? "—" : `${fmt(fromSI(x, "%"), 2)} %`)
    const grades = Object.entries(validation.material_grades).map(([m, g]) => `${m} ${g}`).join(", ")
    const basis = wnd
      ? `Key numbers at the case's winding (${wnd.turns} turns per pole${wnd.paths > 1 ? `, ${wnd.paths} paths` : ""}).`
      : `Key numbers at the ${validation.reference_turns}-turn reference winding.`
    return `<p>${e(validation.label ? VERIFIED_LABEL : "Not validated")}, srmcore ${e(validation.engine_version)}</p>
${grades ? `<p class="muted">B-H grades: ${e(grades)}</p>` : ""}
<h3>Checks</h3>${table(["Check", "Status", "Value", "Limit", "Detail"], validation.checks.map((c) => [c.name, c.status.toUpperCase(), fmt(c.value, 3), fmt(c.limit, 3), c.detail]), false)}
<h3>Uncertainty budget</h3><p class="muted">${e(basis)} Worst-case relative error of each key number, against the end-winding-corrected value.</p>
${table(
  ["Source", ...keys.map(head)],
  [
    ["2D map value", ...keys.map((x) => val(x, v2[x]))],
    ["With end winding", ...keys.map((x) => val(x, vv[x]))],
    ...budget.rows.map((r) => [`${r.source} (${r.note})`, ...keys.map((x) => pct(r.rel[x]))]),
    ["Total", ...keys.map((x) => pct(budget.total[x]))],
  ],
)}`
  })()
  const validationSection = section("validation", "Validation", validationBody)

  // before / after
  const cmp = data.compare
  const beforeAfter = cmp
    ? section(
        "before-after",
        "Before and after",
        !cmp.ok
          ? unavailable(cmp.reason)
          : !cmp.value.parent_evaluated
            ? '<div class="not-run">Parent not evaluated</div>'
            : table(
                ["Quantity", "Before", "After", "Change", "Change %"],
                compareRows(cmp.value.rows).map((r) => [
                  r.unit ? `${r.name} (${r.unit})` : r.name,
                  fmt(r.before),
                  fmt(r.after),
                  fmt(r.delta),
                  r.deltaPct == null ? "–" : `${r.deltaPct > 0 ? "+" : ""}${fmt(r.deltaPct, 2)} %`,
                ]),
              ),
      )
    : ""

  // animation
  let framesJson = ""
  const animBody = (() => {
    const a = data.animation
    if (!a.ok) return notRun("press Animate stroke on the Field tab", a.reason)
    const fr = a.value.frames
    if (fr.length === 0) return unavailable("the animation has no frames")
    framesJson = `<script type="application/json" id="frames">${jsonScript({ frames: fr, currentA: a.value.currentA, bMax: a.value.bMax })}</script>`
    const f0 = fr[0]
    const probe = a.value.probes.length ? line(a.value.probes, "Electrical angle (°, from unaligned)", "|B| (T)", undefined, true) : ""
    return `<div class="anim"><img id="anim-frame" src="${e(f0.src)}" alt="Flux density in the machine at the selected rotor angle">
<div class="controls"><button type="button" id="anim-play">Play</button>
<label>Speed <select id="anim-speed">${SPEEDS.map((s) => `<option value="${s}"${s === 1 ? " selected" : ""}>${s}×</option>`).join("")}</select></label>
<input type="range" id="anim-scrub" min="0" max="${fr.length - 1}" value="0" step="1" aria-label="Frame"></div>
<p id="anim-readout">Frame 1 of ${fr.length} at ${e(f0.currentA.toFixed(1))} A</p>
<p id="anim-values" class="mono muted">ψ ${e((f0.psi * 1e3).toFixed(2))} mWb, torque ${e(f0.torque.toFixed(2))} N·m</p>
<p class="muted">Phase A at ${e(a.value.currentA.toFixed(1))} A, rotor from unaligned to aligned; colour is |B| (inferno), full scale ${e(a.value.bMax.toFixed(2))} T.</p></div>${probe}`
  })()
  const animation = section("animation", "Flux animation", animBody)

  const sections = [header, findings, inputsSection, outline, keyNumbers, mapSection, performance, losses, validationSection, beforeAfter, animation]
  // The figures JSON is built last: every section above registers its plots while it is rendered.
  const figuresJson = jsonScript(figures)
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${e(`Run report — ${caseOut.label ?? caseOut.id}`)}</title>
<style>${CSS}</style></head>
<body><main>
${sections.join("\n")}
</main>
<script>${scriptSafe(plotlySource)}</script>
<script type="application/json" id="figures">${figuresJson}</script>
${framesJson}
<script>${scriptSafe(PLAYER_SOURCE)}</script>
</body></html>
`
}
