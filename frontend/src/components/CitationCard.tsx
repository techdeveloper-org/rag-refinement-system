import type { Citation } from "@/api/types";
import { BookIcon } from "@/components/icons";

interface CitationCardProps {
  citation: Citation;
  index: number;
  onJumpToPage?: (page: number) => void;
}

/**
 * CitationCard (FR-008). Renders a single source citation from
 * `AnswerFinalEvent.citations[]` = `Citation{ section_title, page_start,
 * page_end }` (optional `section_id`). The "Jump to page" action targets
 * `page_start`.
 *
 * @param citation - The citation to render.
 * @param index - 1-based reference number shown in the corner chip.
 * @param onJumpToPage - Optional handler for the "Jump to page" action.
 */
export function CitationCard({ citation, index, onJumpToPage }: CitationCardProps): JSX.Element {
  const pages = `Pages ${citation.page_start}-${citation.page_end}`;
  const label = `Citation: ${citation.section_title}, pages ${citation.page_start} to ${citation.page_end}`;

  return (
    <article
      aria-label={label}
      className="flex items-start gap-md rounded-md bg-surface-alt p-md shadow-elevation-1 hover:shadow-elevation-2 transition-shadow"
    >
      <BookIcon className="w-5 h-5 text-text-secondary mt-xs shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-sm">
          <h4 className="text-body font-semibold text-text-primary truncate">
            {citation.section_title}
          </h4>
          <span className="shrink-0 rounded-sm bg-primary px-sm text-caption font-semibold text-text-on-primary">
            {index}
          </span>
        </div>
        <p className="text-body-sm text-text-secondary mt-xs">{pages}</p>
      </div>
      {onJumpToPage !== undefined ? (
        <button
          type="button"
          onClick={() => onJumpToPage(citation.page_start)}
          className="shrink-0 min-h-[44px] rounded-md px-md text-body-sm font-semibold text-primary hover:bg-surface-sunken transition-colors"
        >
          Jump to page {citation.page_start}
        </button>
      ) : null}
    </article>
  );
}

/**
 * Empty-citations placeholder shown when `citations[]` is empty (fallback mode).
 * Mirrors the wireframe's "No section citations - full-document retrieval."
 */
export function NoCitations(): JSX.Element {
  return (
    <p className="text-body-sm text-text-secondary italic">
      No section citations - full-document retrieval.
    </p>
  );
}
