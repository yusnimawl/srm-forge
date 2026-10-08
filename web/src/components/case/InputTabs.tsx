import { useRef, useState } from "react"
import { toast } from "sonner"
import { importIssues, type SetupFile } from "@/api/cases"
import { api } from "@/api/client"
import type { Evaluation } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CASE_TABS, issueKey, tabOfKey, type CaseTab } from "@/lib/caseForm"
import { errorMessage } from "@/lib/errorMessage"
import { applySection, download, sectionSetup } from "@/lib/exports"
import { DimensionTab } from "./DimensionTab"
import { DriveTab } from "./DriveTab"
import { MaterialTab } from "./MaterialTab"
import { RequirementTab } from "./RequirementTab"
import type { TabProps } from "./fields"
import { WindingTab } from "./WindingTab"

/** Exports the open tab's inputs as a setup file holding that section, or merges the section of a setup file into the draft. */
function SectionIo({ tab, form, update, canImport }: TabProps & { tab: CaseTab; canImport: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const label = CASE_TABS.find((t) => t.id === tab)?.label ?? tab

  const importFile = async (file: File) => {
    try {
      let json: unknown
      try {
        json = JSON.parse(await file.text())
      } catch {
        throw new Error(`${file.name} is not a JSON file`)
      }
      const checked = await api<SetupFile>("/api/setup/check", { method: "POST", body: JSON.stringify(json) })
      if (!applySection(form, tab, checked)) throw new Error(`${file.name} has no ${label.toLowerCase()} section`)
      update((f) => applySection(f, tab, checked) ?? f)
    } catch (e) {
      const issues = importIssues(e)
      toast.error(issues ? `${file.name}: ${issues.errors.map((i) => `${issueKey(i.loc.filter((p) => p !== "body"))} ${i.msg}`).join("; ")}` : errorMessage(e))
    }
  }

  return (
    <div className="flex flex-wrap gap-2 py-2">
      <Button variant="outline" className="min-h-11" onClick={() => download(`${tab}.srm-setup.json`, JSON.stringify(sectionSetup(form, tab), null, 2))}>
        Export {label.toLowerCase()}
      </Button>
      <Button variant="outline" className="min-h-11" disabled={!canImport} onClick={() => input.current?.click()}>
        Import {label.toLowerCase()}
      </Button>
      <input ref={input} type="file" accept=".json,application/json" className="hidden" aria-label={`${label} setup file`}
        onChange={(e) => {
          const f = e.target.files?.[0]
          e.target.value = ""
          if (f) void importFile(f)
        }} />
    </div>
  )
}

/** The five input tabs. A tab that holds a field with an error shows the error count; `readOnly` disables every input. */
export function InputTabs({ readOnly, evaluation, ...p }: TabProps & { readOnly: boolean; evaluation: Evaluation | null }) {
  const [tab, setTab] = useState<CaseTab>("requirement")
  const count = (id: string) => Object.keys(p.errors).filter((k) => tabOfKey(k) === id).length
  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as CaseTab)}>
      <TabsList className="max-w-full overflow-x-auto">
        {CASE_TABS.map((t) => (
          <TabsTrigger key={t.id} value={t.id}>
            {t.label}
            {count(t.id) > 0 && (
              <span className="ml-1 rounded-full bg-destructive px-1.5 text-xs text-white" aria-label={`${count(t.id)} ${count(t.id) === 1 ? "error" : "errors"}`}>
                {count(t.id)}
              </span>
            )}
          </TabsTrigger>
        ))}
      </TabsList>
      <SectionIo tab={tab} canImport={!readOnly} {...p} />
      <fieldset disabled={readOnly} className="min-w-0 border-0 p-0">
        <TabsContent value="requirement"><RequirementTab {...p} /></TabsContent>
        <TabsContent value="dimension"><DimensionTab {...p} /></TabsContent>
        <TabsContent value="material"><MaterialTab {...p} /></TabsContent>
        <TabsContent value="winding"><WindingTab {...p} /></TabsContent>
        <TabsContent value="drive"><DriveTab {...p} evaluation={evaluation} /></TabsContent>
      </fieldset>
    </Tabs>
  )
}
