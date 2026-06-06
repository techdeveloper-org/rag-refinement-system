# Design Spec v2 Notes - Phase 4 Reconciliation (in-place design binding rules)

<!-- Phase 4 Full-Stack Reconciliation (Mode A) | ui-ux-designer | 2026-06-06 -->

This file is an **additive addendum** to the Phase-3 design. The Phase-3 design
(`wireframes/`, `tokens_css.css`, `component_library.md`, `screen_inventory.md`,
`accessibility_report.json`, `design_verdict.json`) is **unchanged and stands**: no
wireframe, token, APCA value, or screen was altered during Phase 4. This addendum
records only the two **design-side binding rules** UI/UX applied in-session to close
the cross-domain conflicts GRC-002 and GRC-003 (the architecture-side note for the
CRITICAL GRC-001 is in `hld_v3.md §R1`).

## D1 - ConfidenceMeter scalar reduction over routing.confidence[] (resolves GRC-002)

**Problem.** `component_library.md` ConfidenceMeter shows one level (HIGH/MED/LOW) and
one numeric value (`aria-valuenow={value}`), but `AnswerFinalEvent.routing.confidence[]`
is an **array** (one score per selected section). The scalar source was unspecified.

**Binding rule.**
- Displayed scalar = `max(routing.confidence[])` (the routing decision's strongest
  signal). `aria-valuenow = max(confidence[])`, `aria-valuemin = 0`, `aria-valuemax = 1`,
  `aria-valuetext = "{LEVEL}, {value}"`.
- Level via PRD 8.3 thresholds on that scalar: `>= 0.70` HIGH (`conf-high`),
  `0.50-0.69` MEDIUM (`conf-med`), `< 0.50` LOW (`conf-low`).
- If `routing.fallback == true` OR `routing.confidence[]` is empty -> render the
  **Fallback** variant (not a numeric meter), consistent with FallbackBanner.
- Level is conveyed by label text + numeric value + bar + icon (not color alone),
  preserving WCAG 1.4.1 from `accessibility_report.json`. No token change; the existing
  `conf-high`/`conf-med`/`conf-low`/`conf-track` bindings and APCA Lc values are reused
  as-is.

## D2 - Ingest badge enum mapping (resolves GRC-003)

**Problem.** UploadDropzone/DocumentCard badge variants were named
"Indexed / Pseudo(B) / FallbackOnly(C)", but the contract enum
`IngestResponse.ingest_status` is `[indexed, fallback_only, ephemeral]` (no separate
"Pseudo(B)"; Scenarios A and B are both `indexed`), and the library card badge derives
from `Document.fallback_only` (boolean), not the enum.

**Binding rule.**
- UploadDropzone post-ingest badge maps from `IngestResponse.ingest_status`:
  `indexed` -> "Indexed", `fallback_only` -> "Fallback-only", `ephemeral` -> "Ephemeral".
- The "Pseudo(B)" label is dropped from the user-facing badge - it is an internal
  ingestion detail (Scenario B is `indexed` with a non-native pseudo-TOC) and is not
  contract-visible.
- DocumentCard library badge maps from `Document.fallback_only`:
  `false` -> "Indexed" (`success`/`primary` token), `true` -> "Fallback-only"
  (`fallback` token).
- `Dedup` state still derives from `IngestResponse.deduplicated == true`.
- Token bindings unchanged (`success` / `primary` / `fallback`).

## Re-confirmed (no change needed)

- **CitationCard** binds `AnswerFinalEvent.citations[]` (`section_title`, `page_start`,
  `page_end`); "Jump to page" uses `page_start`. `section_id` is optional and not required
  for rendering. Consistent as designed.
- **ExplainabilityPanel** title/page-range now resolved via the client-side TOC join
  defined in `hld_v3.md §R1` (architecture-side). The Phase-3 component spec needs no
  visual change; only its data source is clarified.
- **ChatStream / FallbackBanner / TocSidebar / DocumentLibrary** bindings verified
  consistent in `reconciliation_matrix.md`; no design change.

**Net design change:** two consumer-side binding rules (D1, D2). All Phase-3 wireframes,
tokens, and APCA values stand unchanged.
