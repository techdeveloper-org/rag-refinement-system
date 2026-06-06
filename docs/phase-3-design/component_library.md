# Component Library - RAG Refinement System (Personal Tool)

<!-- Phase 3 Standard Path | ui-ux-designer | 2026-06-06 | React + Tailwind + Vite (ADR-9) -->

Each component maps to (a) the screens it appears on, (b) the design tokens it binds,
and (c) the **real API contract field(s)** it renders (per
`docs/phase-1-api-contracts/openapi.yaml`). No response shape is invented.

Threshold note: confidence levels follow PRD 8.3 (>=0.70 high, 0.50-0.69 medium, <0.50 low).

---

## Core differentiator components

### CitationCard  (FR-008)
- **Screens:** Chat, FallbackIndicator
- **Renders API field:** `AnswerFinalEvent.citations[]` = `Citation{ section_title, page_start, page_end }` (optional `section_id`)
- **Variants:** Default, Hover, Focused, NoCitations (fallback - shows "No section citations - full-doc")
- **Layout:** horizontal; book icon + title + page-range + "Jump to page {page_start}" action
- **Padding:** 16px (--spacing-md)
- **Token bindings:** bg `surface-alt`; title `text-primary`; page-range `text-secondary`; ref-number chip `primary`; hover `elevation-2`; r `--radius-md`
- **A11y:** "Jump to page N" is a button/link; `aria-label="Citation: {section_title}, pages {page_start} to {page_end}"`

### ConfidenceMeter  (FR-011)
- **Screens:** Chat, FallbackIndicator
- **Renders API field:** `AnswerFinalEvent.routing.confidence[]` (+ `routing.fallback` to flip styling)
- **Variants:** High (>=0.7), Medium (0.5-0.69), Low (<0.5), Fallback, Loading (skeleton)
- **Layout:** label ("HIGH"/"MEDIUM"/"LOW") + numeric value + horizontal fill bar + level icon
- **Padding:** 12px 16px
- **Token bindings:** fill `conf-high` / `conf-med` / `conf-low`; track `conf-track`; label `text-primary`; r `--radius-full`
- **A11y:** `role="meter"`, `aria-valuemin=0`, `aria-valuemax=1`, `aria-valuenow={value}`, `aria-valuetext="HIGH, 0.94"`; level shown by label+icon+bar, not color alone (WCAG 1.4.1)

### ExplainabilityPanel  (FR-012 - "why did you look here?")
- **Screens:** Chat, FallbackIndicator
- **Renders API field:** `AnswerFinalEvent.routing.rationale` (prose) + `routing.sections[]` (section ids) + `routing.confidence[]` (per-section score)
- **Variants:** Collapsed, Expanded, FallbackRationale, Loading
- **Layout:** disclosure header + body (rationale paragraph + considered-sections list incl. rejected ones with scores)
- **Padding:** 16px (--spacing-md); panel r `--radius-lg`
- **Token bindings:** bg `surface-sunken`; rationale text `text-primary`; section meta `text-secondary`; chevron `primary`
- **A11y:** `button[aria-expanded]` controls `region[aria-labelledby]`; Enter/Space toggles

---

## Document & ingestion components

### UploadDropzone  (FR-001, FR-027, FR-028)
- **Screens:** UploadLibrary
- **Renders API field:** posts `IngestRequest{ file, title?, domain?, no_retention, residency_region, ocr? }` -> `POST /v1/documents`; reads `IngestResponse{ doc_id, toc, ingest_status, deduplicated }`
- **Variants:** Idle, DragOver, Uploading (progress), Success, Dedup, FallbackOnly, Error (413/415)
- **Layout:** vertical; icon + prompt + "Browse files" + no-retention checkbox + residency select
- **Padding:** 24px (--spacing-lg)
- **Token bindings:** border `border` (dashed) -> `primary` (DragOver); bg `surface-alt`; r `--radius-md`; progress fill `primary`
- **A11y:** labelled button-region; Enter/Space opens file picker; progress `aria-live="polite"` + `aria-busy`

### DocumentLibrary + DocumentCard  (FR-024)
- **Screens:** UploadLibrary
- **Renders API field:** `GET /v1/documents` -> `DocumentListResponse{ data[Document], pagination }`; card menu actions call `DELETE /v1/documents/{id}` (`ErasureReceipt`) and `GET /v1/documents/{id}/data` (`DataAccessExport`)
- **Variants (Library):** Populated, Empty, Loading (skeleton grid), Paginated
- **Variants (Card):** Default, Hover, Focused; ingest badge Indexed / Pseudo(B) / FallbackOnly(C); menu open
- **Layout:** responsive card grid; card = title + meta (pages/domain/TOC count) + Open + "..." menu
- **Padding:** card 16px (--spacing-md)
- **Token bindings:** card bg `surface-alt`, `elevation-1`; title `text-primary`; meta `text-secondary`; badge `success`/`primary`/`fallback`; delete (in confirm) `error`; r `--radius-md`
- **A11y:** card grid arrow-navigable; "..." is `aria-haspopup="menu"`; delete confirm traps focus, Esc cancels

### TocSidebar + TocEntry  (FR-002, FR-003)
- **Screens:** DocumentView (also drives section context for Chat)
- **Renders API field:** `GET /v1/documents/{id}/toc` -> `TocResponse{ document_id, fallback_only, toc[TocEntry{ section_id, level, title, page_start, page_end, summary }] }`
- **Variants (Sidebar):** Structured (A/B), EmptyFallback (C), Loading, Drawer (mobile)
- **Variants (Entry):** Default, Hover, Selected, Expanded, Collapsed; indent by `level`
- **Layout:** vertical tree; entry = title + page-range; chevron for entries with children
- **Padding:** entry 8px 16px; indent 16px per level
- **Token bindings:** bg `surface-alt`; text `text-primary`; selected left-border + tint `primary`; page-range `text-secondary`
- **A11y:** `role="tree"`/`treeitem`, `aria-level`, `aria-expanded`, `aria-current`; arrow-key tree nav

