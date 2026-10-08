import { useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router"
import { Plus } from "lucide-react"
import { toast } from "sonner"
import { importIssues, useCreateCase, type CaseCreate, type SetupFile } from "@/api/cases"
import { api, type ValidationIssue } from "@/api/client"
import type { Reference } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { errorMessage } from "@/lib/errorMessage"
import { defaultSearchForm, toSearchRequest } from "@/lib/searchForm"

const where = (loc: ValidationIssue["loc"]) => loc.filter((p) => p !== "body").join(".")

function IssueList({ title, items }: { title: string; items: ValidationIssue[] }) {
  if (items.length === 0) return null
  return (
    <div className="space-y-1">
      <h3 className="font-medium">{title}</h3>
      <ul className="list-disc space-y-0.5 pl-5">
        {items.map((i, k) => (
          <li key={k}>
            {where(i.loc) && <code className="num">{where(i.loc)}</code>} {i.msg}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** "New case": a reference machine with the New-search requirements, or an imported setup file. */
export function NewCaseMenu() {
  const navigate = useNavigate()
  const create = useCreateCase()
  const [open, setOpen] = useState(false)
  const [rejected, setRejected] = useState<{ file: string; errors: ValidationIssue[]; warnings: ValidationIssue[] } | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const references = useQuery({ queryKey: ["references"], queryFn: () => api<Reference[]>("/api/references"), staleTime: Infinity })

  const submit = (body: CaseCreate, file = "") =>
    create.mutate(body, {
      onSuccess: (c) => navigate(`/cases/${c.id}`),
      onError: (e) => {
        const issues = importIssues(e)
        if (issues) setRejected({ file, ...issues })
        else toast.error(errorMessage(e))
      },
    })

  const fromReference = (name: Reference["name"]) => {
    setOpen(false)
    submit({ origin: "reference", name, requirements: toSearchRequest(defaultSearchForm()).requirements, preset: "full" })
  }

  const fromFile = async (file: File) => {
    let setup: SetupFile
    try {
      setup = JSON.parse(await file.text())
    } catch {
      toast.error(`${file.name} is not a JSON file`)
      return
    }
    submit({ origin: "import", setup }, file.name)
  }

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger render={<Button className="min-h-11" disabled={create.isPending} />}>
          <Plus className="size-4" /> New case
        </PopoverTrigger>
        <PopoverContent className="w-56 space-y-1">
          <p className="px-2 pb-1 text-xs font-medium text-muted-foreground">From reference</p>
          {references.data?.map(({ name }) => (
            <Button key={name} variant="ghost" className="min-h-11 w-full justify-start" onClick={() => fromReference(name)}>
              {name} machine
            </Button>
          ))}
          <Button
            variant="outline"
            className="min-h-11 w-full justify-start"
            onClick={() => {
              setOpen(false)
              fileInput.current?.click()
            }}
          >
            Import setup file
          </Button>
        </PopoverContent>
      </Popover>
      <input
        ref={fileInput}
        type="file"
        accept=".json,application/json"
        className="hidden"
        aria-label="Setup file"
        onChange={(e) => {
          const f = e.target.files?.[0]
          e.target.value = ""
          if (f) void fromFile(f)
        }}
      />
      <Dialog open={rejected !== null} onOpenChange={(o) => !o && setRejected(null)}>
        <DialogContent>
          <DialogTitle>Setup file rejected</DialogTitle>
          <DialogDescription>{rejected?.file} was not imported.</DialogDescription>
          <IssueList title="Errors" items={rejected?.errors ?? []} />
          <IssueList title="Warnings" items={rejected?.warnings ?? []} />
          <DialogClose render={<Button variant="outline" className="min-h-11 self-end" />}>Close</DialogClose>
        </DialogContent>
      </Dialog>
    </>
  )
}
