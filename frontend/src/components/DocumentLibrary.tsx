import type { Document, DocumentListResponse } from "@/api/types";
import { DocumentCard } from "@/components/DocumentCard";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/Button";

interface DocumentLibraryProps {
  list: DocumentListResponse;
  onOpen: (doc: Document) => void;
  onDelete: (doc: Document) => void;
  onExportData: (doc: Document) => void;
  onPageChange?: (page: number) => void;
}

/**
 * DocumentLibrary (FR-024). Renders the paginated document grid from
 * `GET /v1/documents` -> `DocumentListResponse{ data[], pagination }`. Shows an
 * EmptyState when `data` is empty and prev/next controls driven by
 * `pagination`.
 *
 * @param list - The paginated document list response.
 * @param onOpen - Open a document.
 * @param onDelete - Erase a document (DPDP).
 * @param onExportData - DPDP access export for a document.
 * @param onPageChange - Called with the requested 1-based page number.
 */
export function DocumentLibrary({
  list,
  onOpen,
  onDelete,
  onExportData,
  onPageChange,
}: DocumentLibraryProps): JSX.Element {
  const { data, pagination } = list;

  if (data.length === 0) {
    return (
      <EmptyState
        heading="No documents yet"
        body="Upload a PDF above to extract its table of contents and start asking questions."
      />
    );
  }

  const canPrev = pagination.page > 1;
  const canNext = pagination.page < pagination.total_pages;

  return (
    <section aria-label="Your documents" className="flex flex-col gap-md">
      <h2 className="text-heading-2 font-semibold text-text-primary">
        Your documents ({pagination.total_count})
      </h2>
      <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3">
        {data.map((doc) => (
          <DocumentCard
            key={doc.doc_id}
            document={doc}
            onOpen={onOpen}
            onDelete={onDelete}
            onExportData={onExportData}
          />
        ))}
      </div>
      <div className="flex items-center justify-center gap-md">
        <Button
          variant="ghost"
          disabled={!canPrev}
          onClick={() => onPageChange?.(pagination.page - 1)}
        >
          Prev
        </Button>
        <span className="text-body-sm text-text-secondary">
          Page {pagination.page} of {pagination.total_pages}
        </span>
        <Button
          variant="ghost"
          disabled={!canNext}
          onClick={() => onPageChange?.(pagination.page + 1)}
        >
          Next
        </Button>
      </div>
    </section>
  );
}
