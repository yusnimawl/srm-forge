import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router"
import { toast } from "sonner"
import { api, type JobOut } from "@/api/client"
import { errorMessage } from "@/lib/errorMessage"

export type JobAction = "open" | "cancel" | "resume" | "delete"

/** The buttons a job offers, in display order. */
export function actionsFor(job: Pick<JobOut, "active" | "resumable">): JobAction[] {
  if (job.active) return ["open", "cancel"]
  return job.resumable ? ["open", "resume", "delete"] : ["open", "delete"]
}

/** Cancel, resume and delete a job; each toasts its error and refreshes the job, result and case queries. */
export function useJobActions() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const refresh = (id: string) =>
    Promise.all(
      [["jobs"], ["job", id], ["result", id], ["cases"]].map((queryKey) => qc.invalidateQueries({ queryKey })),
    )
  const onError = (e: unknown) => toast.error(errorMessage(e))

  const cancel = useMutation({
    onError,
    mutationFn: (id: string) => api(`/api/jobs/${id}/cancel`, { method: "POST" }),
    onSuccess: (_, id) => refresh(id),
  })
  const resume = useMutation({
    onError,
    mutationFn: (id: string) => api<{ id: string }>(`/api/jobs/${id}/resume`, { method: "POST" }),
    onSuccess: ({ id: newId }, id) => {
      refresh(id)
      navigate(`/runs/${newId}`)
    },
  })
  const remove = useMutation({
    onError,
    mutationFn: (id: string) => api(`/api/jobs/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) => refresh(id),
  })

  return {
    cancel: cancel.mutate,
    resume: resume.mutate,
    remove: remove.mutate,
    busy: cancel.isPending || resume.isPending || remove.isPending,
  }
}
