import { SrmSpinner } from "@/components/brand/SrmSpinner"
import { lazy, Suspense, useState } from "react"
import { useCaseDetails, useCaseList, useDeleteCase, usePatchCase } from "@/api/cases"
import { CaseTable } from "@/components/cases/CaseTable"
import { NewCaseMenu } from "@/components/cases/NewCaseMenu"
import type { Overlay } from "@/lib/analysis"
import { canShowMore, filterByFlag, toCaseRows, type CaseRow } from "@/lib/cases"

const AnalysisTabs = lazy(() => import("@/components/analysis/AnalysisTabs"))

export function CasesPage() {
  const list = useCaseList()
  const patch = usePatchCase()
  const remove = useDeleteCase()
  const [flag, setFlag] = useState<string | null>(null)

  const rows = toCaseRows(list.data ?? [])
  const flags = [...new Set(rows.flatMap((r) => (r.flag ? [r.flag] : [])))].sort()
  const active = flag !== null && flags.includes(flag) ? flag : null
  const shown = rows.filter((r) => r.show_in_graphs)
  const details = useCaseDetails(shown.map((r) => r.id))
  const evaluated = shown.flatMap((r, k) => {
    const evaluation = details[k]?.data?.evaluation
    return evaluation?.envelope ? [{ label: r.label, evaluation }] : []
  })
  const [main, ...others] = evaluated
  const overlays: Overlay[] = others

  const confirmDelete = (r: CaseRow) => {
    if (window.confirm(`Delete case "${r.label}"? This cannot be undone.`)) remove.mutate(r.id)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-foreground">Cases</h1>
        <div className="flex flex-wrap items-center gap-2">
          {flags.length > 0 && (
            <select
              aria-label="Filter by flag"
              className="h-11 rounded-[6px] border border-border-strong bg-background px-2.5 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring md:text-[13px]"
              value={active ?? ""}
              onChange={(e) => setFlag(e.target.value || null)}
            >
              <option value="">All flags</option>
              {flags.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          )}
          <NewCaseMenu />
        </div>
      </div>
      {list.isError && <p className="text-destructive">Could not load the cases.</p>}
      {list.isSuccess && rows.length === 0 && (
        <div className="rounded-[10px] border border-border bg-card p-6 text-center text-muted-foreground">
          No cases yet — open a candidate as a case, or start from a reference
        </div>
      )}
      {shown.length > 0 && (
        <section aria-label="Performance of the shown cases" className="order-1 space-y-2 md:order-none">
          {main ? (
            <Suspense fallback={<SrmSpinner label="Loading charts…" showLabel />}>
              <AnalysisTabs performanceOnly evaluation={main.evaluation} label={main.label} overlays={overlays} />
            </Suspense>
          ) : (
            <p className="text-sm text-muted-foreground">
              {details.some((d) => d.isPending) ? "Loading the shown cases…" : "None of the shown cases has an envelope to plot: they are drafts or their evaluation failed."}
            </p>
          )}
          <p className="text-xs text-muted-foreground">Unvalidated, peak-only, except cases whose status reads 2D-verified.</p>
        </section>
      )}
      {rows.length > 0 && (
        <CaseTable
          rows={filterByFlag(rows, active)}
          actions={{ patch: (id, p) => patch.mutate({ id, patch: p }), remove: confirmDelete, canShowMore: canShowMore(rows) }}
        />
      )}
    </div>
  )
}
