import { SrmSpinner } from "@/components/brand/SrmSpinner"
import { lazy, Suspense } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Overlay } from "@/lib/analysis"
import type { Evaluation } from "@/api/types"
import DesignFactorsTab from "./DesignFactorsTab"
import MapTab from "./MapTab"
import PerformanceTab from "./PerformanceTab"
import WaveformsTab from "./WaveformsTab"

const FieldTab = lazy(() => import("./FieldTab"))
const ControlTab = lazy(() => import("./ControlTab"))

/** Overlays (at most 6 cases) draw on the Performance and Design factors charts; `label` names the main case in their legends.
 *  `performanceOnly` drops the tab bar and the other tabs. */
export default function AnalysisTabs({
  evaluation,
  overlays = [],
  label,
  performanceOnly = false,
  baseSpeedRpm,
  caseId,
  busVoltage,
}: {
  evaluation: Evaluation
  overlays?: Overlay[]
  label?: string
  performanceOnly?: boolean
  baseSpeedRpm?: number
  /** Enables the field tab (an evaluated case only). */
  caseId?: string
  /** Bus voltage (V) the control scenario starts from. */
  busVoltage?: number
}) {
  if (performanceOnly) return <PerformanceTab evaluation={evaluation} overlays={overlays} label={label} />
  const showField = !!caseId && evaluation.status === "ok"
  return (
    <Tabs defaultValue="performance" className="gap-0 overflow-hidden rounded-[10px] border border-border bg-card [&_[data-slot=tabs-content]]:px-4 [&_[data-slot=tabs-content]]:pb-4">
      <TabsList className="px-2.5 pt-2">
        <TabsTrigger value="performance">Performance</TabsTrigger>
        {evaluation.envelope?.waveforms && <TabsTrigger value="waveforms">Waveforms</TabsTrigger>}
        <TabsTrigger value="map">Map</TabsTrigger>
        <TabsTrigger value="factors">Design factors</TabsTrigger>
        {showField && <TabsTrigger value="field">Field</TabsTrigger>}
        {showField && <TabsTrigger value="control">Control</TabsTrigger>}
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
          <Suspense fallback={<SrmSpinner className="py-4" label="Loading..." showLabel />}>
            <FieldTab key={caseId} caseId={caseId} />
          </Suspense>
        </TabsContent>
      )}
      {showField && (
        <TabsContent value="control">
          <Suspense fallback={<SrmSpinner className="py-4" label="Loading..." showLabel />}>
            <ControlTab key={caseId} caseId={caseId} busVoltage={busVoltage} peakTorque={evaluation.key?.peak_torque} baseSpeedRpm={baseSpeedRpm} />
          </Suspense>
        </TabsContent>
      )}
    </Tabs>
  )
}
