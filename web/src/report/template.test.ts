import { describe, expect, it } from "vitest"
import type { Case } from "@/api/types"
import type { LossesResult } from "@/lib/losses"
import { buildReport, escapeHtml, scriptSafe } from "./template"
import type { Finding, ReportData } from "./types"

const PLOTLY = "/*plotly*/ var x = '</script>';"
const arr = <T>(n: number, f: (k: number) => T) => Array.from({ length: n }, (_, k) => f(k))

const evaluation = {
  id: "e1", feasible: true, status: "ok", error: "", mass_kg: 5, torque_ratio: 1.1, power_ratio: 1.2,
  peak_power_w: 3000, power_density_kw_per_kg: 0.6, efficiency_base: 0.9, j_limit: 6e6, srmapp_version: "0.6.0",
  key: { la: 0.01, lu: 0.002, la_lu: 5, peak_torque: 3, psi_max: 0.05, i_max: 20, aligned_angle: 0, unaligned_angle: 0.5 },
  winding: { turns: 20, strands: 1, paths: 1, wire: 0.001, resistance: 0.1, copper_mass: 1, copper_area: 1e-6, current: 10 },
  map: {
    angles: arr(5, (k) => k * 0.1), currents: [0, 5, 10],
    psi: arr(5, (a) => [0, 0.01 + a * 0.001, 0.02]), torque: arr(5, () => [0, 1, 2]),
  },
  curves: {
    currents: [1, 2, 3], la_sat: [0.01, 0.01, 0.009], lu: [0.002, 0.002, 0.002], la_lu: [5, 5, 4.5], k2: [0.8, 0.8, 0.78],
    b_sp: [1, 1.5, 1.8], b_sp_k2: [0.8, 1.2, 1.4], inductance: [[0.01, 0.01, 0.01]], la_unsat: 0.011,
  },
  envelope: {
    speeds_rpm: [1000, 2000], torque: [3, 2], power: [300, 400], efficiency: [0.9, 0.85], i_rms: [5, 6],
    theta_on_el: [10, 20], theta_off_el: [150, 160], theta_on: [1, 2], theta_off: [3, 4], copper_loss: [1, 2],
    work_loop: [1, 1], work_torque: [1, 1], line_mean: [1, 2], line_rms: [2, 3], power_factor: [0.5, 0.6],
    waveforms: {
      theta: [0, 1, 2], theta_el: [0, 30, 60],
      current: [[0, 1, 0], [0, 1, 0]], psi: [[0, 0.01, 0], [0, 0.01, 0]], voltage: [[1, 1, 1], [1, 1, 1]],
      torque: [[0, 1, 0], [0, 1, 0]], line: [[1, 1, 1], [1, 1, 1]],
    },
  },
  scan: [], design: {},
}

const caseOut = (over: Record<string, unknown> = {}) =>
  ({
    id: "c1", label: "My case", comment: null, created: "2026-10-19", flag: null, origin: "search", poles: "8/6", preset: "full",
    parent_case_id: null, show_in_graphs: true, stale: false, jobs: [], validated: false, validation: null,
    evaluation,
    inputs: {
      requirements: { peak_power_w: 3000, peak_torque_nm: 3, base_speed_rpm: 1000, max_speed_rpm: 4000, bus_voltage_v: 400, wires: [] },
      design: { machine: { n_stator_poles: 8, n_rotor_poles: 6, n_phases: 4, stator_outer_diameter: 0.1, materials: { stator: "M19<b>", rotor: "M19", shaft: "steel_1010", coil: "copper" } } },
      winding: "auto", j_limit: 6e6,
    },
    ...over,
  }) as unknown as Case

const finding = (level: Finding["level"]): Finding => ({ id: level, level, topic: `topic-${level}`, text: `text-${level} 1.5`, unit: "", value: 1.5 })

const fixture = (over: Partial<ReportData> = {}): ReportData => ({
  caseOut: caseOut(),
  report: {
    findings: [finding("missing"), finding("ok"), finding("note"), finding("warn")],
    versions: { srmcore: "0.6.0", srmapp: "0.6.0", srmweb: "0.7.0" },
    generated: "2026-10-19T10:00:00Z", animation_job_id: null, animation_current_a: null,
  },
  outline: { ok: true, value: '<svg viewBox="0 0 10 10"><path d="M0 0L10 10"/></svg>' },
  losses: { ok: false, reason: "why-not" },
  compare: null,
  animation: { ok: false, reason: "why-not" },
  ...over,
})

