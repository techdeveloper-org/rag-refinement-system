/** Lifecycle phase of an in-flight answer request (FR-018). */
export type StreamPhase = "routing" | "retrieving" | "streaming";

interface StreamingIndicatorProps {
  phase: StreamPhase;
}

const PHASE_LABEL: Record<StreamPhase, string> = {
  routing: "Routing your question...",
  retrieving: "Retrieving the relevant sections...",
  streaming: "Composing the answer...",
};

/**
 * StreamingIndicator (FR-018). Announces the answer lifecycle phase via an
 * `aria-live="polite"` + `aria-busy` status region so progress is conveyed to
 * assistive tech without stealing focus.
 *
 * @param phase - The current request phase.
 */
export function StreamingIndicator({ phase }: StreamingIndicatorProps): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="flex items-center gap-sm text-body-sm text-text-secondary"
    >
      <span aria-hidden="true" className="inline-flex gap-xs">
        <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
        <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
        <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
      </span>
      <span>{PHASE_LABEL[phase]}</span>
    </div>
  );
}
