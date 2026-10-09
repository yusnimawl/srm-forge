import { lazy, Suspense } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Overlay } from "@/lib/analysis"
import type { Evaluation } from "@/api/types"
import DesignFactorsTab from "./DesignFactorsTab"
import MapTab from "./MapTab"
import PerformanceTab from "./PerformanceTab"
import WaveformsTab from "./WaveformsTab"

const FieldTab = lazy(() => import("./FieldTab"))

/** Overlays (at most 6 cases) draw on the Performance and Design factors charts; `label` names the main case in their legends.
 *  `performanceOnly` drops the tab bar and the other tabs. */
export default function AnalysisTabs({
  evaluation,
  overlays = [],
  label,
  performanceOnly = false,
  baseSpeedRpm,
  caseId,
}: {
  evaluation: Evaluation
  overlays?: Overlay[]
  label?: string
  performanceOnly?: boolean
  baseSpeedRpm?: number
  /** Enables the field tab (an evaluated case only). */
  caseId?: string
}) {
  if (performanceOnly) return <PerformanceTab evaluation={evaluation} overlays={overlays} label={label} />
  const showField = !!caseId && evaluation.status === "ok"
  return (
    <Tabs defaultValue="performance">
      <TabsList>
        <TabsTrigger value="performance">Performance</TabsTrigger>
        {evaluation.envelope?.waveforms && <TabsTrigger value="waveforms">Waveforms</TabsTrigger>}
        <TabsTrigger value="map">Map</TabsTrigger>
        <TabsTrigger value="factors">Design factors</TabsTrigger>
        {showField && <TabsTrigger value="field">Field</TabsTrigger>}
      </TabsList>
      <TabsContent value="performance">
        <PerformanceTab evaluation={evaluation} overlays={overlays} label={label} />
      </TabsContent>
      {evaluation.envelope?.waveforms && (
        <TabsContent value="waveforms">
          <WaveformsTab evaluation={evaluation} baseSpeedRpm={baseSpeedRpm} />
        </TabsContent>
      )}
      <TabsContent value="map">
        <MapTab evaluation={evaluation} />
      </TabsContent>
      <TabsContent value="factors">
        <DesignFactorsTab evaluation={evaluation} overlays={overlays} label={label} />
      </TabsContent>
      {showField && (
        <TabsContent value="field">
          <Suspense fallback={<p className="py-4 text-sm text-muted-foreground">Loading...</p>}>
            <FieldTab key={caseId} caseId={caseId} />
          </Suspense>
        </TabsContent>
      )}
    </Tabs>
  )
}
