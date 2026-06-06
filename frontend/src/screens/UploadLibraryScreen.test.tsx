import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadLibraryScreen } from "@/screens/UploadLibraryScreen";
import type { ApiClient } from "@/api/client";
import type {
  Document,
  DocumentListResponse,
  IngestResponse,
} from "@/api/types";

const EXISTING_DOC: Document = {
  doc_id: "doc_existing1",
  title: "Existing Manual",
  total_pages: 120,
  residency_region: "GLOBAL",
  fallback_only: false,
  created_at: "2026-06-06T00:00:00Z",
};

const EMPTY_LIST: DocumentListResponse = {
  data: [],
  pagination: { page: 1, page_size: 20, total_count: 0, total_pages: 1 },
};

const DEDUP_RESPONSE: IngestResponse = {
  doc_id: EXISTING_DOC.doc_id,
  title: EXISTING_DOC.title,
  total_pages: EXISTING_DOC.total_pages,
  toc: [],
  ingest_status: "indexed",
  deduplicated: true,
};

/** Build a fake ApiClient stubbing only the methods this screen calls. */
function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  const base = {
    listDocuments: vi.fn().mockResolvedValue(EMPTY_LIST),
    ingestDocument: vi.fn().mockResolvedValue(DEDUP_RESPONSE),
    getDocument: vi.fn().mockResolvedValue(EXISTING_DOC),
  };
  return { ...base, ...overrides } as unknown as ApiClient;
}

async function uploadAPdf(): Promise<void> {
  const user = userEvent.setup();
  const input = document.querySelector('input[type="file"]');
  if (!(input instanceof HTMLInputElement)) {
    throw new Error("file input not found");
  }
  const file = new File([new Uint8Array([1, 2, 3])], "manual.pdf", {
    type: "application/pdf",
  });
  await user.upload(input, file);
}

describe("UploadLibraryScreen (FR-001 dedup)", () => {
  it("opens the existing document when an upload is deduplicated", async () => {
    const onOpenDocument = vi.fn();
    const getDocument = vi.fn().mockResolvedValue(EXISTING_DOC);
    const client = fakeClient({ getDocument });

    render(<UploadLibraryScreen client={client} onOpenDocument={onOpenDocument} />);
    await screen.findByRole("button", { name: /browse files/i });

    await uploadAPdf();

    await waitFor(() => {
      expect(onOpenDocument).toHaveBeenCalledWith(EXISTING_DOC);
    });
    expect(getDocument).toHaveBeenCalledWith(EXISTING_DOC.doc_id);
  });
});
