import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Overlay } from "@/lib/analysis"
import type { Evaluation } from "@/api/types"
import DesignFactorsTab from "./DesignFactorsTab"
import MapTab from "./MapTab"
import PerformanceTab from "./PerformanceTab"

/** Overlays (at most 6 cases) draw on the Performance and Design factors charts; `label` names the main case in their legends. */
export default function AnalysisTabs({ evaluation, overlays = [], label }: { evaluation: Evaluation; overlays?: Overlay[]; label?: string }) {
  return (
    <Tabs defaultValue="performance">
      <TabsList>
        <TabsTrigger value="performance">Performance</TabsTrigger>
        <TabsTrigger value="map">Map</TabsTrigger>
        <TabsTrigger value="factors">Design factors</TabsTrigger>
      </TabsList>
      <TabsContent value="performance">
        <PerformanceTab evaluation={evaluation} overlays={overlays} label={label} />
      </TabsContent>
      <TabsContent value="map">
        <MapTab evaluation={evaluation} />
      </TabsContent>
      <TabsContent value="factors">
        <DesignFactorsTab evaluation={evaluation} overlays={overlays} label={label} />
      </TabsContent>
    </Tabs>
  )
}
