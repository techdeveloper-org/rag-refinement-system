# HLD v3 - Phase 4 Reconciliation Addendum (in-place binding notes)

<!-- Phase 4 Full-Stack Reconciliation (Mode A) | solution-architect | 2026-06-06 -->

This file is an **additive addendum** to `docs/phase-1-architecture/hld.md`. The
base HLD (§1-§8) is **unchanged and stands**: no structural, data-model, contract,
or fault-tolerance change was required during Phase 4 reconciliation. The
`openapi.yaml` (Phase 1.5) is **not modified** (do-not-modify scope). This addendum
records the single architecture<->design binding clarification SA applied in-session
to resolve the one CRITICAL reconciliation finding (GRC-001), plus pointers for the
two design-side resolutions (GRC-002, GRC-003) recorded in `design_spec_v2_notes.md`.

## §R1 - Explainability data path: client-side TOC join (resolves GRC-001)

**Context.** The personal-tool `ExplainabilityPanel` (FR-012, NFR-011) must show, per
the Phase-3 `component_library.md`, the rationale prose plus a list of considered
sections **with human-readable titles, page ranges, and per-section scores** (including
rejected sections).

**Architectural fact.** The `/v1/answer` SSE final event (`AnswerFinalEvent`) carries
`routing` as `RoutingSummary`:

```
RoutingSummary = { sections: [SectionId], confidence: [float], fallback: bool, rationale: string }
```

`sections[]` is an array of bare `section_id` strings and `confidence[]` is an
index-aligned array of floats. The richer titled per-section objects exist only on the
in-process `RouterOutput.relevant_sections[]` (HLD §7.1) and are intentionally **not**
re-serialized into the SSE summary (the summary stays compact).

**Binding rule (the resolution).** The SPA already fetches `TocResponse.toc[]` for the
open document (TocSidebar, FR-002/003) and `section_id` is the **universal join key**
(HLD §4, openapi.yaml `SectionId`). Therefore the ExplainabilityPanel renders the
considered-sections list by:

1. binding `routing.rationale` directly (prose);
2. for each index `i` in `routing.sections[]`: pairing `routing.sections[i]`
   (a `section_id`) with `routing.confidence[i]` (its score);
3. resolving the display `title` + `page_start`/`page_end` by looking that
   `section_id` up in the already-loaded `TocResponse.toc[]` (same document).

No new API field and no `openapi.yaml` change is needed: the index-aligned
`sections[]`/`confidence[]` arrays plus the TOC the SPA already holds are sufficient.
Within MVP scope the answer path is single-document (`AnswerRequest.document_id`, see
ADV-006), so every `section_id` in `routing.sections[]` is guaranteed to resolve in the
loaded TOC.

**Phase B obligation.** `react-engineer` MUST implement this client-side join rather
than expecting a titled array on the wire. If `routing.fallback == true` (no scoped
sections), the panel shows the FallbackRationale variant (rationale only, no section
list). A future multi-document answer path would instead require the deferred additive
`considered_sections[]` object array (GRC-001-DEFER in `grand_advisory_items.json`).

## §R2 - Pointers to design-side resolutions (no HLD impact)

- **GRC-002 (ConfidenceMeter scalar):** the displayed confidence scalar is
  `max(routing.confidence[])`, mapped to PRD 8.3 thresholds; Fallback variant when
  `routing.fallback` is true or `confidence[]` is empty. Architecturally a pure
  consumer-side reduction over the existing `confidence[]` array - no HLD/contract
  change. Recorded in `design_spec_v2_notes.md`.
- **GRC-003 (ingest badge enum):** badge labels map to the existing
  `IngestResponse.ingest_status` enum `[indexed, fallback_only, ephemeral]` and
  `Document.fallback_only`. No new enum value; no HLD/contract change. Recorded in
  `design_spec_v2_notes.md`.

## Invariants re-confirmed unchanged

- `section_id` is the universal join/filter key across Document -> Section -> chunk
  (HLD §4, §7; AGREED CONTRACT).
- `/v1/route` is routing-only and never calls the generation LLM (HLD §7.2 invariant).
- `/v1/answer` is SSE: `TokenEvent` stream then a terminal `AnswerFinalEvent`; mid-stream
  failures arrive as `event: error` -> `Problem` (HLD §7.3; AC-ADV-002).
- Fallback contract: `routing.fallback` (query-time) / `TocResponse.fallback_only`
  (structural) / `503 SERVICE_UNAVAILABLE` (dependency-down) - the three fallback
  surfaces the UI's FallbackBanner and ConfidenceMeter Fallback variant must reflect
  (HLD §3.2, OAQ-6; NFR-013).
- All 10 ADRs stand.

**Net HLD change:** one additive binding note (§R1). hld.md §1-§8 require no edit.
