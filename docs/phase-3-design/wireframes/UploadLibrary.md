# Wireframe: Upload / Library (1280x800 desktop; reflows to 390 mobile)

**FR Coverage:** FR-001 (PDF upload), FR-024 (document library), FR-027 (no-retention toggle), FR-028 (residency)
**Platform:** Web (React + Tailwind + Vite, ADR-9)
**Components:** AppHeader, UploadDropzone, DocumentLibrary, DocumentCard, EmptyState, Toast
**Design tokens:** surface, surface-alt, primary, text-primary, text-secondary, border, success, error
**API binding:** `POST /v1/documents` (multipart IngestRequest -> IngestResponse {doc_id, toc, ingest_status, deduplicated}); `GET /v1/documents` (DocumentListResponse {data[], pagination}); `DELETE /v1/documents/{id}` (ErasureReceipt)

## Layout (populated library)

```
+------------------------------------------------------------------+
| [skip to content]                                                |  (visually hidden until focused)
+------------------------------------------------------------------+
|  [Logo] RAG Refinement      Library  |  Profile (o)              |  AppHeader  h=64  surface / border-bottom: border
+------------------------------------------------------------------+
|                                                                  |  spacing-xl top
|  +------------------------------------------------------------+  |
|  |  [ up-arrow icon ]  Drag a PDF here, or  [ Browse files ]  |  |  UploadDropzone  surface-alt  border: border (dashed)  r=md
|  |  PDF up to 50 MB / 1000 pages.                             |  |  helper: body-sm / text-secondary
|  |  [ ] No-retention mode   Residency: [ GLOBAL v ]          |  |  no_retention + residency_region -> IngestRequest
|  +------------------------------------------------------------+  |
|                                                                  |  spacing-xl
|  Your documents  (12)                       [ Search... ]        |  heading-2 / text-primary
|  ------------------------------------------------------------    |  divider: border-subtle
|  +----------------------+  +----------------------+              |
|  | [PDF] Motor Manual   |  | [PDF] Lease Agreement|              |  DocumentCard  surface-alt  r=md  elevation-1
|  | 200 pages . legal    |  | 48 pages . legal     |              |  title: body / text-primary
|  | TOC: 8 sections      |  | TOC: pseudo (B)      |              |  meta: body-sm / text-secondary
|  | [ Open ]    [ ... ]  |  | [ Open ]    [ ... ]  |              |  ingest_status badge: indexed/fallback_only
|  +----------------------+  +----------------------+              |  [...] menu: Open / Export data / Delete
|  +----------------------+  +----------------------+              |
|  | [PDF] Annual Report  |  | [PDF] Research Paper |              |
|  | 96 pages . finance   |  | 14 pages . research  |              |
|  | TOC: 22 sections     |  | TOC: 5 sections      |              |
|  | [ Open ]    [ ... ]  |  | [ Open ]    [ ... ]  |              |
|  +----------------------+  +----------------------+              |
|                                                                  |
|  < Prev    Page 1 of 3    Next >                                 |  Pagination -> DocumentListResponse.pagination
+------------------------------------------------------------------+
```

## States / variants

| State | Visual | Token binding | API source |
|-------|--------|---------------|------------|
| UploadDropzone Idle | dashed `border`, surface-alt | border: border | - |
| UploadDropzone DragOver | solid `primary` 2px border, primary tint bg | border: primary | - |
| UploadDropzone Uploading | progress bar, "Parsing TOC... 40%" caption | bar: primary on conf-track | (client progress) |
| Upload Success | green toast "Indexed - 8 sections found" | bg: success, text: text-on-primary | IngestResponse.ingest_status=indexed |
| Upload Dedup | info toast "Already in library - opened existing" | bg: primary, text: text-on-primary | IngestResponse.deduplicated=true (200) |
| Upload fallback_only | amber toast "No TOC detected - full-doc mode" | bg: fallback, text: text-on-primary | IngestResponse.ingest_status=fallback_only |
| Upload Error 413/415 | red toast with Problem.detail | bg: error, text: text-on-primary | RFC-7807 Problem |
| DocumentCard ingest badge | "TOC: N sections" (indexed) / "TOC: pseudo (B)" / "Full-doc only (C)" | badge: success / primary / fallback | IngestResponse.toc + ingest_status |
| DocumentCard Delete | confirm dialog "Erase document and all data? (DPDP)" | dialog; destructive btn: error | DELETE -> ErasureReceipt |
| Empty library | EmptyState (see EmptyLoadingError.md) | - | DocumentListResponse.data=[] |

## Accessibility notes (GIGW v3.0)
- UploadDropzone is a labelled `button` region; Enter/Space opens the native file picker (keyboard-equivalent to drag-drop).
- Upload progress region is `aria-live="polite"` + `aria-busy="true"`.
- Each DocumentCard "..." menu is a keyboard-operable menu button (`aria-haspopup="menu"`).
- Delete confirm traps focus inside the dialog; Esc cancels; focus returns to the triggering card.
- No PII shown: card titles use document titles only (DPDP - no document body content rendered in library).