---

## Chat & feedback components

### ChatStream + MessageBubble  (FR-007, FR-018)
- **Screens:** Chat
- **Renders API field:** user bubble = `AnswerRequest.query`; assistant bubble = `TokenEvent.token` (streamed) -> `AnswerFinalEvent.answer`
- **Variants (Stream):** Idle, Streaming, Complete, Error
- **Variants (Bubble):** User, AssistantStreaming (caret), AssistantComplete
- **Layout:** stacked message list; user right-aligned, assistant left-aligned; max-width `--layout-chat-max-width`
- **Padding:** bubble 16px (--spacing-md)
- **Token bindings:** user bg `primary` text `text-on-primary`; assistant bg `surface-alt` text `text-primary`; caret `primary`; r `--radius-md`
- **A11y:** assistant region `aria-live="polite"` (announce tokens, no focus steal)

### ChatComposer  (FR-007)
- **Screens:** Chat
- **Renders API field:** posts `AnswerRequest{ document_id, query }` -> `POST /v1/answer`
- **Variants:** Empty, Typing, Sending, Disabled
- **Layout:** sticky bottom; textarea + Send button
- **Padding:** 12px 16px
- **Token bindings:** textarea border `border` -> `primary` (focus); Send bg `primary` text `text-on-primary`; r `--radius-md`
- **A11y:** labelled textarea; Ctrl/Cmd+Enter submits; Send reachable by Tab

### FallbackBanner  (FR-009)
- **Screens:** Chat, FallbackIndicator, DocumentView (structural)
- **Renders API field:** `AnswerFinalEvent.routing.fallback` (query-time) / `TocResponse.fallback_only` (structural)
- **Variants:** QueryTimeFallback, StructuralFallback (hidden when fallback=false)
- **Layout:** full-width banner; icon + message + optional "Why?" link
- **Padding:** 16px (--spacing-md)
- **Token bindings:** bg `fallback`; text `text-on-primary`; r `--radius-md`
- **A11y:** `role="alert"`; conveys state via icon+text+color (not color alone)

---

## Shared / scaffolding components

### AppHeader
- **Screens:** all
- **Renders API field:** active document title from `Document.title` (DocumentView/Chat)
- **Variants:** Default, WithDocumentContext
- **Token bindings:** bg `surface`; border-bottom `border`; nav text `text-primary`; active `primary`
- **A11y:** first Tab is a "Skip to content" link

### Button
- **Screens:** all
- **Renders API field:** n/a (action trigger)
- **Variants:** Primary (Default/Hover/Press/Disabled/Loading), Secondary, Ghost, Destructive
- **Padding:** 12px 24px
- **Token bindings:** Primary bg `primary` -> `primary-dark` (hover) text `text-on-primary`; Destructive `error`; r `--radius-md`; focus ring `focus-ring`
- **A11y:** native `button`; visible focus; min target 44px

### EmptyState / LoadingSkeleton / StreamingIndicator / ErrorState / Toast
- **Screens:** all (see EmptyLoadingError.md)
- **Renders API field:** ErrorState/Toast bind `Problem{ code, detail }` (RFC-7807); StreamingIndicator binds SSE lifecycle (FR-018); EmptyState shown on `DocumentListResponse.data=[]`
- **Variants:** EmptyState (NoDocuments/NoMessages); LoadingSkeleton (Card/Bar/Bubble); StreamingIndicator (Routing/Retrieving/Streaming); ErrorState (Blocking 4xx / MidStream / Degraded 503); Toast (Success/Info/Warning/Error)
- **Token bindings:** Empty heading `text-primary` body `text-secondary` CTA `primary`; Error `error`; Degraded `warning`; skeleton shimmer over `surface-alt`
- **A11y:** loading `aria-busy`+`aria-live=polite`; errors `role="alert"`; degraded `role="status"`; focus moves to retry on blocking error

---

## HLD UI-facing component coverage check

| HLD component (UI-facing) | Covered by |
|---------------------------|-----------|
| Personal Tool SPA (HLD 3.2) | all components |
| `/v1/answer` SSE answer + final event (HLD 7.3) | ChatStream, MessageBubble, CitationCard, ConfidenceMeter, ExplainabilityPanel, FallbackBanner |
| Router output `rationale`/`sections`/`confidence` (HLD 7.1) | ExplainabilityPanel, ConfidenceMeter |
| TOC / sections page-range authority (HLD 4.2, 7.5) | TocSidebar, TocEntry, CitationCard |
| Upload / ingestion (HLD 3.1) | UploadDropzone |
| Document management + DPDP erasure/access (HLD 7.4) | DocumentLibrary, DocumentCard (Delete -> erasure, menu -> data export) |
| Fallback branch (HLD 3.2, OAQ-6) | FallbackBanner, ConfidenceMeter (Low), FallbackIndicator screen |
| RFC-7807 errors (HLD 7, NFR-010) | ErrorState, Toast |

Total components: **18** (CitationCard, ConfidenceMeter, ExplainabilityPanel, UploadDropzone, DocumentLibrary, DocumentCard, TocSidebar, TocEntry, ChatStream, MessageBubble, ChatComposer, FallbackBanner, AppHeader, Button, EmptyState, LoadingSkeleton, StreamingIndicator, ErrorState) plus Toast.
