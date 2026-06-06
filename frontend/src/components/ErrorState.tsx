import type { Problem } from "@/api/types";
import { Button } from "@/components/Button";

interface ErrorStateProps {
  problem: Problem;
  onRetry?: () => void;
  midStream?: boolean;
}

/**
 * ErrorState (NFR-010). Renders an RFC 7807 `Problem` (`code` + `detail`) as a
 * user-facing alert. Used both for blocking pre-stream errors and for
 * mid-stream SSE `error` events, which must be surfaced as `role="alert"` and
 * never silently dropped (AC-ADV-002).
 *
 * Only `code` and `detail` are shown - no internal/stack detail is exposed.
 *
 * @param problem - The RFC 7807 problem to display.
 * @param onRetry - Optional retry handler; renders a Retry button when present.
 * @param midStream - Marks the error as occurring after the stream opened.
 */
export function ErrorState({ problem, onRetry, midStream = false }: ErrorStateProps): JSX.Element {
  const detail = problem.detail ?? problem.title;
  return (
    <div
      role="alert"
      className="flex flex-col gap-sm rounded-md border border-error bg-surface-alt px-md py-md"
    >
      <div className="flex items-baseline gap-sm">
        <span className="text-body-sm font-bold text-error">{problem.code}</span>
        {midStream ? (
          <span className="text-caption text-text-secondary">(answer interrupted)</span>
        ) : null}
      </div>
      <p className="m-0 text-body-sm text-text-primary">{detail}</p>
      {onRetry !== undefined ? (
        <div>
          <Button variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        </div>
      ) : null}
    </div>
  );
}
