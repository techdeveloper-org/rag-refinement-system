# Screen Inventory - FR -> Screen -> Component Traceability

<!-- Phase 3 Standard Path | ui-ux-designer | 2026-06-06 | Mode A (greenfield) -->

Scope: the **Personal/Developer Tool** web SPA (PRD Section 7, Angle 1; ADR-9).
Enterprise-API-only FRs (routing-only `/v1/route`, no UI) are listed in the
"Non-UI / backend-only" table for completeness and are intentionally out of the
personal-tool screen set.

Platform: Web (all screens). Reflow: TocSidebar collapses to a drawer < 768px.

## Personal-tool UI FRs -> Screens

| FR | Description (user-facing) | Screen(s) | Key components | API field(s) rendered |
|----|---------------------------|-----------|----------------|------------------------|
| FR-001 | Upload a PDF and ingest it | UploadLibrary | UploadDropzone | `POST /v1/documents` IngestRequest -> IngestResponse |
| FR-002 | See the extracted / pseudo TOC | DocumentView | TocSidebar, TocEntry | `GET /v1/documents/{id}/toc` TocResponse.toc[] |
| FR-003 | Navigate the Document->Section hierarchy | DocumentView | TocSidebar (tree), TocEntry (level) | TocEntry.level / page_start / page_end |
| FR-007 | Ask questions in a chat interface | Chat, EmptyLoadingError | ChatStream, ChatComposer, MessageBubble | `POST /v1/answer` AnswerRequest.query |
| FR-008 | See source citations (section + page) | Chat, FallbackIndicator | CitationCard | AnswerFinalEvent.citations[] {section_title, page_start, page_end} |
| FR-009 | Be told when the system fell back to full-doc | Chat, FallbackIndicator, DocumentView | FallbackBanner, ConfidenceMeter (Low) | routing.fallback / TocResponse.fallback_only |
| FR-011 | See the routing-confidence value | Chat, FallbackIndicator | ConfidenceMeter | AnswerFinalEvent.routing.confidence[] |
| FR-012 | See "why did you look here?" explanation | Chat, FallbackIndicator | ExplainabilityPanel | routing.rationale + routing.sections[] + routing.confidence[] |
| FR-018 | Watch the answer stream token-by-token | Chat, EmptyLoadingError | ChatStream, MessageBubble, StreamingIndicator | SSE TokenEvent.token -> AnswerFinalEvent.answer |
| FR-024 | Browse / manage a document library | UploadLibrary | DocumentLibrary, DocumentCard | `GET /v1/documents` DocumentListResponse |
| FR-025 | Erase a document (DPDP) from the library | UploadLibrary | DocumentCard (Delete -> confirm) | `DELETE /v1/documents/{id}` ErasureReceipt |
| FR-026 | Export the data held for a document (DPDP) | UploadLibrary | DocumentCard ("Export data" menu) | `GET /v1/documents/{id}/data` DataAccessExport |
| FR-027 | Choose no-retention (ephemeral) processing | UploadLibrary | UploadDropzone (checkbox) | IngestRequest.no_retention / AnswerRequest.no_retention |
| FR-028 | Choose data-residency region | UploadLibrary | UploadDropzone (select) | IngestRequest.residency_region |
| FR-016 | Optionally request reranking | (deferred control) | ChatComposer (advanced toggle, P1) | AnswerRequest.rerank |
| NFR-010 | See structured (RFC-7807) errors | EmptyLoadingError | ErrorState, Toast | Problem{code, detail} |
| NFR-011 | Every answer is explainable | Chat, FallbackIndicator | ConfidenceMeter + ExplainabilityPanel + CitationCard | routing{} + citations[] |
| NFR-013 | Graceful degradation is visible | EmptyLoadingError, FallbackIndicator | DegradedBanner, FallbackBanner | 503 SERVICE_UNAVAILABLE / routing.fallback |

## Screens (6 total)

| # | Screen | Wireframe file | Primary FRs |
|---|--------|----------------|-------------|
| 1 | UploadLibrary | wireframes/UploadLibrary.md | FR-001, FR-024, FR-025, FR-026, FR-027, FR-028 |
| 2 | DocumentView | wireframes/DocumentView.md | FR-002, FR-003, FR-009 (structural) |
| 3 | Chat | wireframes/Chat.md | FR-007, FR-008, FR-011, FR-012, FR-018 |
| 4 | EmptyLoadingError | wireframes/EmptyLoadingError.md | FR-007, FR-018, NFR-010, NFR-013 |
| 5 | FallbackIndicator | wireframes/FallbackIndicator.md | FR-009, FR-011, FR-012 |
| 6 | (Auth) Login/OAuth | handled by OAuth2 provider (ADR-7) | FR-007 auth precondition |

> Screen 6 (Login) is delegated to the OAuth2 authorization-code flow (ADR-7,
> openapi.yaml `securitySchemes.oauth2`). It is an external provider redirect,
> not a custom-designed screen, so it carries no bespoke wireframe in this set.
> Recorded here for completeness; not counted among the 5 designed screens.

## Non-UI / backend-only FRs (no personal-tool screen by design)

| FR | Why no personal-tool screen |
|----|------------------------------|
| FR-004, FR-005, FR-006 | Internal pipeline (embed/route/retrieve); surfaced only via answer + explainability |
| FR-010 | `/v1/route` is the routing-only **enterprise API** (no UI) |
| FR-013, FR-015 | Hybrid search / query rewrite - internal strategy, no dedicated screen |
| FR-014 | Multi-document routing is enterprise routing-only for MVP (advisory ADV-006) |
| FR-017 | OCR is an ingestion option (UploadDropzone `ocr` flag), not a screen |
| FR-019, FR-020, FR-021, FR-022, FR-023 | P2 - feedback/dashboard/SDK/fine-tune/multilingual (post-MVP; out of this design set) |
| FR-029 | x-pii flagging is a schema/data concern surfaced inside FR-026 export, not a standalone screen |

## Coverage assertion
Every personal-tool-facing FR (FR-001, 002, 003, 007, 008, 009, 011, 012, 016, 018, 024, 025, 026, 027, 028) maps to at least one screen and at least one component. The 3 core differentiators (FR-008 citations, FR-011 confidence, FR-012 explainability) each bind to a real `AnswerFinalEvent`/`routing` field in `openapi.yaml`. No screen references an FR that does not exist in the PRD.
