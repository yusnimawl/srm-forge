import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { useCreateCase, usePatchCase } from "@/api/cases"
import { api } from "@/api/client"
import type { Case, CaseInputs } from "@/api/types"
import { Banner } from "@/components/Banner"
import { MotorDiagram } from "@/components/candidate/MotorDiagram"
import { CaseActions } from "@/components/case/CaseActions"
import { InputTabs } from "@/components/case/InputTabs"
import { ValidationPanel } from "@/components/case/ValidationPanel"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { issueKey, tabOfKey, toForm, toInputs, useDebounced, validationByField, type CaseForm, type IssuesResponse } from "@/lib/caseForm"
import { caseStatus } from "@/lib/cases"
import { errorMessage } from "@/lib/errorMessage"
import { cn } from "@/lib/utils"

const AnalysisTabs = lazy(() => import("@/components/analysis/AnalysisTabs"))

type View = "input" | "diagram" | "results"
const VIEWS: [View, string][] = [["input", "Input"], ["diagram", "Diagram"], ["results", "Results"]]

export function CasePage() {
  const { caseId = "" } = useParams()
  const c = useQuery({ queryKey: ["case", caseId], queryFn: () => api<Case>(`/api/cases/${caseId}`) })
  if (c.isError) return <p className="text-destructive">Could not load the case: {errorMessage(c.error)}</p>
  if (!c.data) return <p className="text-muted-foreground" aria-busy="true">Loading the case…</p>
  return <CaseEditor key={c.data.id} data={c.data} />
}

