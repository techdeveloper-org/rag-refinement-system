# Wireframe: Document View with extracted TOC (1280x800; reflows to drawer on mobile)

**FR Coverage:** FR-002 (TOC extraction A/B/C), FR-003 (3-level hierarchy), FR-024 (document surface)
**Platform:** Web (React + Tailwind + Vite, ADR-9)
**Components:** AppHeader, TocSidebar, TocEntry, DocumentMeta, FallbackBanner (conditional), Button
**Design tokens:** surface, surface-alt, primary, text-primary, text-secondary, border, fallback
**API binding:** `GET /v1/documents/{id}` (Document); `GET /v1/documents/{id}/toc` (TocResponse {document_id, fallback_only, toc[TocEntry{section_id, level, title, page_start, page_end, summary}]})

## Layout (Scenario A/B - structured TOC present)

```
+------------------------------------------------------------------+
|  [Logo] RAG Refinement      Library  |  Profile (o)              |  AppHeader  h=64
+------------------------------------------------------------------+
| TocSidebar  w=280  surface-alt | Document main  surface          |
| (sticky)                       |                                 |
| Contents                       |  Motor Manual                   |  heading-1 / text-primary
| -------------------------       |  200 pages . legal . indexed   |  body-sm / text-secondary
| > 1  Introduction      p1-3    |  ----------------------------   |
| > 2  Installation      p4-20   |                                 |
|   v 3  Operation       p21-60  |  Source: native bookmarks (A)   |  TocResponse.fallback_only=false
|       3.1 Startup      p21-30  |  8 top-level sections, 22 total |  TocEntry count by level
|       3.2 Controls     p31-45  |                                 |
|       3.3 Shutdown     p46-60  |  +---------------------------+  |
| > 4  Maintenance       p61-90  |  |  Ask about this document  |  |  primary CTA -> opens Chat
| > ...                          |  +---------------------------+  |  bg: primary  text: text-on-primary  r=md
| v 8  Warranty & Support p142-148|                                |
|       (selected)               |  Selected: Warranty & Support   |  aria-current section detail
|                                |  Pages 142-148 . Level 1        |  body-sm / text-secondary
+--------------------------------+---------------------------------+
```

TocEntry rows render `title` + `page_start-page_end`; indentation = `level` (L1 chapter, L2 subsection). `section_id` is the stable key (not shown to user). The "Ask about this document" CTA navigates to the Chat screen scoped to this `doc_id`.

## Layout (Scenario C - fallback_only document, no usable structure)

```
+------------------------------------------------------------------+
|  [ ! ]  No table of contents detected. Answers will search the   |  FallbackBanner  bg: fallback  text: text-on-primary
|         whole document (full-doc RAG).                            |  role=alert  TocResponse.fallback_only=true
+------------------------------------------------------------------+
| TocSidebar (empty)             | Document main                   |
| No sections.                   |  Research Notes                 |
| This document had no native    |  14 pages . full-doc only (C)   |
| or detectable headings.        |                                 |
|                                |  +---------------------------+  |
|                                |  |  Ask about this document  |  |
|                                |  +---------------------------+  |
+--------------------------------+---------------------------------+
```

## States / variants

| Component | States | Token binding | API source |
|-----------|--------|---------------|------------|
| TocEntry | Default / Hover / Selected / Expanded / Collapsed | text: text-primary; selected bg: primary tint, left-border: primary | TocEntry.level, .title, .page_start/end |
| TocEntry (L1 vs L2) | indent by level (16px per level) | - | TocEntry.level |
| FallbackBanner | shown only when fallback_only=true | bg: fallback, text: text-on-primary | TocResponse.fallback_only |
| Source label | "native bookmarks (A)" / "pseudo-TOC (B)" / "full-doc only (C)" | badge: success / primary / fallback | TocResponse.fallback_only + section count |
| Ask CTA | Default / Hover / Disabled (while TOC loading) | bg: primary -> primary-dark | - |
| Loading TOC | skeleton rows in sidebar | shimmer over surface-alt | (pending GET /toc) |
| Error loading | inline retry (see EmptyLoadingError.md) | error | RFC-7807 Problem |

## Accessibility notes (GIGW v3.0)
- TocSidebar is an ARIA `tree` (role=tree); each TocEntry is a `treeitem` with `aria-level`, `aria-expanded` (for L1 with children), `aria-current` on the selected entry.
- Up/Down arrows move between entries; Right/Left expand/collapse; Enter selects.
- FallbackBanner is `role="alert"` so screen readers announce the full-doc mode immediately.
- On mobile (<768px) TocSidebar collapses to a drawer toggled by a keyboard-operable "Contents" button; focus moves into the drawer on open, Esc closes.
- No document body text is rendered here (only TOC titles + page numbers) - keeps PII surface minimal (DPDP).
