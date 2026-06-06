import { useId, useState } from "react";
import type { RoutingSummary, TocEntry } from "@/api/types";
import { buildConsideredSections } from "@/domain/explainability";
import type { ConsideredSection } from "@/domain/explainability";
import { ChevronIcon, HelpIcon } from "@/components/icons";

interface ExplainabilityPanelProps {
  routing: RoutingSummary;
  toc: readonly TocEntry[];
}

/** Render one considered-section row, including rejected sections with scores. */
function ConsideredRow({ section }: { section: ConsideredSection }): JSX.Element {
  const pages =
    section.page_start !== null && section.page_end !== null
      ? `p${section.page_start}-${section.page_end}`
      : "pages n/a";
  const status = section.selected ? "selected" : "rejected";
  return (
    <li className="flex items-baseline gap-sm py-xs text-body-sm">
      <span className="flex-1 text-text-primary">{section.title}</span>
      <span className="font-mono text-caption text-text-secondary">{section.section_id}</span>
      <span className="text-text-secondary tabular-nums">{pages}</span>
      <span className="font-semibold text-text-primary tabular-nums">
        {section.confidence.toFixed(2)}
      </span>
      <span className="text-caption text-text-secondary">{status}</span>
    </li>
  );
}

/**
 * ExplainabilityPanel (FR-012, "why did you look here?"). A disclosure that
 * shows the router's `rationale` prose plus the list of sections it considered.
 *
 * The considered-sections list is built by joining `routing.sections[]` x
 * `routing.confidence[]` (index-aligned) to the open document's `toc[]` via
 * `section_id` (GRC-001), resolving each section's title and page range. Both
 * selected and rejected sections are listed with their scores so the user sees
 * "why here, and why not there".
 *
 * Accessibility: a `button[aria-expanded]` controls a `region[aria-labelledby]`;
 * Enter/Space toggles (native button semantics).
 */
export function ExplainabilityPanel({ routing, toc }: ExplainabilityPanelProps): JSX.Element {
  const [expanded, setExpanded] = useState<boolean>(false);
  const headerId = useId();
  const regionId = useId();
  const considered = buildConsideredSections(routing, toc);

  return (
    <section className="rounded-lg bg-surface-sunken">
      <h3 className="m-0">
        <button
          type="button"
          id={headerId}
          aria-expanded={expanded}
          aria-controls={regionId}
          onClick={() => setExpanded((prev) => !prev)}
          className="flex w-full items-center gap-sm min-h-[44px] px-md py-sm text-left text-body font-semibold text-text-primary"
        >
          <HelpIcon className="w-5 h-5 text-primary shrink-0" />
          <span className="flex-1">Why did you look here?</span>
          <ChevronIcon
            className={`w-5 h-5 text-primary transition-transform ${expanded ? "rotate-90" : ""}`}
          />
        </button>
      </h3>
      {expanded ? (
        <div id={regionId} role="region" aria-labelledby={headerId} className="px-md pb-md">
          {routing.rationale !== undefined && routing.rationale.length > 0 ? (
            <p className="text-body text-text-primary italic mb-md">{routing.rationale}</p>
          ) : (
            <p className="text-body-sm text-text-secondary mb-md">No rationale was provided.</p>
          )}
          <p className="text-body-sm font-medium text-text-secondary mb-xs">
            Sections the router considered:
          </p>
          <ul className="m-0 list-none p-0">
            {considered.map((section) => (
              <ConsideredRow key={section.section_id} section={section} />
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
