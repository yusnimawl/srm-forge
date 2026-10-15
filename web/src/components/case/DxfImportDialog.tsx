import { useRef, useState } from "react"
import { useNavigate } from "react-router"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { formatIssues, importIssues } from "@/api/cases"
import { api, type ValidationIssue } from "@/api/client"
import type { CaseSummary, DxfImport } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { MAX_SHOWN } from "@/lib/cases"
import { errorMessage } from "@/lib/errorMessage"

const post = (caseId: string, file: File) => {
  const body = new FormData()
  body.append("file", file)
  // `api` leaves Content-Type to the browser for a FormData body (it adds the multipart boundary).
  return api<DxfImport>(`/api/cases/${caseId}/dxf`, { method: "POST", body })
}

/** Shows the given cases in the graphs while there is room, skipping those already shown. Best effort: the import is
 *  already stored when this runs. */
export async function showInGraphs(ids: string[]) {
  try {
    const list = await api<CaseSummary[]>("/api/cases")
    const shown = new Set(list.filter((c) => c.show_in_graphs).map((c) => c.id))
    for (const id of ids) {
      if (shown.has(id)) continue
      if (shown.size >= MAX_SHOWN) break
      await api(`/api/cases/${id}`, { method: "PATCH", body: JSON.stringify({ show_in_graphs: true }) })
      shown.add(id)
    }
  } catch {
    // The graphs selection can be set from the case list.
  }
}

/** Picks a DXF file, imports it as a new case derived from `caseId`, and opens that case. A rejected file lists every
 *  problem and keeps the dialog open. */
export function DxfImportDialog({ caseId, open, onOpenChange }: { caseId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [issues, setIssues] = useState<ValidationIssue[]>([])

  const run = useMutation({
    mutationFn: async (f: File) => {
      const out = await post(caseId, f)
      await showInGraphs([caseId, out.case.id])
      return out
    },
    onSuccess: (out) => {
      for (const w of out.warnings) toast.message(String((w as { msg?: string }).msg ?? ""))
      qc.invalidateQueries({ queryKey: ["cases"] })
      qc.invalidateQueries({ queryKey: ["case", caseId] })
      onOpenChange(false)
      navigate(`/cases/${out.case.id}`)
    },
    onError: (e) => setIssues(importIssues(e)?.errors ?? [{ loc: [], msg: errorMessage(e) }]),
  })

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!run.isPending) onOpenChange(o) }}>
      <DialogContent>
        <DialogTitle>Import DXF</DialogTitle>
        <DialogDescription>
          The outline in the file becomes a new case with this case as its parent. Units are millimetres.
        </DialogDescription>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" className="min-h-11" onClick={() => input.current?.click()}>Choose file</Button>
          <span className="min-w-0 break-all text-sm text-muted-foreground">{file?.name ?? "No file chosen"}</span>
          <input ref={input} type="file" accept=".dxf" className="hidden" aria-label="DXF file"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setIssues([]) }} />
        </div>
        {issues.length > 0 && (
          <ul role="alert" className="list-disc rounded-[10px] border border-destructive/40 bg-destructive/10 p-3 pl-8 text-sm text-destructive">
            {issues.map((i, k) => <li key={k}>{formatIssues([i])}</li>)}
          </ul>
        )}
        <div className="flex justify-end gap-2">
          <DialogClose render={<Button variant="outline" className="min-h-11" disabled={run.isPending} />}>Cancel</DialogClose>
          <Button className="min-h-11" disabled={!file || run.isPending} onClick={() => file && run.mutate(file)}>
            {run.isPending ? "Importing…" : "Import"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
