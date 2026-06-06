import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { Document, DocumentListResponse, IngestRequestFields } from "@/api/types";
import { UploadDropzone } from "@/components/UploadDropzone";
import { DocumentLibrary } from "@/components/DocumentLibrary";
import { Toast } from "@/components/Toast";
import type { ToastTone } from "@/components/Toast";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";

interface UploadLibraryScreenProps {
  client: ApiClient;
  onOpenDocument: (doc: Document) => void;
}

interface ToastState {
  tone: ToastTone;
  message: string;
}

/**
 * UploadLibrary screen (FR-001, FR-024, FR-025, FR-026, FR-027, FR-028). Hosts
 * the UploadDropzone and the paginated DocumentLibrary. Upload outcomes
 * (indexed / dedup / fallback-only / error) and erasure/export results surface
 * as Toasts driven by real API responses. A deduplicated upload opens the
 * existing document via onOpenDocument so the toast copy matches the behavior.
 *
 * @param client - The typed API client.
 * @param onOpenDocument - Navigate to the document/chat view for a document.
 */
export function UploadLibraryScreen({ client, onOpenDocument }: UploadLibraryScreenProps): JSX.Element {
  const [list, setList] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [uploading, setUploading] = useState<boolean>(false);
  const [page, setPage] = useState<number>(1);
  const [toast, setToast] = useState<ToastState | null>(null);

  const loadPage = useCallback(
    async (targetPage: number): Promise<void> => {
      setLoading(true);
      try {
        const response = await client.listDocuments({ page: targetPage });
        setList(response);
      } catch (error) {
        const message = error instanceof ApiError ? error.problem.detail ?? error.problem.title : "Failed to load documents.";
        setToast({ tone: "error", message });
      } finally {
        setLoading(false);
      }
    },
    [client],
  );

  useEffect(() => {
    void loadPage(page);
  }, [loadPage, page]);

  const handleUpload = useCallback(
    async (file: File, fields: IngestRequestFields): Promise<void> => {
      setUploading(true);
      try {
        const result = await client.ingestDocument(file, fields);
        if (result.deduplicated) {
          setToast({ tone: "info", message: "Already in library - opened existing." });
          const existing = await client.getDocument(result.doc_id);
          onOpenDocument(existing);
          return;
        }
        if (result.ingest_status === "fallback_only") {
          setToast({ tone: "warning", message: "No TOC detected - full-doc mode." });
        } else if (result.ingest_status === "ephemeral") {
          setToast({ tone: "info", message: "Processed in no-retention mode (not stored)." });
        } else {
          setToast({ tone: "success", message: `Indexed - ${result.toc.length} sections found.` });
        }
        await loadPage(page);
      } catch (error) {
        const message = error instanceof ApiError ? error.problem.detail ?? error.problem.title : "Upload failed.";
        setToast({ tone: "error", message });
      } finally {
        setUploading(false);
      }
    },
    [client, loadPage, page, onOpenDocument],
  );

  const handleDelete = useCallback(
    async (doc: Document): Promise<void> => {
      try {
        await client.deleteDocument(doc.doc_id);
        setToast({ tone: "success", message: "Document erased (DPDP)." });
        await loadPage(page);
      } catch (error) {
        const message = error instanceof ApiError ? error.problem.detail ?? error.problem.title : "Erasure failed.";
        setToast({ tone: "error", message });
      }
    },
    [client, loadPage, page],
  );

  const handleExport = useCallback(
    async (doc: Document): Promise<void> => {
      try {
        const data = await client.exportDocumentData(doc.doc_id);
        setToast({
          tone: "success",
          message: `Exported data: ${data.pii_fields.length} PII field(s) inventoried.`,
        });
      } catch (error) {
        const message = error instanceof ApiError ? error.problem.detail ?? error.problem.title : "Export failed.";
        setToast({ tone: "error", message });
      }
    },
    [client],
  );

  return (
    <main id="main-content" className="mx-auto flex max-w-5xl flex-col gap-xl px-md py-xl">
      {toast !== null ? (
        <Toast tone={toast.tone} message={toast.message} onDismiss={() => setToast(null)} />
      ) : null}

      <UploadDropzone
        uploading={uploading}
        progressLabel="Parsing TOC..."
        onUpload={(file, fields) => void handleUpload(file, fields)}
      />

      {loading || list === null ? (
        <LoadingSkeleton variant="card-grid" />
      ) : (
        <DocumentLibrary
          list={list}
          onOpen={onOpenDocument}
          onDelete={(doc) => void handleDelete(doc)}
          onExportData={(doc) => void handleExport(doc)}
          onPageChange={setPage}
        />
      )}
    </main>
  );
}
