import { toApiError } from "@/api/errors";
import type {
  DataAccessExport,
  Document,
  DocumentId,
  DocumentListResponse,
  IngestRequestFields,
  IngestResponse,
  ResidencyRegion,
  RouteRequest,
  RouteResponse,
  TocResponse,
} from "@/api/types";

/** Resolves a JWT bearer token for the current personal-tool session. */
export type TokenProvider = () => string | null;

/** Configuration for the typed API client. */
export interface ApiClientConfig {
  baseUrl: string;
  getToken: TokenProvider;
  fetchImpl?: typeof fetch;
}

/** Optional page-based pagination + domain filter for document listing. */
export interface ListDocumentsParams {
  page?: number;
  pageSize?: number;
  domain?: string;
}

const JSON_CONTENT_TYPE = "application/json";

/**
 * Typed HTTP client for the RAG Refinement System personal-tool surface.
 *
 * Wraps `fetch` with JWT bearer auth, JSON (de)serialization, and RFC 7807
 * error translation. The streaming `POST /v1/answer` endpoint is consumed by a
 * dedicated SSE client (see `sse.ts`) and is intentionally not modelled here.
 */
export class ApiClient {
  private readonly baseUrl: string;
  private readonly getToken: TokenProvider;
  private readonly fetchImpl: typeof fetch;

  public constructor(config: ApiClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/u, "");
    this.getToken = config.getToken;
    this.fetchImpl = config.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  /** Build the bearer auth header, omitting it when no token is available. */
  private authHeader(): Record<string, string> {
    const token = this.getToken();
    return token === null ? {} : { Authorization: `Bearer ${token}` };
  }

  /**
   * Issue a JSON request and decode the response, raising an ApiError on any
   * non-2xx status.
   *
   * @param path - Path relative to the configured base URL.
   * @param init - Fetch init overrides (method, body, headers).
   * @returns The decoded JSON body typed as `T`.
   * @throws {ApiError} When the response status is not 2xx or decoding fails.
   */
  private async requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        Accept: JSON_CONTENT_TYPE,
        ...this.authHeader(),
        ...(init.headers ?? {}),
      },
    });

    if (!response.ok) {
      const body = await this.safeParseJson(response);
      throw toApiError(response.status, body);
    }

    return (await response.json()) as T;
  }

  /** Parse a response body as JSON, returning null when the body is not JSON. */
  private async safeParseJson(response: Response): Promise<unknown> {
    try {
      return (await response.json()) as unknown;
    } catch {
      return null;
    }
  }

  /**
   * Upload and ingest a PDF (`POST /v1/documents`).
   *
   * @param file - The PDF file to ingest (application/pdf).
   * @param fields - Optional ingestion fields (title, domain, no_retention, residency_region, ocr).
   * @returns The IngestResponse (201 first-time, 200 idempotent dedup).
   * @throws {ApiError} On 4xx/5xx (413/415 on bad uploads).
   */
  public async ingestDocument(
    file: File,
    fields: IngestRequestFields = {},
  ): Promise<IngestResponse> {
    const form = new FormData();
    form.append("file", file);
    if (fields.title !== undefined) {
      form.append("title", fields.title);
    }
    if (fields.domain !== undefined) {
      form.append("domain", fields.domain);
    }
    if (fields.no_retention !== undefined) {
      form.append("no_retention", String(fields.no_retention));
    }
    if (fields.residency_region !== undefined) {
      form.append("residency_region", fields.residency_region);
    }
    if (fields.ocr !== undefined) {
      form.append("ocr", String(fields.ocr));
    }
    return this.requestJson<IngestResponse>("/v1/documents", {
      method: "POST",
      body: form,
    });
  }

  /** List ingested documents, paginated (`GET /v1/documents`). */
  public async listDocuments(params: ListDocumentsParams = {}): Promise<DocumentListResponse> {
    const query = new URLSearchParams();
    if (params.page !== undefined) {
      query.set("page", String(params.page));
    }
    if (params.pageSize !== undefined) {
      query.set("page_size", String(params.pageSize));
    }
    if (params.domain !== undefined) {
      query.set("domain", params.domain);
    }
    const suffix = query.toString();
    const path = suffix.length > 0 ? `/v1/documents?${suffix}` : "/v1/documents";
    return this.requestJson<DocumentListResponse>(path);
  }

  /** Retrieve metadata for a single document (`GET /v1/documents/{id}`). */
  public async getDocument(id: DocumentId): Promise<Document> {
    return this.requestJson<Document>(`/v1/documents/${encodeURIComponent(id)}`);
  }

  /** Retrieve the extracted/pseudo TOC (`GET /v1/documents/{id}/toc`). */
  public async getDocumentToc(id: DocumentId): Promise<TocResponse> {
    return this.requestJson<TocResponse>(`/v1/documents/${encodeURIComponent(id)}/toc`);
  }

  /** Export the personal data held for a document (`GET /v1/documents/{id}/data`). */
  public async exportDocumentData(id: DocumentId): Promise<DataAccessExport> {
    return this.requestJson<DataAccessExport>(`/v1/documents/${encodeURIComponent(id)}/data`);
  }

  /** Erase a document and all derived data (`DELETE /v1/documents/{id}`). */
  public async deleteDocument(id: DocumentId): Promise<void> {
    await this.requestJson<unknown>(`/v1/documents/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  }

  /** Route a query to relevant sections, routing-only (`POST /v1/route`). */
  public async routeQuery(request: RouteRequest): Promise<RouteResponse> {
    return this.requestJson<RouteResponse>("/v1/route", {
      method: "POST",
      headers: { "Content-Type": JSON_CONTENT_TYPE },
      body: JSON.stringify(request),
    });
  }
}

/** Residency-region options surfaced in the upload form (IngestRequest enum). */
export const RESIDENCY_REGIONS: readonly ResidencyRegion[] = ["GLOBAL", "IN", "EU", "US"];
