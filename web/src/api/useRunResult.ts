import { useQuery } from "@tanstack/react-query"
import { api, ApiError } from "@/api/client"
import type { SearchResult } from "@/api/types"

/** A run that stopped before any design was evaluated has no stored result (404): that is `null`, not an error. */
export async function resultOrNull<T>(load: () => Promise<T>): Promise<T | null> {
  try {
    return await load()
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null
    throw e
  }
}

export const useRunResult = (jobId: string, enabled = true) =>
  useQuery({
    queryKey: ["result", jobId],
    queryFn: () => resultOrNull(() => api<SearchResult>(`/api/jobs/${jobId}/result`)),
    enabled,
  })
