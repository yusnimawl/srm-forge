import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Overlay } from "@/lib/analysis"
import type { Evaluation } from "@/api/types"
import DesignFactorsTab from "./DesignFactorsTab"
import MapTab from "./MapTab"
import PerformanceTab from "./PerformanceTab"
import WaveformsTab from "./WaveformsTab"

/** Overlays (at most 6 cases) draw on the Performance and Design factors charts; `label` names the main case in their legends.
 *  `performanceOnly` drops the tab bar and the other tabs. */
export default function AnalysisTabs({
  evaluation,
  overlays = [],
  label,
  performanceOnly = false,
  baseSpeedRpm,
  caseId: _caseId,
}: {
  evaluation: Evaluation
  overlays?: Overlay[]
  label?: string
  performanceOnly?: boolean
  baseSpeedRpm?: number
  /** Used by the field tab. */
  caseId?: string
}) {
  if (performanceOnly) return <PerformanceTab evaluation={evaluation} overlays={overlays} label={label} />
  return (
    <Tabs defaultValue="performance">
      <TabsList>
        <TabsTrigger value="performance">Performance</TabsTrigger>
        {evaluation.envelope?.waveforms && <TabsTrigger value="waveforms">Waveforms</TabsTrigger>}
        <TabsTrigger value="map">Map</TabsTrigger>
        <TabsTrigger value="factors">Design factors</TabsTrigger>
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
    </Tabs>
  )
}
