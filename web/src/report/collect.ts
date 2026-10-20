import { api, ApiError } from "@/api/client"
import { binary, fetchFrames } from "@/api/field"
import type { Case } from "@/api/types"
import type { Geometry } from "@/components/candidate/MotorDiagram"
import { errorMessage } from "@/lib/errorMessage"
import { bMaxOfFrames } from "@/lib/fieldGl"
import { meshFromWire, type FieldFrameData, type FieldMeshData } from "@/lib/fieldWire"
import type { LossesResult } from "@/lib/losses"
import { probeSeries } from "@/lib/playback"
import type { CompareOut, Part, Report, ReportAnimation, ReportData } from "./types"

type RenderFrames = (mesh: FieldMeshData, frames: FieldFrameData[], bMax: number, onFrame: (k: number, n: number) => void) => Promise<string[]>

async function part<T>(run: () => Promise<T>, reasonOf: (e: unknown) => string = errorMessage): Promise<Part<T>> {
  try {
    return { ok: true, value: await run() }
  } catch (e) {
    return { ok: false, reason: reasonOf(e) }
  }
}

// Coil fills are mid-tones that read on both themes.
const PHASE_FILL: Record<string, string> = { A: "#c0392b", B: "#d68910", C: "#2e8b57", D: "#8e44ad" }

const attr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;")

/** The cross-section as a static SVG: iron, shaft, coil sides by phase. Iron and shaft use the report's theme tokens (`--iron`, `--iron-edge`), which `:root` defines for screen and print alike; the fallbacks only apply outside the report. */
function outlineSvg(g: Geometry): string {
  const iron = 'fill="var(--iron,#bdbdbd)" stroke="var(--iron-edge,#555)" stroke-width="0.2"'
  const coils = g.coils
    .map((c) => `<path d="${attr(c.d)}" fill="${PHASE_FILL[c.phase] ?? "#777"}" fill-opacity="${c.sign === "+" ? 0.9 : 0.5}"/>`)
    .join("")
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${g.view_box.join(" ")}" role="img" aria-label="Motor cross-section">` +
    `<path d="${attr(g.stator)}" fill-rule="evenodd" ${iron}/><path d="${attr(g.rotor)}" fill-rule="evenodd" ${iron}/>` +
    `<path d="${attr(g.shaft)}" fill="var(--bg)" stroke="var(--iron-edge,#555)" stroke-width="0.2"/>${coils}</svg>`
  )
}

async function animationOf(
  caseId: string, jobId: string, onStep: (m: string) => void, renderFrames: RenderFrames,
): Promise<ReportAnimation> {
  onStep("Loading the field frames")
  const { frames } = await fetchFrames(jobId)
  const mesh = meshFromWire(await binary(`/api/cases/${caseId}/field/mesh`))
  const bMax = bMaxOfFrames(mesh, frames)
  const srcs = await renderFrames(mesh, frames, bMax, (k, n) => onStep(`Rendering frames ${k}/${n}`))
  return {
    frames: frames.map((f, i) => ({ src: srcs[i], angle: f.angle, currentA: f.currentA, psi: f.psi, torque: f.torque, status: f.status })),
    probes: probeSeries(frames, mesh.nRotorPoles),
    currentA: frames[0]?.currentA ?? 0,
    bMax,
  }
}

/** Fetches everything the report shows. The case and the findings are required; every other part becomes "unavailable" on failure. Starts no job. */
export async function collect(caseId: string, onStep: (msg: string) => void, renderFrames: RenderFrames): Promise<ReportData> {
  onStep("Collecting the results")
  const base = `/api/cases/${caseId}`
  const [caseOut, report] = await Promise.all([api<Case>(base), api<Report>(`${base}/report`)])
  const machine = (caseOut.inputs as { design?: { machine?: object } }).design?.machine
  const missing = report.findings.find((f) => f.id === "animation_missing")?.text
  const [outline, losses, compare, animation] = await Promise.all([
    part(async () => outlineSvg(await api<Geometry>("/api/geometry", { method: "POST", body: JSON.stringify(machine) }))),
    part(() => api<LossesResult>(`${base}/losses`), (e) => (e instanceof ApiError && e.status === 404 ? "not run" : errorMessage(e))),
    caseOut.origin === "dxf" && caseOut.parent_case_id ? part(() => api<CompareOut>(`${base}/compare`)) : Promise.resolve(null),
    report.animation_job_id
      ? part(() => animationOf(caseId, report.animation_job_id!, onStep, renderFrames))
      : Promise.resolve<Part<ReportAnimation>>({ ok: false, reason: missing ?? "no animation was run" }),
  ])
  return { caseOut, report, outline, losses, compare, animation }
}
