import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { requestMessage } from "@/api/cases"
import { api } from "@/api/client"
import type { Compare } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { compareRows } from "@/lib/compare"
import { fmt } from "@/lib/format"

export const COMPARE_POLL_MS = 5000

/** Key numbers of the parent case beside those of this (imported) case. An unevaluated parent gets an Evaluate button. */
export function BeforeAfterTable({ caseId, evaluated }: { caseId: string; evaluated: boolean }) {
  const qc = useQueryClient()
  const cmp = useQuery({
    queryKey: ["compare", caseId, evaluated],
    queryFn: () => api<Compare>(`/api/cases/${caseId}/compare`),
    retry: false,
    // The parent's evaluation runs as a job of its own; poll until it has finished.
    refetchInterval: (q) => (q.state.data && !q.state.data.parent_evaluated ? COMPARE_POLL_MS : false),
  })
  const evaluate = useMutation({
    mutationFn: (id: string) => api(`/api/cases/${id}/evaluate`, { method: "POST" }),
    onSuccess: () => {
      toast.message("Parent evaluation started")
      qc.invalidateQueries({ queryKey: ["cases"] })
      qc.invalidateQueries({ queryKey: ["compare", caseId] })
    },
    onError: (e) => toast.error(requestMessage(e)),
  })
  if (!cmp.data) return null
  const { parent_id, parent_evaluated, rows } = cmp.data
  if (!parent_evaluated)
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-[10px] border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">Parent not evaluated</p>
        {parent_id && (
          <Button variant="outline" className="min-h-11" disabled={evaluate.isPending} onClick={() => evaluate.mutate(parent_id)}>
            Evaluate parent
          </Button>
        )}
      </div>
    )
  const pct = (v: number | null) => (v == null ? "–" : `${v > 0 ? "+" : ""}${fmt(v, 2)} %`)
  return (
    <section aria-label="Before and after" className="space-y-2">
      <h2 className="text-sm font-medium">Parent (before) and imported geometry (after)</h2>
      <div className="overflow-x-auto rounded-[10px] border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Quantity</TableHead>
              <TableHead className="text-right">Before</TableHead>
              <TableHead className="text-right">After</TableHead>
              <TableHead className="text-right">Change</TableHead>
              <TableHead className="text-right">Change %</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {compareRows(rows).map((r) => (
              <TableRow key={r.name}>
                <TableCell>{r.name}{r.unit && <span className="text-muted-foreground"> ({r.unit})</span>}</TableCell>
                <TableCell className="num text-right">{fmt(r.before)}</TableCell>
                <TableCell className="num text-right">{fmt(r.after)}</TableCell>
                <TableCell className="num text-right">{fmt(r.delta)}</TableCell>
                <TableCell className="num text-right">{pct(r.deltaPct)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}
