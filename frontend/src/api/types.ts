/**
 * TypeScript types mirroring the RAG Refinement System API contract
 * (`docs/phase-1-api-contracts/openapi.yaml`, OpenAPI 3.1.0).
 *
 * These are a faithful projection of the wire schemas - no response shape is
 * invented. Field names, optionality, and enums match the contract exactly so
 * components bind only to fields that actually exist.
 */

/** Stable document identifier (pattern: `^doc_[A-Za-z0-9]{6,}$`). */
export type DocumentId = string;

/** Universal section identifier - the join/filter key (HLD section 7.5). */
export type SectionId = string;

/** Correlation id for a routing/answer request (NFR-009 tracing). */
export type QueryId = string;

/** Router confidence in [0.0, 1.0] that a section is relevant (PRD 8.3). */
export type Confidence = number;

/** Data-residency region for tenant storage (FR-028). */
export type ResidencyRegion = "IN" | "EU" | "US" | "GLOBAL";

/** Ingestion outcome enum (IngestResponse.ingest_status). */
export type IngestStatus = "indexed" | "fallback_only" | "ephemeral";

/** A [page_start, page_end] inclusive page interval. */
export type PageRange = [number, number];

/** A single table-of-contents entry (TocEntry schema). */
export interface TocEntry {
  section_id: SectionId;
  level: number;
  title: string;
  page_start: number;
  page_end: number;
  summary?: string;
}

/** Document TOC response (`GET /v1/documents/{id}/toc`). */
export interface TocResponse {
  document_id: DocumentId;
  fallback_only: boolean;
  toc: TocEntry[];
}

/** Document metadata (Document schema). */
export interface Document {
  doc_id: DocumentId;
  title?: string;
  total_pages: number;
  domain?: string;
  tenant_id?: string;
  residency_region: ResidencyRegion;
  fallback_only: boolean;
  created_at: string;
}

/** Pagination envelope (Pagination schema). */
export interface Pagination {
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

/** Paginated document list (`GET /v1/documents`). */
export interface DocumentListResponse {
  data: Document[];
  pagination: Pagination;
}

/** Ingest response (`POST /v1/documents`). */
export interface IngestResponse {
  doc_id: DocumentId;
  title?: string;
  total_pages?: number;
  toc: TocEntry[];
  ingest_status: IngestStatus;
  deduplicated: boolean;
}

/** Erasure receipt (`DELETE /v1/documents/{id}`, DPDP right to erasure). */
export interface ErasureReceipt {
  doc_id: DocumentId;
  erased: boolean;
  accepted_at: string;
}

/** A PII field located within a document's stored data (DPDP section 4). */
export interface PiiField {
  field: string;
  location: string;
  category?: string;
}

/** DPDP section 8 access export (`GET /v1/documents/{id}/data`). */
export interface DataAccessExport {
  doc_id: DocumentId;
  generated_at: string;
  document: Document;
  sections: TocEntry[];
  pii_fields: PiiField[];
}

/** A source citation on the answer path (Citation schema). */
export interface Citation {
  section_id?: SectionId;
  section_title: string;
  page_start: number;
  page_end: number;
}

/**
 * Routing summary attached to the terminal answer event (RoutingSummary).
 *
 * `sections[]` and `confidence[]` are index-aligned (GRC-001): `sections[i]`
 * is the bare section id and `confidence[i]` is its score. Titles and page
 * ranges are resolved client-side by joining `sections[i]` to the already
 * loaded `TocResponse.toc[]` via `section_id`.
 */
export interface RoutingSummary {
  sections: SectionId[];
  confidence: Confidence[];
  fallback: boolean;
  rationale?: string;
}

/** SSE `event: token` data payload - an incremental answer fragment. */
export interface TokenEvent {
  query_id?: QueryId;
  token: string;
}

/** SSE `event: final` data payload - the completed cited answer. */
export interface AnswerFinalEvent {
  query_id?: QueryId;
  answer: string;
  citations: Citation[];
  routing: RoutingSummary;
}

/** Request body for `POST /v1/answer`. */
export interface AnswerRequest {
  document_id: DocumentId;
  query: string;
  confidence_threshold?: Confidence;
  max_sections?: number;
  rerank?: boolean;
  no_retention?: boolean;
}

/** Request fields for `POST /v1/documents` (multipart IngestRequest). */
export interface IngestRequestFields {
  title?: string;
  domain?: string;
  no_retention?: boolean;
  residency_region?: ResidencyRegion;
  ocr?: boolean;
}

/** A relevant section on the routing-only path (RelevantSection schema). */
export interface RelevantSection {
  section_id: SectionId;
  document_id?: DocumentId;
  title: string;
  page_start: number;
  page_end: number;
  confidence: Confidence;
}

/** Request body for `POST /v1/route` (routing-only enterprise endpoint). */
export interface RouteRequest {
  document_id?: DocumentId;
  document_ids?: DocumentId[];
  query: string;
  confidence_threshold?: Confidence;
  max_sections?: number;
  rerank?: boolean;
}

/** Routing decision (`POST /v1/route`). */
export interface RouteResponse {
  query_id: QueryId;
  relevant_sections: RelevantSection[];
  page_ranges: PageRange[];
  confidence: Confidence[];
  fallback: boolean;
  routing_time_ms: number;
  rationale?: string;
  estimated_token_reduction?: string;
}

/** RFC 7807 problem detail (application/problem+json). */
export interface Problem {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
  instance?: string;
  query_id?: QueryId;
}

/** A single field-level validation failure (ValidationProblem.errors[]). */
export interface ValidationProblemError {
  field: string;
  message: string;
}

/** RFC 7807 problem extended with field-level validation errors. */
export interface ValidationProblem extends Problem {
  errors?: ValidationProblemError[];
}