function CaseEditor({ data }: { data: Case }) {
  const navigate = useNavigate()
  const patch = usePatchCase()
  const create = useCreateCase()
  const editable = data.stale
  const [view, setView] = useState<View>("input")

  // The form starts from the stored inputs and is not reset by later refetches; an evaluated case shows the stored ones.
  const stored = useMemo(() => toForm(data.inputs), [data.inputs])
  const [draft, setDraft] = useState<CaseForm>(stored)
  const form = editable ? draft : stored
  const update = (fn: (f: CaseForm) => CaseForm) => setDraft(fn)
  const now = useMemo(() => JSON.stringify(toInputs(form)), [form])
  const text = useDebounced(now)

  const check = useQuery({
    queryKey: ["validate", text],
    queryFn: () => api<IssuesResponse>("/api/validate", { method: "POST", body: `{"inputs":${text}}` }),
    enabled: editable,
    placeholderData: keepPreviousData,
  })
  const issues = editable ? check.data : undefined
  const errors = useMemo(() => validationByField(issues ?? { errors: [] }), [issues])
  const unplaced = (issues?.errors ?? []).filter((e) => tabOfKey(issueKey(e.loc)) === null)

  // Every edit is saved, valid or not. `flush` saves the newest inputs now and resolves true once the stored inputs
  // are the newest ones, false when the save failed (already toasted; the inputs are retried) or the form changed while
  // saving; saves run one after another.
  const latest = useRef(now)
  latest.current = now
  const saved = useRef(now)
  const [savedText, setSavedText] = useState(now)
  const queue = useRef(Promise.resolve(true))
  const flush = (): Promise<boolean> => {
    if (!editable) return Promise.resolve(true)
    queue.current = queue.current.then(async () => {
      const body = latest.current
      if (body !== saved.current) {
        const before = saved.current
        saved.current = body
        try {
          await patch.mutateAsync({ id: data.id, patch: { inputs: JSON.parse(body) } })
          setSavedText(body)
        } catch {
          saved.current = before
          return false
        }
      }
      return latest.current === saved.current
    })
    return queue.current
  }
  const flushRef = useRef(flush)
  flushRef.current = flush
  useEffect(() => {
    void flushRef.current()
  }, [text])
  useEffect(() => () => void flushRef.current(), [])

  // Evaluate needs a draft with no errors, checked against the text now in the form. While a job runs the inputs are locked.
  const ready = editable && text === now && check.data !== undefined && !check.isPlaceholderData && !check.isError &&
    check.data.errors.length === 0
  const running = data.jobs.some((j) => j.active)

  // The diagram keeps the last machine that passed validation; only errors under "design" hold it back.
  const machine = useMemo(() => JSON.parse(text).design?.machine as object | undefined, [text])
  const valid = !editable || (check.data !== undefined && !check.isPlaceholderData &&
    !check.data.errors.some((e) => issueKey(e.loc).startsWith("design.")))
  const [good, setGood] = useState<object | null>(null)
  useEffect(() => {
    if (machine && valid) setGood(machine)
  }, [machine, valid])

  const edit = () =>
    create.mutate(
      { origin: "edit", parent_case_id: data.id, inputs: data.inputs as CaseInputs },
      { onSuccess: (made) => navigate(`/cases/${made.id}`), onError: (e) => toast.error(errorMessage(e)) },
    )

  const status = caseStatus(data)
  const evaluation = editable ? null : data.evaluation
  const pane = (v: View, extra = "") => cn(view === v ? "block" : "hidden", "md:block", extra)

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold text-primary">{data.label || data.id}</h1>
          <Badge variant="outline">{data.origin}</Badge>
          <Badge variant={status === "Failed" ? "destructive" : status === "Draft" ? "secondary" : "default"}>{status}</Badge>
          {!editable && (
            <Button className="ml-auto min-h-11" onClick={edit} disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Edit"}
            </Button>
          )}
        </div>
        <Banner engineVersion={data.validation?.label ? data.validation.engine_version : null} />
        <CaseActions data={data} editable={editable} ready={ready} savedText={savedText} flush={flush} />
        {!editable && <p className="text-sm text-muted-foreground">Evaluated cases are read-only. Edit makes a new draft.</p>}
      </header>

      <div role="radiogroup" aria-label="Page section" className="inline-flex rounded-lg border p-0.5 md:hidden">
        {VIEWS.map(([v, label]) => (
          <button key={v} type="button" role="radio" aria-checked={view === v} onClick={() => setView(v)}
            className={cn("min-h-11 rounded-md px-4 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
              view === v ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-2 md:items-start">
        <section aria-label="Inputs" className={cn("min-w-0 space-y-3", pane("input"))}>
          {check.isError && (
            <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              Validation unavailable: {errorMessage(check.error)}
            </p>
          )}
          {unplaced.length > 0 && (
            <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              <p className="font-medium">Check the inputs:</p>
              <ul className="list-disc pl-5">
                {unplaced.map((e, k) => <li key={k}>{e.loc.length > 0 ? `${issueKey(e.loc)}: ` : ""}{e.msg}</li>)}
              </ul>
            </div>
          )}
          {(issues?.warnings.length ?? 0) > 0 && (
            <ul className="list-disc rounded-lg border p-3 pl-8 text-sm text-muted-foreground">
              {issues?.warnings.map((w, k) => <li key={k}>{w.loc.length > 0 ? `${issueKey(w.loc)}: ` : ""}{w.msg}</li>)}
            </ul>
          )}
          <InputTabs form={form} update={update} errors={errors} readOnly={!editable || running} evaluation={evaluation} />
        </section>
        <div className="min-w-0 space-y-6">
          <section aria-label="Motor diagram" className={pane("diagram")}>
            {good ? <MotorDiagram machine={good} /> : <p className="text-sm text-muted-foreground">The diagram appears once the dimensions are valid.</p>}
            {editable && good && !valid && <p className="text-xs text-muted-foreground">Showing the last valid dimensions.</p>}
          </section>
          <section aria-label="Results" className={pane("results", "min-w-0")}>
            {evaluation ? (
              evaluation.status === "ok" ? (
                <div className="space-y-6">
                  <Suspense fallback={<p className="text-sm text-muted-foreground">Loading charts…</p>}>
                    <AnalysisTabs evaluation={evaluation} label={data.label || data.id} />
                  </Suspense>
                  {data.validation && <ValidationPanel validation={data.validation} />}
                </div>
              ) : (
                <p className="text-sm text-destructive">{evaluation.error || "The evaluation failed."}</p>
              )
            ) : (
              <p className="text-sm text-muted-foreground">
                {editable ? "Evaluate this draft to see its results." : "This case has no evaluation."}
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
