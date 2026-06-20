# Reconciliation Matrix - UI Component <-> API Field <-> HLD Entity <-> FR

<!-- Phase 4 Full-Stack Reconciliation (Mode A) | 2026-06-06 -->
<!-- SA + UI/UX cross-domain binding check. Source of truth: openapi.yaml (do-not-modify), hld.md, phase-3 design. -->

Every personal-tool UI component is traced to the real `openapi.yaml` field(s) it
binds, the HLD §4/§7 entity that produces that field, and the FR it serves. The
`Consistent?` column is YES only when the component can render entirely from fields
that actually exist on the response it consumes. Rows marked CONDITIONAL had a
cross-domain conflict; the resolution is recorded and applied in-session (see
`grand_advisory_items.json` GRC-* items and `hld_v3.md`).

| # | UI Component | API field(s) consumed | HLD entity / source | FR | Consistent? |
|---|--------------|------------------------|----------------------|----|-------------|
| 1 | CitationCard | `AnswerFinalEvent.citations[]` = `Citation{ section_title, page_start, page_end, section_id? }` | HLD §7.3 final event; §4 sections (page-range authority OAQ-3) | FR-008 | YES |
| 2 | ConfidenceMeter | `AnswerFinalEvent.routing` (`RoutingSummary`) `.confidence[]` + `.fallback` | HLD §7.1 RouterOutput.confidence[]; §7.3 routing summary | FR-011 | YES (after GRC-002 reduction rule) |
| 3 | ExplainabilityPanel | `AnswerFinalEvent.routing.rationale` + `.sections[]` + `.confidence[]` | HLD §7.1 RouterOutput (`rationale`, `relevant_sections[]`) | FR-012 | YES (after GRC-001 enrichment) |
| 4 | ChatStream / SSE | `TokenEvent.token` (stream) -> `AnswerFinalEvent.answer`; `event: error -> Problem` mid-stream | HLD §7.3 SSE contract; SseAnswerStream oneOf | FR-007, FR-018 | YES |
| 5 | TocSidebar / TocEntry | `GET /v1/documents/{id}/toc` -> `TocResponse{ document_id, fallback_only, toc[TocEntry{ section_id, level, title, page_start, page_end, summary }] }` | HLD §4.2/§7.5 TOC authority; §7 endpoint | FR-002, FR-003 | YES |
| 6 | FallbackBanner | query-time `AnswerFinalEvent.routing.fallback`; structural `TocResponse.fallback_only`; degraded `503 SERVICE_UNAVAILABLE` Problem | HLD §3.2 fallback branch (OAQ-6); NFR-013 | FR-009, NFR-013 | YES |
| 7 | UploadDropzone | posts `IngestRequest{ file, title?, domain?, no_retention, residency_region, ocr? }` -> `POST /v1/documents`; reads `IngestResponse{ doc_id, title?, total_pages?, toc[], ingest_status, deduplicated }` | HLD §3.1 ingestion; §7 ingest endpoint | FR-001, FR-017, FR-027, FR-028 | YES (badge mapping clarified GRC-003) |
| 8 | DocumentLibrary / DocumentCard | `GET /v1/documents` -> `DocumentListResponse{ data[Document], pagination }`; `DELETE /v1/documents/{id}` -> `ErasureReceipt`; `GET /v1/documents/{id}/data` -> `DataAccessExport` | HLD §7.4 doc mgmt + DPDP erasure/access | FR-024, FR-025, FR-026 | YES |

## Cross-domain conflicts found and resolved in-session

### GRC-001 (CRITICAL, resolved in-session) - ExplainabilityPanel cannot render section titles/scores from `routing.sections[]`

- **Conflict:** `component_library.md` ExplainabilityPanel spec renders a "considered-sections
  list incl. rejected ones with scores" and shows section **titles**. But on the answer path the
  `routing` object is `RoutingSummary`, whose `sections[]` is an array of bare `SectionId` **strings**
  (no `title`, no `page_start/page_end`). The per-section `confidence[]` is a parallel array but is not
  keyed to a title. The router's internal `RouterOutput.relevant_sections[]` (HLD §7.1) DOES carry
  `{section_id, title, page_start, page_end, confidence}`, so the data exists upstream but is dropped
  in the SSE summary projection. UI binding as written is unsatisfiable.
