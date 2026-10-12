import { lazy, Suspense, type ReactNode } from "react"
import { Link, useNavigate, useParams } from "react-router"
import { toast } from "sonner"
import { useCreateCase } from "@/api/cases"
import { useRunResult } from "@/api/useRunResult"
import { MotorDiagram } from "@/components/candidate/MotorDiagram"
import { WindingScan } from "@/components/candidate/WindingScan"
import { StatusChips } from "@/components/StatusChips"
import { Button } from "@/components/ui/button"
import { errorMessage } from "@/lib/errorMessage"
import { fmt, fmtSI } from "@/lib/format"
import { UNIT_LABEL } from "@/lib/units"
import { cn } from "@/lib/utils"

const AnalysisTabs = lazy(() => import("@/components/analysis/AnalysisTabs"))
const fallback = <div className="h-[380px]" aria-busy="true" />

function Item({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="border-b border-r border-border px-4 py-3.5">
      <div className="num text-xl font-medium tracking-[-0.02em]">
        {value}
        {unit && <span className="ml-[3px] text-xs font-normal text-muted-foreground">{unit}</span>}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

/** The items sit in a bordered strip; the cells' right and bottom hairlines are the dividers, clipped at the edge. */
function Strip({ children, ...rest }: { children: ReactNode } & React.HTMLAttributes<HTMLElement>) {
  return (
    <section {...rest} className={cn("overflow-hidden rounded-[10px] border border-border bg-card", rest.className)}>
      <div className="-mb-px -mr-px grid grid-cols-2 md:grid-cols-4">{children}</div>
    </section>
  )
}

export function CandidatePage() {
  const { jobId = "", candidateId = "" } = useParams()
  const result = useRunResult(jobId)
  const navigate = useNavigate()
  const create = useCreateCase()
  const back = (
    <Link to={`/runs/${jobId}`} className="inline-flex min-h-11 items-center text-[12.5px] text-faint hover:text-muted-foreground">
      Back to the run
    </Link>
  )
  const ev = result.data?.evaluations.find((e) => e.id === candidateId)
  if (!ev) {
    return (
      <div className="space-y-4">
        {back}
        <p>{result.isPending
            ? "Loading…"
            : result.isError
              ? "Could not load the result."
              : result.data === null
                ? "No result for this run."
                : "Candidate not found."}</p>
      </div>
    )
  }
  const w = ev.winding
  const k = ev.key
  const wire = w?.wire != null ? result.data?.requirements.wires[w.wire]?.kind : null
  return (
    <div className="space-y-6">
      {back}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-foreground">Candidate</h1>
        <span className="num text-sm text-muted-foreground">{ev.id}</span>
        <span className="text-sm text-muted-foreground">
          {ev.design.machine.n_stator_poles}/{ev.design.machine.n_rotor_poles} · {ev.status}
        </span>
        <Button className="ml-auto min-h-11" disabled={ev.status !== "ok" || create.isPending}
          onClick={() =>
            create.mutate(
              { origin: "candidate", job_id: jobId, candidate_id: ev.id },
              { onSuccess: (made) => navigate(`/cases/${made.id}`), onError: (e) => toast.error(errorMessage(e)) },
            )
          }>
          {create.isPending ? "Opening…" : "Open as case"}
        </Button>
      </div>
      <StatusChips evaluation={ev} />
      {ev.error &&
        (ev.status === "ok" ? (
          <p className="text-sm text-muted-foreground">Notes: {ev.error}</p>
        ) : (
          <p className="text-sm text-destructive">{ev.error}</p>
        ))}
      {k && (
        <Strip aria-label="Key numbers">
          <Item label="La" value={fmtSI(k.la, "mH")} unit="mH" />
          <Item label="Lu" value={fmtSI(k.lu, "mH")} unit="mH" />
          <Item label="La/Lu" value={fmt(k.la_lu)} />
          <Item label="Peak torque" value={fmt(k.peak_torque)} unit="N·m" />
          <Item label="ψ max" value={fmtSI(k.psi_max, "mWb")} unit="mWb" />
          <Item label="I max" value={fmt(k.i_max)} unit="A" />
        </Strip>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-2">
          <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Cross-section</h2>
          <MotorDiagram machine={ev.design.machine} />
        </section>
        {w && (
          <section className="space-y-2">
            <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Winding</h2>
            <Strip>
              <Item label="Turns per pole" value={fmt(w.turns)} />
              <Item label="Strands" value={fmt(w.strands)} />
              <Item label="Parallel paths" value={fmt(w.paths)} />
              <Item label="Wire" value={wire ?? "density mode"} />
              <Item label="Resistance" value={fmtSI(w.resistance, "mOhm")} unit={UNIT_LABEL.mOhm} />
              <Item label="J rms" value={fmtSI(ev.j_rms, "A/mm2")} unit={UNIT_LABEL["A/mm2"]} />
              <Item label="I rms" value={fmt(ev.i_rms_a)} unit="A" />
            </Strip>
          </section>
        )}
      </div>
      {(ev.map || ev.envelope) && (
        <section className="space-y-2">
          <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Analysis</h2>
          <Suspense fallback={fallback}>
            <AnalysisTabs evaluation={ev} />
          </Suspense>
        </section>
      )}
      {ev.scan.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">Winding scan</h2>
          <WindingScan scan={ev.scan} chosen={ev.winding} />
        </section>
      )}
    </div>
  )
}
