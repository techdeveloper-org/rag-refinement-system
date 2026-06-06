import { useEffect, useState } from "react";
import type { ApiClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { DocumentId, SectionId, TocEntry, TocResponse } from "@/api/types";
import { TocSidebar } from "@/components/TocSidebar";
import { FallbackBanner } from "@/components/FallbackBanner";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/Button";

interface DocumentViewScreenProps {
  client: ApiClient;
  documentId: DocumentId;
  documentTitle: string;
  onStartChat: () => void;
}

/**
 * DocumentView screen (FR-002, FR-003, FR-009 structural). Fetches and renders
 * `GET /v1/documents/{id}/toc` as a TocSidebar. For `fallback_only` documents a
 * structural FallbackBanner is shown. A selected section drives the page-range
 * detail panel.
 *
 * @param client - The typed API client.
 * @param documentId - The open document id.
 * @param documentTitle - The open document title (header context).
 * @param onStartChat - Navigate to the chat screen for this document.
 */
export function DocumentViewScreen({
  client,
  documentId,
  documentTitle,
  onStartChat,
}: DocumentViewScreenProps): JSX.Element {
  const [toc, setToc] = useState<TocResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<TocEntry | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void client
      .getDocumentToc(documentId)
      .then((response) => {
        if (active) {
          setToc(response);
        }
      })
      .catch((caught: unknown) => {
        if (active) {
          setError(caught instanceof ApiError ? caught : null);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [client, documentId]);

  const selectedId: SectionId | undefined = selected?.section_id;

  return (
    <main id="main-content" className="flex min-h-[60vh]">
      {loading ? (
        <div className="w-toc-sidebar p-md">
          <LoadingSkeleton variant="bar" />
        </div>
      ) : error !== null ? (
        <div className="p-md">
          <ErrorState problem={error.problem} />
        </div>
      ) : toc !== null ? (
        <>
          <TocSidebar toc={toc} selectedSectionId={selectedId} onSelectSection={setSelected} />
          <section className="flex-1 px-lg py-md">
            {toc.fallback_only ? (
              <FallbackBanner message="This document has no usable structure - queries will search the whole document." />
            ) : null}
            <div className="flex items-center justify-between gap-md">
              <h1 className="text-heading-1 font-bold text-text-primary">{documentTitle}</h1>
              <Button onClick={onStartChat}>Ask a question</Button>
            </div>
            {selected !== null ? (
              <p className="mt-md text-body text-text-secondary">
                Selected section <strong className="text-text-primary">{selected.title}</strong> &middot;
                pages {selected.page_start}-{selected.page_end}
              </p>
            ) : (
              <p className="mt-md text-body text-text-secondary">
                Select a section to see its page range, or start a chat to ask a question.
              </p>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
