import type { ReactNode } from "react";

interface EmptyStateProps {
  heading: string;
  body: string;
  action?: ReactNode;
}

/**
 * EmptyState. Shown when a collection is empty (e.g. `DocumentListResponse.data
 * === []` or no chat messages yet). Heading uses primary text, body uses
 * secondary text, with an optional call-to-action.
 *
 * @param heading - Short empty-state title.
 * @param body - Supporting explanation.
 * @param action - Optional CTA element.
 */
export function EmptyState({ heading, body, action }: EmptyStateProps): JSX.Element {
  return (
    <div className="flex flex-col items-center gap-sm rounded-lg bg-surface-alt px-lg py-2xl text-center">
      <h2 className="text-heading-3 font-semibold text-text-primary">{heading}</h2>
      <p className="max-w-chat text-body text-text-secondary">{body}</p>
      {action !== undefined ? <div className="mt-sm">{action}</div> : null}
    </div>
  );
}
