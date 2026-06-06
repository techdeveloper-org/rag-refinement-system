import { WarningIcon } from "@/components/icons";

interface FallbackBannerProps {
  message?: string;
}

/**
 * FallbackBanner (FR-009). Shown when the router fell back to full-document
 * retrieval (`AnswerFinalEvent.routing.fallback === true`) or a document has no
 * usable structure (`TocResponse.fallback_only === true`). State is conveyed by
 * icon + text + color (not color alone). Exposes `role="alert"` so the change
 * is announced.
 *
 * @param message - Optional override of the default fallback message.
 */
export function FallbackBanner({ message }: FallbackBannerProps): JSX.Element {
  const text =
    message ??
    "Low routing confidence - searched the whole document. The answer below was not scoped to a specific section.";
  return (
    <div
      role="alert"
      className="flex items-start gap-sm rounded-md bg-fallback px-md py-md text-text-on-primary"
    >
      <WarningIcon className="w-5 h-5 shrink-0 mt-xs" />
      <p className="m-0 text-body-sm">{text}</p>
    </div>
  );
}
