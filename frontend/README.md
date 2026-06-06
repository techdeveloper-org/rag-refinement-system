# RAG Refinement System - Personal Tool SPA

## Overview

Vite + React + TypeScript (strict) single-page app for the personal/developer
tool surface of the RAG Refinement System (STORY-012, ADR-9). It uploads PDFs,
browses the document library, views extracted TOCs, and streams cited answers
with interpretable routing.

The three core differentiators bind to real API fields from
`docs/phase-1-api-contracts/openapi.yaml`:

- **CitationCard** (FR-008) renders `AnswerFinalEvent.citations[]`
  `{ section_title, page_start, page_end }`.
- **ConfidenceMeter** (FR-011) shows `max(routing.confidence[])` (GRC-002) by
  label + numeral + bar + icon, not color alone.
- **ExplainabilityPanel** (FR-012) joins index-aligned `routing.sections[]` x
  `routing.confidence[]` to the loaded `TocResponse.toc[]` via `section_id`
  (GRC-001) to resolve titles and page ranges, listing selected and rejected
  sections.

## Prerequisites / Requirements

- Node.js 20+ and npm 10+

## Installation / Setup

```bash
cd frontend
npm install
```

Set the API base URL (defaults to `http://localhost:8000`):

```bash
# .env.local
VITE_API_BASE_URL=http://localhost:8000
```

The JWT bearer token (ADR-7) is read from `sessionStorage` under
`rag_refinement_jwt`, populated by the external OAuth2 authorization-code flow.
No secrets are hardcoded.

## Usage

```bash
npm run dev        # start the dev server
npm run build      # tsc --strict type-check + production build
npm run test       # run the vitest suite
npm run lint       # eslint (no-explicit-any enforced)
```

## Architecture

- `src/api/` - typed client (`client.ts`), SSE answer consumer (`sse.ts`),
  RFC-7807 error handling (`errors.ts`), and contract types (`types.ts`)
  mirroring the OpenAPI schemas.
- `src/domain/` - pure binding logic: confidence reduction (GRC-002) and the
  explainability TOC-join (GRC-001).
- `src/components/` - the 18 + Toast components from `component_library.md`.
- `src/screens/` - UploadLibrary, DocumentView, Chat.
- `src/styles/tokens.css` - Phase 3 design tokens imported verbatim; mapped into
  Tailwind via `tailwind.config.js` (the design system is not recreated).

## Contributing

File ownership for this story is `frontend/` only. Bind components to real API
fields from `openapi.yaml`; do not invent response shapes. TypeScript strict
mode and the no-`any` rule are enforced in CI.
