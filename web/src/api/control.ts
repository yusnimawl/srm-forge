import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, ApiError } from "./client"
import type { components } from "./schema"
import { scopesFromWire, type Scenario } from "@/lib/control"

export type ControllerInfo = components["schemas"]["ControllerOut"]
export type TargetCheck = components["schemas"]["TargetCheckOut"]

export const useControllers = () =>
  useQuery({ queryKey: ["controllers"], queryFn: () => api<ControllerInfo[]>("/api/control/controllers"), staleTime: Infinity })

/** Starts a control run on an evaluated case; resolves with the job id. */
export const useRunControl = (caseId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { controller: string; scenario: Scenario }) =>
      api<{ job_id: string }>(`/api/cases/${caseId}/control`, { method: "POST", body: JSON.stringify(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", caseId] }),
  })
}

export const useTargetCheck = (caseId: string) =>
  useMutation({
    mutationFn: (controller: string) =>
      api<TargetCheck>("/api/control/target-check", { method: "POST", body: JSON.stringify({ controller, case_id: caseId }) }),
  })

/** The traces of a finished control job, decimated to about `nPx` points per channel. */
export const useControlScopes = (jobId: string | null, nPx: number) =>
  useQuery({
    queryKey: ["control-scopes", jobId, nPx],
    queryFn: async () => {
      const res = await fetch(`/api/jobs/${jobId}/control?n_px=${nPx}`, { credentials: "same-origin" })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new ApiError(res.status, body?.detail ?? res.statusText, body)
      }
      return scopesFromWire(await res.arrayBuffer())
    },
    enabled: jobId !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