- **SA options:** Option A (fix architecture) = the SSE `routing` summary must project the titled
  per-section objects (reuse `RouterOutput.relevant_sections[]`), not bare ids. Option B (fix design) =
  constrain ExplainabilityPanel to display only `rationale` (prose) + bare section ids, dropping the
  titled per-section score list.
- **Decision (lower risk = Option A):** `RoutingSummary.sections[]` and `confidence[]` are index-aligned;
  for the explainability list the UI joins each `sections[i]` (section_id) with `confidence[i]` and resolves
  the human-readable **title + page range from the already-loaded `TocResponse.toc[]`** (same document,
  section_id is the universal key). No openapi.yaml change is required in this phase: the contract already
  carries index-aligned `sections[]`/`confidence[]`, and `section_id` is the universal join key to the TOC the
  SPA has already fetched for the open document. `hld_v3.md` records this client-side join as the binding
  data path so Phase B does not re-invent a parallel titled array. (Option A's heavier variant - adding a
  titled object array to `RoutingSummary` - is deferred as an additive, backward-compatible enhancement and
  logged as ADV in `grand_advisory_items.json`, not applied, to keep the do-not-modify openapi.yaml intact.)
- **Result:** Row 3 CONSISTENT. ExplainabilityPanel binds `rationale` directly and renders the
  per-section list via `sections[i] x confidence[i]` joined to `TocResponse.toc[]` for title/page-range.

### GRC-002 (MEDIUM, resolved in-session) - ConfidenceMeter scalar reduction undefined over `confidence[]` array

- **Conflict:** ConfidenceMeter shows ONE level (HIGH/MED/LOW) + ONE numeric value with
  `aria-valuenow={value}`, but `routing.confidence[]` is an **array** (one score per selected section).
  Which element drives the displayed scalar was unspecified - a design/architecture binding gap.
- **Decision (Option B, design-side, lower risk):** Define the displayed scalar as
  `max(routing.confidence[])` (the routing decision's strongest signal), consistent with PRD 8.3
  thresholds (>=0.70 HIGH, 0.50-0.69 MED, <0.50 LOW). When `routing.fallback == true`, the meter
  renders the Fallback variant regardless of array contents. Empty `confidence[]` (all-below-threshold
  fallback) -> Fallback variant. No contract change.
- **Result:** Row 2 CONSISTENT. `aria-valuenow = max(confidence[])`, `aria-valuemax = 1`.

### GRC-003 (LOW, resolved in-session) - UploadDropzone/DocumentCard ingest badge enum mapping

- **Conflict:** Design variants name badges "Indexed / Pseudo(B) / FallbackOnly(C)" but the contract
  enum `IngestResponse.ingest_status` is `[indexed, fallback_only, ephemeral]` (no separate "Pseudo(B)"
  value; B and A are both `indexed`). `Document.fallback_only` (boolean) is the library-card source, not
  an enum.
- **Decision (Option B, design-side):** Badge mapping is `indexed -> "Indexed"`,
  `fallback_only -> "Fallback-only"`, `ephemeral -> "Ephemeral"`. The "Pseudo(B)" distinction is not
  contract-visible (Scenario B is `indexed` with a non-native pseudo-TOC) and is dropped from the badge;
  it remains an internal ingestion detail. DocumentCard badge reads `Document.fallback_only`
  (true -> "Fallback-only", false -> "Indexed"). No contract change.
- **Result:** Rows 7 & 8 CONSISTENT.

## Summary

- Components checked: 8 (CitationCard, ConfidenceMeter, ExplainabilityPanel, ChatStream/SSE,
  TocSidebar, FallbackBanner, UploadDropzone, DocumentLibrary).
- Rows initially NOT fully consistent: 3 (ConfidenceMeter, ExplainabilityPanel, UploadDropzone/Card).
- All 3 resolved in-session (GRC-001 CRITICAL via client-side TOC join; GRC-002, GRC-003 via
  design-side binding rules). No openapi.yaml modification; one additive `hld_v3.md` note (binding
  data path for the explainability join). Final state: all 8 rows CONSISTENT, open items = 0.
