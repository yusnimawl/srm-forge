import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import type { components } from "./schema"
import { api, ApiError, type ValidationIssue } from "./client"
import type { Case, CaseSummary } from "./types"
import { issueKey } from "@/lib/caseForm"
import { errorMessage } from "@/lib/errorMessage"
import { toast } from "sonner"

export type CasePatch = components["schemas"]["CasePatch"]
export type CaseCreate =
  | components["schemas"]["CandidateCase"]
  | components["schemas"]["ReferenceCase"]
  | components["schemas"]["ImportCase"]
  | components["schemas"]["EditCase"]
export type SetupFile = components["schemas"]["SetupFile"]

const CASES = ["cases"] as const

export const useCaseList = () => useQuery({ queryKey: CASES, queryFn: () => api<CaseSummary[]>("/api/cases") })

/** Full cases (with their evaluations) for the given ids. */
export const useCaseDetails = (ids: string[]) =>
  useQueries({ queries: ids.map((id) => ({ queryKey: ["case", id], queryFn: () => api<Case>(`/api/cases/${id}`) })) })

/** Edits one case in the list at once and rolls back when the request fails. */
export function usePatchCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: CasePatch }) =>
      api<Case>(`/api/cases/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: CASES })
      const before = qc.getQueryData<CaseSummary[]>(CASES)
      qc.setQueryData<CaseSummary[]>(CASES, (list) =>
        list?.map((c) =>
          c.id !== id
            ? c
            : {
                ...c,
                ...(patch.label != null && { label: patch.label }),
                ...(patch.flag != null && { flag: patch.flag || null }),
                ...(patch.comment != null && { comment: patch.comment }),
                ...(patch.show_in_graphs != null && { show_in_graphs: patch.show_in_graphs }),
              },
        ),
      )
      return { before }
    },
    onError: (e, _v, ctx) => {
      qc.setQueryData(CASES, ctx?.before)
      toast.error(errorMessage(e))
    },
    onSettled: (_d, _e, { id }) => {
      qc.invalidateQueries({ queryKey: CASES })
      qc.invalidateQueries({ queryKey: ["case", id] })
    },
  })
}

export function useDeleteCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api<void>(`/api/cases/${id}`, { method: "DELETE" }),
    onError: (e) => toast.error(errorMessage(e)),
    onSettled: () => qc.invalidateQueries({ queryKey: CASES }),
  })
}

export function useCreateCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CaseCreate) => api<Case>("/api/cases", { method: "POST", body: JSON.stringify(body) }),
    onSettled: () => qc.invalidateQueries({ queryKey: CASES }),
  })
}

/** The issues a rejected case import lists: `{errors, warnings}` from the import check, or FastAPI's own `detail` list. */
export function importIssues(e: unknown): { errors: ValidationIssue[]; warnings: ValidationIssue[] } | null {
  if (!(e instanceof ApiError) || e.status !== 422) return null
  const body = e.body as { errors?: ValidationIssue[]; warnings?: ValidationIssue[] } | null
  if (body?.errors) return { errors: body.errors, warnings: body.warnings ?? [] }
  return Array.isArray(e.detail) ? { errors: e.detail, warnings: [] } : null
}

/** Issues as one line: "field: message" joined by "; " (the request's "body" prefix and union tags are dropped). */
export function formatIssues(items: ValidationIssue[]): string {
  return items
    .map((i) => {
      const key = issueKey(i.loc.filter((p) => p !== "body"))
      return key ? `${key}: ${i.msg}` : i.msg
    })
    .join("; ")
}

/** The text of a failed request: its listed errors when it was rejected as invalid, else the API's message. */
export function requestMessage(e: unknown): string {
  const issues = importIssues(e)
  return issues && issues.errors.length > 0 ? formatIssues(issues.errors) : errorMessage(e)
}

/** Reads a setup file and has the server check and normalize it (absent sections come back null). */
export async function checkSetupFile(file: File): Promise<SetupFile> {
  let json: unknown
  try {
    json = JSON.parse(await file.text())
  } catch {
    throw new Error(`${file.name} is not a JSON file`)
  }
  return api<SetupFile>("/api/setup/check", { method: "POST", body: JSON.stringify(json) })
}
