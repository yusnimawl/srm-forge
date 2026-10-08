import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import type { SearchResult } from "@/lib/candidates"

export const useRunResult = (jobId: string, enabled = true) =>
  useQuery({
    queryKey: ["result", jobId],
    queryFn: () => api<SearchResult>(`/api/jobs/${jobId}/result`),
    enabled,
  })
