import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { components } from "./schema"
import { api, ApiError } from "./client"
import type { LossesResult } from "@/lib/losses"

export type LossesEstimate = components["schemas"]["LossesEstimateOut"]
export type BWaveform = components["schemas"]["BWaveformOut"]

/** The stored losses of a case; null while it has none. */
export const useLosses = (caseId: string) =>
  useQuery({
    queryKey: ["losses", caseId],
    queryFn: async () => {
      try {
        return await api<LossesResult>(`/api/cases/${caseId}/losses`)
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null
        throw e
      }
    },
  })

export const useLossesEstimate = (caseId: string, enabled: boolean) =>
  useQuery({
    queryKey: ["losses-estimate", caseId],
    queryFn: () => api<LossesEstimate>(`/api/cases/${caseId}/losses/estimate`),
    enabled,
    retry: false,
  })

/** Starts the losses job with the default grid; resolves with the job id and refreshes the case (its job list). */
export const useRunLosses = (caseId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api<{ job_id: string }>(`/api/cases/${caseId}/losses`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", caseId] }),
  })
}

/** B(t) at the iron element nearest (x, y) metres for operating point `point`. */
export const useLossB = (caseId: string, point: number, at: { x: number; y: number } | null) =>
  useQuery({
    queryKey: ["losses-b", caseId, point, at?.x, at?.y],
    queryFn: () => api<BWaveform>(`/api/cases/${caseId}/losses/b?point=${point}&x=${at!.x}&y=${at!.y}`),
    enabled: at !== null,
    retry: false,
  })

/** A readable message for a failed losses request; a 422 lists the server's messages (it names the material). */
export function lossesMessage(e: unknown): string {
  if (e instanceof ApiError && Array.isArray(e.detail)) return e.detail.map((i) => i.msg).join("; ")
  return e instanceof ApiError && typeof e.detail === "string" ? e.detail : e instanceof Error ? e.message : "Request failed"
}
