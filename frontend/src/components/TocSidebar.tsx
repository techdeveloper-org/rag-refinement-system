import type { SectionId, TocEntry as TocEntryType, TocResponse } from "@/api/types";

interface TocSidebarProps {
  toc: TocResponse;
  selectedSectionId?: SectionId;
  onSelectSection?: (entry: TocEntryType) => void;
}

interface TocEntryRowProps {
  entry: TocEntryType;
  selected: boolean;
  onSelect?: (entry: TocEntryType) => void;
}

/**
 * A single TOC tree item. Indents by `level` and shows the section page range.
 * Exposes `treeitem` role with `aria-level` and `aria-current` for tree
 * navigation.
 */
function TocEntryRow({ entry, selected, onSelect }: TocEntryRowProps): JSX.Element {
  const indent = (entry.level - 1) * 16;
  return (
    <li role="none">
      <button
        type="button"
        role="treeitem"
        aria-level={entry.level}
        aria-current={selected ? "true" : undefined}
        onClick={() => onSelect?.(entry)}
        style={{ paddingLeft: `${16 + indent}px` }}
        className={[
          "flex w-full items-baseline justify-between gap-sm py-sm pr-md text-left text-body-sm",
          selected
            ? "border-l-2 border-primary bg-surface-sunken text-text-primary"
            : "border-l-2 border-transparent text-text-primary hover:bg-surface-sunken",
        ].join(" ")}
      >
        <span className="truncate">{entry.title}</span>
        <span className="shrink-0 text-text-secondary tabular-nums">
          {entry.page_start}-{entry.page_end}
        </span>
      </button>
    </li>
  );
}

/**
 * TocSidebar + TocEntry (FR-002, FR-003). Renders `TocResponse.toc[]` as a
 * navigable section tree, indented by `TocEntry.level`, with each entry's
 * page range. For `fallback_only` documents the TOC is empty and an explanatory
 * empty state is shown.
 *
 * @param toc - The TocResponse for the open document.
 * @param selectedSectionId - The currently selected section, if any.
 * @param onSelectSection - Called when a section is activated.
 */
export function TocSidebar({ toc, selectedSectionId, onSelectSection }: TocSidebarProps): JSX.Element {
  return (
    <nav
      aria-label="Document table of contents"
      className="w-toc-sidebar shrink-0 bg-surface-alt"
    >
      {toc.fallback_only || toc.toc.length === 0 ? (
        <p className="px-md py-md text-body-sm text-text-secondary">
          No table of contents detected. This document uses full-document retrieval.
        </p>
      ) : (
        <ul role="tree" aria-label="Sections" className="m-0 list-none p-0">
          {toc.toc.map((entry) => (
            <TocEntryRow
              key={entry.section_id}
              entry={entry}
              selected={entry.section_id === selectedSectionId}
              {...(onSelectSection === undefined ? {} : { onSelect: onSelectSection })}
            />
          ))}
        </ul>
      )}
    </nav>
  );
}
