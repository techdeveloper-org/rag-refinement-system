import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { DocumentListResponse, Problem } from "@/api/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ApiClient", () => {
  it("attaches the JWT bearer header on listDocuments", async () => {
    const list: DocumentListResponse = {
      data: [],
      pagination: { page: 1, page_size: 20, total_count: 0, total_pages: 0 },
    };
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(list));
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      getToken: () => "jwt-token",
      fetchImpl,
    });

    const result = await client.listDocuments({ page: 2 });

    expect(result.pagination.page).toBe(1);
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/v1/documents?page=2");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer jwt-token");
  });

  it("throws an ApiError carrying the RFC-7807 problem on a 404", async () => {
    const problem: Problem = {
      type: "https://api/problems/document-not-found",
      title: "Not Found",
      status: 404,
      code: "DOCUMENT_NOT_FOUND",
      detail: "No document with the given id exists.",
    };
    const fetchImpl = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(problem, 404)));
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      getToken: () => null,
      fetchImpl,
    });

    const caught = await client.getDocument("doc_missing").catch((error: unknown) => error);
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({
      problem: { code: "DOCUMENT_NOT_FOUND", status: 404 },
    });
  });

  it("posts multipart form data with the file for ingestDocument", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse(
        { doc_id: "doc_abc123", toc: [], ingest_status: "indexed", deduplicated: false },
        201,
      ),
    );
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      getToken: () => "jwt-token",
      fetchImpl,
    });
    const file = new File(["%PDF-1.7"], "manual.pdf", { type: "application/pdf" });

    const result = await client.ingestDocument(file, { no_retention: true, residency_region: "IN" });

    expect(result.doc_id).toBe("doc_abc123");
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const form = init.body as FormData;
    expect(form.get("no_retention")).toBe("true");
    expect(form.get("residency_region")).toBe("IN");
  });
});
