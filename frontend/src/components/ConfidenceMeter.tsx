import type { RoutingSummary } from "@/api/types";
import type { ConfidenceLevel, MeterState } from "@/domain/confidence";
import { resolveMeterState } from "@/domain/confidence";
import {
  CircleEmptyIcon,
  CircleFilledIcon,
  CircleHalfIcon,
  WarningIcon,
} from "@/components/icons";

interface ConfidenceMeterProps {
  routing: RoutingSummary;
}

const LEVEL_FILL: Record<ConfidenceLevel, string> = {
  HIGH: "bg-conf-high",
  MEDIUM: "bg-conf-med",
  LOW: "bg-conf-low",
};

const LEVEL_TEXT: Record<ConfidenceLevel, string> = {
  HIGH: "text-conf-high",
  MEDIUM: "text-conf-med",
  LOW: "text-conf-low",
};

/**
 * Render the per-level confidence icon. The icon shape differs per level so the
 * level is conveyed by icon (plus label, numeral, and bar) and never by color
 * alone (WCAG 1.4.1).
 */
function LevelIcon({ level }: { level: ConfidenceLevel }): JSX.Element {
  const className = `w-5 h-5 ${LEVEL_TEXT[level]}`;
  if (level === "HIGH") {
    return <CircleFilledIcon className={className} />;
  }
  if (level === "MEDIUM") {
    return <CircleHalfIcon className={className} />;
  }
  return <CircleEmptyIcon className={className} />;
}

/**
 * ConfidenceMeter (FR-011). Renders the routing decision's confidence as one
 * level (HIGH/MEDIUM/LOW) derived from `max(routing.confidence[])` (GRC-002),
 * shown via label text + numeric value + fill bar + level icon. When
 * `routing.fallback` is true or `confidence[]` is empty, renders the Fallback
 * variant.
 *
 * Exposes `role="meter"` with `aria-valuemin/now/max` and a descriptive
 * `aria-valuetext` so assistive tech reads e.g. "HIGH, 0.94".
 */
export function ConfidenceMeter({ routing }: ConfidenceMeterProps): JSX.Element {
  const state: MeterState = resolveMeterState(routing);

  if (state.variant === "fallback") {
    return (
      <section aria-labelledby="confidence-heading" className="py-sm">
        <h3 id="confidence-heading" className="text-body-sm font-medium text-text-secondary mb-xs">
          Routing confidence
        </h3>
        <div
          role="meter"
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={0}
          aria-valuetext="Fallback, full-document retrieval"
          className="flex items-center gap-sm rounded-full bg-surface-sunken px-md py-sm"
        >
          <WarningIcon className="w-5 h-5 text-fallback" />
          <span className="text-body-sm font-semibold text-fallback">FALLBACK</span>
          <span className="text-body-sm text-text-secondary">Searched the whole document</span>
        </div>
      </section>
    );
  }

  const percent = Math.round(state.value * 100);
  const display = state.value.toFixed(2);

  return (
    <section aria-labelledby="confidence-heading" className="py-sm">
      <h3 id="confidence-heading" className="text-body-sm font-medium text-text-secondary mb-xs">
        Routing confidence
      </h3>
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={state.value}
        aria-valuetext={`${state.level}, ${display}`}
        className="flex items-center gap-md rounded-full bg-surface-alt px-md py-sm"
      >
        <LevelIcon level={state.level} />
        <span className={`text-body-sm font-bold ${LEVEL_TEXT[state.level]}`}>{state.level}</span>
        <span className="text-body-sm font-semibold text-text-primary tabular-nums">{display}</span>
        <div className="flex-1 h-2 rounded-full bg-conf-track overflow-hidden" aria-hidden="true">
          <div
            className={`h-full ${LEVEL_FILL[state.level]}`}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>
    </section>
  );
}
