import type { Confidence, RoutingSummary } from "@/api/types";

/** Confidence level label per PRD 8.3 thresholds. */
export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";

/** PRD 8.3 thresholds: >=0.70 HIGH, 0.50-0.69 MEDIUM, <0.50 LOW. */
export const HIGH_THRESHOLD = 0.7;
export const MEDIUM_THRESHOLD = 0.5;

/**
 * Map a scalar confidence to its PRD 8.3 level.
 *
 * @param value - A confidence in [0, 1].
 * @returns HIGH (>=0.70), MEDIUM (0.50-0.69), or LOW (<0.50).
 */
export function confidenceLevel(value: Confidence): ConfidenceLevel {
  if (value >= HIGH_THRESHOLD) {
    return "HIGH";
  }
  if (value >= MEDIUM_THRESHOLD) {
    return "MEDIUM";
  }
  return "LOW";
}

/**
 * Reduce the routing `confidence[]` array to the single scalar the
 * ConfidenceMeter displays (GRC-002 binding rule D1).
 *
 * The displayed scalar is `max(routing.confidence[])` - the routing decision's
 * strongest signal. An empty array yields null, signalling the Fallback variant.
 *
 * @param confidence - The per-section confidence array from RoutingSummary.
 * @returns The maximum confidence, or null when the array is empty.
 */
export function maxConfidence(confidence: readonly Confidence[]): Confidence | null {
  if (confidence.length === 0) {
    return null;
  }
  return confidence.reduce((acc, value) => (value > acc ? value : acc), confidence[0] as Confidence);
}

/** Resolved display state for the ConfidenceMeter. */
export type MeterState =
  | { variant: "fallback" }
  | { variant: "level"; level: ConfidenceLevel; value: Confidence };

/**
 * Resolve the ConfidenceMeter display state from a routing summary (GRC-002).
 *
 * Renders the Fallback variant when `routing.fallback` is true OR the
 * `confidence[]` array is empty; otherwise renders the level + scalar derived
 * from `max(confidence[])`.
 *
 * @param routing - The RoutingSummary attached to the answer's final event.
 * @returns The meter state to render.
 */
export function resolveMeterState(routing: RoutingSummary): MeterState {
  const scalar = maxConfidence(routing.confidence);
  if (routing.fallback || scalar === null) {
    return { variant: "fallback" };
  }
  return { variant: "level", level: confidenceLevel(scalar), value: scalar };
}
