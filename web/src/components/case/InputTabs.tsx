import { useRef, useState } from "react"
import { toast } from "sonner"
import { checkSetupFile, requestMessage } from "@/api/cases"
import type { Evaluation } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CASE_TABS, tabOfKey, type CaseTab } from "@/lib/caseForm"
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
      const checked = await checkSetupFile(file)
      const next = applySection(form, tab, checked)
      if (!next) throw new Error(`${file.name} has no ${label.toLowerCase()} section`)
      update((f) => applySection(f, tab, checked) ?? f)
      // The winding section carries the margin, which the Material tab shows.
      if (tab === "winding" && next.margin !== form.margin) toast.message("Margin (Material tab) also set from the file")
    } catch (e) {
      toast.error(`${file.name}: ${requestMessage(e)}`)
    }
  }

  return (
    <div className="flex flex-wrap gap-2 px-4 py-3">
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
export function InputTabs({ readOnly, evaluation, imported, ...p }: TabProps & { readOnly: boolean; evaluation: Evaluation | null; imported?: boolean }) {
  const [tab, setTab] = useState<CaseTab>("requirement")
  const count = (id: string) => Object.keys(p.errors).filter((k) => tabOfKey(k) === id).length
  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as CaseTab)} className="gap-0 overflow-hidden rounded-[10px] border border-border bg-card">
      <TabsList className="px-2.5 pt-2">
        {CASE_TABS.map((t) => (
          <TabsTrigger key={t.id} value={t.id}>
            {t.label}
            {count(t.id) > 0 && (
              <span className="ml-1 rounded-full bg-destructive px-1.5 text-xs text-background" aria-label={`${count(t.id)} ${count(t.id) === 1 ? "error" : "errors"}`}>
                {count(t.id)}
              </span>
            )}
          </TabsTrigger>
        ))}
      </TabsList>
      <SectionIo tab={tab} canImport={!readOnly} {...p} />
      <fieldset disabled={readOnly} className="min-w-0 border-0 px-4 pb-5 pt-1">
        <TabsContent value="requirement"><RequirementTab {...p} /></TabsContent>
        <TabsContent value="dimension"><DimensionTab {...p} imported={imported} /></TabsContent>
        <TabsContent value="material"><MaterialTab {...p} /></TabsContent>
        <TabsContent value="winding"><WindingTab {...p} /></TabsContent>
        <TabsContent value="drive"><DriveTab {...p} evaluation={evaluation} /></TabsContent>
      </fieldset>
    </Tabs>
  )
}
