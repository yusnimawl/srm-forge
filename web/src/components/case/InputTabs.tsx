import type { Evaluation } from "@/api/types"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CASE_TABS, tabOfKey } from "@/lib/caseForm"
import { DimensionTab } from "./DimensionTab"
import { DriveTab } from "./DriveTab"
import { MaterialTab } from "./MaterialTab"
import { RequirementTab } from "./RequirementTab"
import type { TabProps } from "./fields"
import { WindingTab } from "./WindingTab"

/** The five input tabs. A tab that holds a field with an error shows the error count; `readOnly` disables every input. */
export function InputTabs({ readOnly, evaluation, ...p }: TabProps & { readOnly: boolean; evaluation: Evaluation | null }) {
  const count = (id: string) => Object.keys(p.errors).filter((k) => tabOfKey(k) === id).length
  return (
    <Tabs defaultValue="requirement">
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
