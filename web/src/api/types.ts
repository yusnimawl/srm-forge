import type { components } from "./schema"

type S = components["schemas"]

export type Evaluation = S["EvaluationOut"]
export type SearchResult = S["SearchResultOut"]
export type Material = S["MaterialOut"]
export type CaseSummary = S["CaseSummaryOut"]
/** `inputs` is a raw record because a draft may hold invalid inputs; cast it to `CaseInputs` where it is valid. */
export type Case = S["CaseOut"]
export type CaseInputs = S["CaseInputs"]
export type Validation = S["ValidationOut"]
export type Winding = S["WindingOut"]
export type Envelope = S["EnvelopeOut"]
export type MapArrays = S["MapArraysOut"]
export type MapCurves = S["MapCurvesOut"]
export type Estimate = S["EstimateOut"]
export type Reference = S["ReferenceOut"]