const lossPoint = (speed: number, eff: number) => ({
  speed_rpm: speed, torque_nm: 2, reached: true, efficiency: eff, copper_dc_w: 10, copper_ac_w: 1,
  iron: { stator_pole: { hysteresis: 1, classical: 0.1, excess: 0.05 } }, iron_w: 1.2, beyond_fit_range: false,
  current_limit: null, iron_uncertainty_rel: 0.1, power_w: 500, stroke_key: "k", theta_off: null, theta_on: null,
})
const losses: LossesResult = {
  points: [lossPoint(1000, 0.8), lossPoint(2000, 0.85)], speeds_rpm: [1000, 2000], torque_fractions: [1], n_angles: 60,
  angle_convergence_rel: null, notes: ["a note"], srmapp_version: "0.6.0", winding_temperature_c: 120,
}

const section = (html: string, id: string) => {
  const m = new RegExp(`<section id="${id}"[\\s\\S]*?</section>`).exec(html)
  return m ? m[0] : ""
}

describe("buildReport", () => {
  it("has no network loads", () => {
    const html = buildReport(fixture({ losses: { ok: true, value: losses } }), PLOTLY)
    expect(html).not.toMatch(/(src|href)\s*=\s*["']?\s*(https?:)?\/\//i)
    expect(html).not.toMatch(/url\(\s*["']?(https?:)?\/\//i)
    expect(html).not.toContain("fetch(")
  })

  it("escapes user text and script terminators", () => {
    const evil = "<img src=x onerror=alert(1)></script>"
    const html = buildReport(fixture({ caseOut: caseOut({ label: evil, comment: evil }) }), PLOTLY)
    expect(html).toContain("&lt;img")
    expect(html).not.toContain("<img src=x")
    expect(html).toContain("<\\/script")
    expect(html.match(/<\/script>/gi)?.length).toBe(html.match(/<script/gi)?.length)
    expect(html).not.toContain("M19<b>")
  })

  it("has every section", () => {
    const ids = ["header", "findings", "inputs", "outline", "key-numbers", "map", "performance", "losses", "validation", "animation"]
    const html = buildReport(fixture(), PLOTLY)
    ids.forEach((id) => expect(html).toContain(`<section id="${id}"`))
    expect(html).not.toContain('id="before-after"')
    for (const id of ["losses", "validation", "animation"]) expect(section(html, id)).toContain("Not run")
    for (const id of ["losses", "animation"]) expect(section(html, id)).toContain("why-not")
    const cmp = { parent_id: "p", parent_evaluated: true, rows: [{ name: "Peak torque", unit: "N·m", before: 2, after: 3 }] }
    const withCmp = buildReport(fixture({ compare: { ok: true, value: cmp } }), PLOTLY)
    expect(section(withCmp, "before-after")).toContain("Peak torque")
    expect(section(withCmp, "before-after")).toContain("+50")
  })

  it("shows the reason of a failed optional part", () => {
    const html = buildReport(fixture({ outline: { ok: false, reason: "boom" } }), PLOTLY)
    expect(section(html, "outline")).toContain("Unavailable: boom")
    expect(section(html, "losses")).toContain("run Losses on the Losses tab")
    expect(section(html, "validation")).toContain("press Validate (needs the full preset)")
    expect(section(html, "animation")).toContain("press Animate stroke on the Field tab")
  })

  it("groups findings by level in order", () => {
    const f = section(buildReport(fixture(), PLOTLY), "findings")
    const at = ["warn", "note", "ok", "missing"].map((l) => f.indexOf(`text-${l} 1.5`))
    expect(at.every((k) => k >= 0)).toBe(true)
    expect([...at].sort((a, b) => a - b)).toEqual(at)
  })

  it("stamps versions and the chips in the header", () => {
    const h = section(buildReport(fixture(), PLOTLY), "header")
    expect(h).toContain("srmcore 0.6.0")
    expect(h).toContain("srmapp 0.6.0")
    expect(h).toContain("srmweb 0.7.0")
    expect(h).toContain("Unvalidated")
    expect(h).toContain("Peak only")
    const validation = { label: "2D-verified", engine_version: "0.4.0", checks: [], material_grades: {}, reference_turns: 20, budget: { rows: [], total: {}, values: {}, values_2d: {} } }
    const v = caseOut({ validation })
    expect(section(buildReport(fixture({ caseOut: v }), PLOTLY), "header")).toContain("2D-verified · srmcore 0.4.0")
  })

  it("tells an old evaluation to be re-evaluated before running losses", () => {
    const old = caseOut({ evaluation: { ...evaluation, srmapp_version: null } })
    expect(section(buildReport(fixture({ caseOut: old }), PLOTLY), "losses")).toContain("re-evaluate")
  })

  it("lists loss points and plots when losses exist", () => {
    const s = section(buildReport(fixture({ losses: { ok: true, value: losses } }), PLOTLY), "losses")
    expect(s).toContain("<td>1000</td>")
    expect(s).toContain("a note")
    expect(s).toContain('class="plot"')
  })

  it("renders the animation player", () => {
    const frame = (k: number) => ({ src: `data:image/png;base64,AA${k}`, angle: k, currentA: 10, psi: 0.01, torque: 1.5, status: "ok" })
    const html = buildReport(fixture({ animation: { ok: true, value: { frames: [frame(0), frame(1)], probes: [], currentA: 10, bMax: 2 } } }), PLOTLY)
    const s = section(html, "animation")
    expect(s).toContain('<img id="anim-frame" src="data:image/png;base64,AA0"')
    expect(s).toContain("Frame 1 of 2")
    expect(s).toContain('type="range"')
    expect(html).toContain('id="frames"')
    expect(html.indexOf("/*plotly*/")).toBeLessThan(html.indexOf('id="figures"'))
    expect(html.indexOf('id="figures"')).toBeLessThan(html.indexOf('id="frames"'))
  })

  it("shows a dash for null frame values", () => {
    const frame = { src: "data:image/png;base64,AA", angle: 0, currentA: 10, psi: null, torque: null, status: "ok" }
    const html = buildReport(fixture({ animation: { ok: true, value: { frames: [frame], probes: [], currentA: 10, bMax: 2 } } }), PLOTLY)
    expect(section(html, "animation")).toContain("ψ – mWb, torque – N·m")
  })

  it("has parseable figures that match plot divs", () => {
    const html = buildReport(fixture({ losses: { ok: true, value: losses } }), PLOTLY)
    const m = /<script type="application\/json" id="figures">([\s\S]*?)<\/script>/.exec(html)
    expect(m).not.toBeNull()
    const figs = JSON.parse(m![1]) as { id: string }[]
    expect(figs.length).toBeGreaterThan(5)
    figs.forEach((f) => expect(html).toContain(`<div class="plot" id="${f.id}">`))
  })
})

describe("print layout", () => {
  const html = buildReport(fixture({ losses: { ok: true, value: losses } }), PLOTLY)
  it("does not force a page break per section and keeps figures whole", () => {
    expect(html).not.toMatch(/break-before:\s*page/)
    expect(html).toMatch(/\.fig,tr\{break-inside:avoid\}/)
    expect(html).toMatch(/h2,h3\{break-after:avoid\}/)
  })
  it("puts every plot in a .fig wrapper, with its heading where it has one", () => {
    const plots = html.match(/class="plot" id=/g)?.length ?? 0
    expect(plots).toBeGreaterThan(5)
    const withPlot = html.split('<div class="fig">').slice(1).filter((f) => /^(?:(?!<div class="fig">)[\s\S])*?class="plot"/.test(f))
    expect(withPlot.length).toBe(plots)
    const map = html.slice(html.indexOf('<section id="map"'), html.indexOf('<section id="performance"'))
    map.split('<div class="fig">').slice(1).filter((f) => f.includes('class="plot"')).forEach((f) => expect(f.indexOf("<h3>")).toBeGreaterThanOrEqual(0))
  })
})

describe("json blocks", () => {
  it("survive <!-- and </script> in values and round-trip", () => {
    const evil = "a<!--b</script>c"
    const frame = { src: "data:image/png;base64,AA", angle: 0, currentA: 10, psi: 0.01, torque: 1, status: evil }
    const d = fixture({
      losses: { ok: true, value: { ...losses, notes: [evil] } },
      animation: { ok: true, value: { frames: [frame], probes: [{ type: "scatter", mode: "lines", name: evil, x: [0], y: [1], line: { color: "#ededed", dash: "solid", width: 2 }, connectgaps: false }], currentA: 10, bMax: 2 } },
    })
    const html = buildReport(d, PLOTLY)
    const block = (id: string) => new RegExp(`<script type="application/json" id="${id}">([\\s\\S]*?)</script>`).exec(html)![1]
    expect(JSON.parse(block("frames")).frames[0].status).toBe(evil)
    expect(JSON.stringify(JSON.parse(block("figures")))).toContain("a<!--b</script>c")
    expect(block("figures")).not.toContain("<")
  })
})

describe("escaping helpers", () => {
  it("escapes html", () => expect(escapeHtml(`<a href="x">&'`)).toBe("&lt;a href=&quot;x&quot;&gt;&amp;&#39;"))
  it("neutralises script terminators", () => {
    expect(scriptSafe("a</SCRIPT>b<!--c")).toBe("a<\\/SCRIPT>b<\\!--c")
  })
})
