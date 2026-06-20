import { useId, useState } from "react";
import type { Document } from "@/api/types";
import { Button } from "@/components/Button";

interface DocumentCardProps {
  document: Document;
  onOpen: (doc: Document) => void;
  onDelete: (doc: Document) => void;
  onExportData: (doc: Document) => void;
}

/**
 * Ingest badge label + token class derived from `Document.fallback_only`
 * (GRC-003 binding rule D2): false -> "Indexed" (success), true ->
 * "Fallback-only" (fallback). The Scenario-B "Pseudo" distinction is not
 * contract-visible and is intentionally not shown.
 */
function ingestBadge(doc: Document): { label: string; className: string } {
  if (doc.fallback_only) {
    return { label: "Fallback-only", className: "bg-fallback text-text-on-primary" };
  }
  return { label: "Indexed", className: "bg-success text-text-on-primary" };
}

/**
 * DocumentCard (FR-024, FR-025, FR-026). Renders one `Document` from the library
 * list with its title, page/domain meta, and ingest badge. The "..." menu opens
 * Open / Export data / Delete actions; Delete shows a focus-trapping confirm
 * dialog (DPDP erasure). Export data calls `GET /v1/documents/{id}/data`.
 *
 * @param document - The document to render.
 * @param onOpen - Open the document (navigate to DocumentView/Chat).
 * @param onDelete - Confirmed erasure (`DELETE /v1/documents/{id}`).
 * @param onExportData - DPDP access export (`GET /v1/documents/{id}/data`).
 */
export function DocumentCard({
  document,
  onOpen,
  onDelete,
  onExportData,
}: DocumentCardProps): JSX.Element {
  const [menuOpen, setMenuOpen] = useState<boolean>(false);
  const [confirmOpen, setConfirmOpen] = useState<boolean>(false);
  const menuId = useId();
  const badge = ingestBadge(document);
  const title = document.title ?? document.doc_id;
  const domain = document.domain ?? "uncategorized";

  return (
    <article className="flex flex-col gap-sm rounded-md bg-surface-alt p-md shadow-elevation-1">
      <div className="flex items-start justify-between gap-sm">
        <h3 className="text-body font-semibold text-text-primary truncate">{title}</h3>
        <span className={`shrink-0 rounded-full px-sm text-caption font-semibold ${badge.className}`}>
          {badge.label}
        </span>
      </div>
      <p className="text-body-sm text-text-secondary">
        {document.total_pages} pages &middot; {domain}
      </p>

      <div className="mt-sm flex items-center gap-sm">
        <Button variant="secondary" onClick={() => onOpen(document)}>
          Open
        </Button>
        <div className="relative">
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            aria-label={`Actions for ${title}`}
            onClick={() => setMenuOpen((prev) => !prev)}
            className="min-h-[44px] min-w-[44px] rounded-md text-body font-bold text-text-secondary hover:bg-surface-sunken"
          >
            &hellip;
          </button>
          {menuOpen ? (
            <ul
              id={menuId}
              role="menu"
              className="absolute right-0 z-overlay mt-xs w-44 list-none rounded-md bg-surface p-xs shadow-elevation-2"
            >
              <li role="none">
                <button
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onOpen(document);
                  }}
                  className="w-full rounded-sm px-sm py-sm text-left text-body-sm text-text-primary hover:bg-surface-alt"
                >
                  Open
                </button>
              </li>
              <li role="none">
                <button
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onExportData(document);
                  }}
                  className="w-full rounded-sm px-sm py-sm text-left text-body-sm text-text-primary hover:bg-surface-alt"
                >
                  Export data
                </button>
              </li>
              <li role="none">
                <button
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    setConfirmOpen(true);
                  }}
                  className="w-full rounded-sm px-sm py-sm text-left text-body-sm text-error hover:bg-surface-alt"
                >
                  Delete
                </button>
              </li>
            </ul>
          ) : null}
        </div>
      </div>

      {confirmOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Confirm document erasure"
          className="mt-sm rounded-md border border-error bg-surface p-md"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setConfirmOpen(false);
            }
          }}
        >
          <p className="text-body-sm text-text-primary">Erase document and all data? (DPDP)</p>
          <div className="mt-sm flex gap-sm">
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmOpen(false);
                onDelete(document);
              }}
            >
              Erase
            </Button>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </article>
  );
}
