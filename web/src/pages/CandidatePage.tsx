import { lazy, Suspense } from "react"
import { Link, useParams } from "react-router"
import { useRunResult } from "@/api/useRunResult"
import { Banner } from "@/components/Banner"
import { MotorDiagram } from "@/components/candidate/MotorDiagram"
import { WindingScan } from "@/components/candidate/WindingScan"
import { fmt, fmtSI } from "@/lib/format"

const MapCharts = lazy(() => import("@/components/candidate/MapCharts"))
const EnvelopeChart = lazy(() => import("@/components/candidate/EnvelopeChart"))
const fallback = <div className="h-[380px]" aria-busy="true" />

function Item({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="num text-lg">
        {value}
        {unit && <span className="ml-1 text-sm text-muted-foreground">{unit}</span>}
      </div>
    </div>
  )
}

export function CandidatePage() {
  const { jobId = "", candidateId = "" } = useParams()
  const result = useRunResult(jobId)
  const back = (
    <Link to={`/runs/${jobId}`} className="inline-flex min-h-11 items-center text-sm text-secondary">
      Back to the run
    </Link>
  )
  const ev = result.data?.evaluations.find((e) => e.id === candidateId)
  if (!ev) {
    return (
      <div className="space-y-4">
        {back}
        <p>{result.isPending ? "Loading…" : result.isError ? "Could not load the result." : "Candidate not found."}</p>
      </div>
    )
  }
  const w = ev.winding
  const k = ev.key
  const wire = w?.wire != null ? result.data?.requirements?.wires?.[w.wire]?.kind : null
  return (
    <div className="space-y-6">
      {back}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-primary">Candidate</h1>
        <span className="num text-sm text-muted-foreground">{ev.id}</span>
        <span className="text-sm">
          {ev.design.machine.n_stator_poles}/{ev.design.machine.n_rotor_poles} · {ev.status}
        </span>
      </div>
      <Banner />
      {ev.error && <p className="text-sm text-destructive">{ev.error}</p>}
      {k && (
        <section aria-label="Key numbers" className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Item label="La" value={fmtSI(k.la, "mH")} unit="mH" />
          <Item label="Lu" value={fmtSI(k.lu, "mH")} unit="mH" />
          <Item label="La/Lu" value={fmt(k.la_lu)} />
          <Item label="Peak torque" value={fmt(k.peak_torque)} unit="N·m" />
          <Item label="ψ max" value={fmtSI(k.psi_max, "mWb")} unit="mWb" />
          <Item label="I max" value={fmt(k.i_max)} unit="A" />
        </section>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Cross-section</h2>
          <MotorDiagram machine={ev.design.machine} />
        </section>
        {w && (
          <section className="space-y-2">
            <h2 className="text-lg font-semibold">Winding</h2>
            <div className="grid grid-cols-2 gap-3">
              <Item label="Turns per pole" value={fmt(w.turns)} />
              <Item label="Strands" value={fmt(w.strands)} />
              <Item label="Parallel paths" value={fmt(w.paths)} />
              <Item label="Wire" value={wire ?? "density mode"} />
              <Item label="Resistance" value={fmt(w.resistance == null ? null : w.resistance * 1000)} unit="mΩ" />
              <Item label="J rms" value={fmt(ev.j_rms == null ? null : ev.j_rms / 1e6)} unit="A/mm²" />
              <Item label="I rms" value={fmt(ev.i_rms_a)} unit="A" />
            </div>
          </section>
        )}
        {ev.map && (
          <Suspense fallback={fallback}>
            <MapCharts map={ev.map} unaligned={k?.unaligned_angle ?? null} />
          </Suspense>
        )}
        {ev.envelope && (
          <section className="space-y-2 lg:col-span-2">
            <h2 className="text-lg font-semibold">Torque and power vs speed</h2>
            <Suspense fallback={fallback}>
              <EnvelopeChart envelope={ev.envelope} />
            </Suspense>
          </section>
        )}
      </div>
      {ev.scan && ev.scan.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Winding scan</h2>
          <WindingScan scan={ev.scan} />
        </section>
      )}
    </div>
  )
}
