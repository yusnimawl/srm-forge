import { useEffect, useState } from "react"
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { importIssues } from "@/api/cases"
import { api, apiBlob, type JobOut } from "@/api/client"
import type { Case, Estimate } from "@/api/types"
import { useJobActions } from "@/api/useJobActions"
import { useJobEvents } from "@/api/useJobEvents"
import { Bar, fmtElapsed, progressOf } from "@/components/run/RunProgress"
import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { issueKey } from "@/lib/caseForm"
import { errorMessage } from "@/lib/errorMessage"
import { download, mapCsv } from "@/lib/exports"

const stem = (c: Case) => (c.label || c.id).replace(/[^\w.-]+/g, "_").slice(0, 60)

/** "No new map — about a minute" or "1 new map, about 26 min". */
export function estimateText(e: Estimate): string {
  if (!e.new_map) return "No new map — about a minute"
  return e.seconds == null ? "1 new map" : `1 new map, about ${Math.max(1, Math.round(e.seconds / 60))} min`
}

/** The text of a rejected request: its listed issues, else the API's message. */
function rejection(e: unknown): string {
  const issues = importIssues(e)
  if (!issues || issues.errors.length === 0) return errorMessage(e)
  return issues.errors.map((i) => (i.loc.length > 0 ? `${issueKey(i.loc)}: ${i.msg}` : i.msg)).join("; ")
}

/** Live state of the case's running job: the map-points bar while evaluating, the message while validating. The page
 *  refetches the case when the job ends. */
function CaseJobProgress({ job, caseId }: { job: JobOut; caseId: string }) {
  const qc = useQueryClient()
  const actions = useJobActions()
  const { job: live } = useJobEvents(job.id)
  const cur = live ?? job
  const p = progressOf(cur)
  const ended = !cur.active
  useEffect(() => {
    if (!ended) return
    if (cur.error) toast.error(cur.error)
    qc.invalidateQueries({ queryKey: ["case", caseId] })
    qc.invalidateQueries({ queryKey: ["cases"] })
  }, [ended, cur.error, caseId, qc])
  const validating = job.kind === "validate"
  // An EM validation cannot be stopped once it runs; a queued one can.
  const cancellable = !(validating && cur.status === "running")
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="font-medium">{validating ? "EM validation" : "Evaluation"}: {cur.status}</p>
        {cancellable && (
          <Button variant="outline" className="ml-auto min-h-11" onClick={() => actions.cancel(job.id)} disabled={actions.busy}>
            Cancel
          </Button>
        )}
      </div>
      {!validating && <Bar label="Map points" done={p.points_done ?? 0} total={p.points_total ?? 0} />}
      <p aria-live="polite" className="text-sm text-muted-foreground">
        Elapsed <span className="num">{fmtElapsed(p.elapsed_s)}</span>
        {p.message ? ` · ${p.message}` : ""}
      </p>
    </div>
  )
}

type Props = {
  data: Case
  editable: boolean
  /** The draft has no validation errors and the check has caught up with the form text. */
  ready: boolean
  /** The inputs as last saved; the estimate is refetched when it changes. */
  savedText: string
  /** Saves the newest inputs; false when they are not stored. */
  flush: () => Promise<boolean>
}

/** Evaluate, EM Validate and the export menu of a case, and the progress of its running job. */
export function CaseActions({ data, editable, ready, savedText, flush }: Props) {
  const qc = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const job = data.jobs.find((j) => j.active)
  const evaluation = editable ? null : data.evaluation
  const refresh = () =>
    Promise.all([qc.invalidateQueries({ queryKey: ["case", data.id] }), qc.invalidateQueries({ queryKey: ["cases"] })])

  const estimate = useQuery({
    queryKey: ["estimate", data.id, savedText],
    queryFn: () => api<Estimate>(`/api/cases/${data.id}/estimate`),
    enabled: editable && ready && !job,
    retry: false,
    placeholderData: keepPreviousData,
  })

  const evaluate = useMutation({
    mutationFn: async () => {
      if (!(await flush())) throw new Error("The latest inputs could not be saved, so the case was not evaluated.")
      return api<{ job_id: string }>(`/api/cases/${data.id}/evaluate`, { method: "POST" })
    },
    onSuccess: refresh,
    onError: (e) => toast.error(rejection(e)),
  })
  const validate = useMutation({
    mutationFn: () => api<{ job_id: string }>(`/api/cases/${data.id}/validate`, { method: "POST" }),
    onSuccess: refresh,
    onError: (e) => toast.error(rejection(e)),
  })

  const canValidate = !editable && data.preset === "full" && evaluation?.status === "ok" && !job && !validate.isPending
  const validateWhy = job
    ? "A job is running"
    : editable
      ? "Evaluate this case first"
      : data.preset !== "full"
        ? "EM validation needs a full map"
        : evaluation?.status !== "ok"
          ? "The evaluation failed"
          : undefined

  const exportSetup = async () => {
    try {
      if (!(await flush())) throw new Error("The latest inputs could not be saved.")
      const file = await api<unknown>(`/api/cases/${data.id}/setup`)
      download(`${stem(data)}.srm-setup.json`, JSON.stringify(file, null, 2))
    } catch (e) {
      toast.error(rejection(e))
    }
  }
  const exportMat = () =>
    apiBlob(`/api/cases/${data.id}/map.mat`).then(
      (b) => download(`${stem(data)}_map.mat`, b),
      (e) => toast.error(rejection(e)),
    )
  const map = evaluation?.map

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start gap-3">
        <div className="space-y-1">
          <span title={editable ? undefined : "Edit to create a new case"} className="inline-block">
            <Button className="min-h-11" onClick={() => evaluate.mutate()} aria-describedby="evaluate-estimate"
              disabled={!editable || !ready || !!job || evaluate.isPending}>
              {evaluate.isPending ? "Evaluating…" : "Evaluate"}
            </Button>
          </span>
          <p id="evaluate-estimate" className="text-xs text-muted-foreground">
            {!editable ? "Edit to create a new case" : estimate.data && ready && !job ? estimateText(estimate.data) : " "}
          </p>
        </div>
        <span title={validateWhy} className="inline-block">
          <Button variant="outline" className="min-h-11" disabled={!canValidate} onClick={() => setConfirming(true)}>
            EM Validate
          </Button>
        </span>
        <Popover>
          <PopoverTrigger render={<Button variant="outline" className="min-h-11" />}>Export</PopoverTrigger>
          <PopoverContent className="w-48 space-y-1">
            <Button variant="ghost" className="min-h-11 w-full justify-start" onClick={exportSetup}>Setup file</Button>
            <Button variant="ghost" className="min-h-11 w-full justify-start" disabled={!map}
              onClick={() => map && download(`${stem(data)}_map.csv`, mapCsv(map))}>Map (CSV)</Button>
            <Button variant="ghost" className="min-h-11 w-full justify-start" disabled={!map} onClick={exportMat}>Map (MAT)</Button>
          </PopoverContent>
        </Popover>
      </div>
      {job && <CaseJobProgress key={job.id} job={job} caseId={data.id} />}
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogTitle>Run EM validation?</DialogTitle>
          <DialogDescription>
            About 1 hour. It re-solves key points on finer meshes and cannot be cancelled once it starts.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose render={<Button variant="outline" className="min-h-11" />}>Not now</DialogClose>
            <Button className="min-h-11" onClick={() => { setConfirming(false); validate.mutate() }}>Start validation</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
