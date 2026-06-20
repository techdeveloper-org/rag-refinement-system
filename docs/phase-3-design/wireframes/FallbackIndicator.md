# Wireframe: Fallback-mode indicator (low routing confidence)

**FR Coverage:** FR-009 (graceful degradation to full-doc RAG + indicate fallback), FR-011 (confidence), FR-012 (rationale)
**Platform:** Web (React + Tailwind + Vite, ADR-9)
**Components:** FallbackBanner, ConfidenceMeter (LOW state), ExplainabilityPanel (fallback rationale)
**Design tokens:** fallback, text-on-primary, conf-low, surface-sunken, text-primary, text-secondary
**API binding:** `AnswerFinalEvent.routing.fallback` (true) + `routing.confidence[]` (all < 0.5) + `routing.rationale`; RouteResponse.fallback for the enterprise surface.

There are two independent triggers for fallback (HLD OAQ-6), and the UI represents both with the same banner + LOW meter so the user always knows the answer was NOT scoped:
1. **Query-time fallback** - the document has a TOC but every section scored < 0.50 (FR-009, PRD 8.3).
2. **Structural fallback** - the document is `fallback_only` (Scenario C, no usable TOC).

## Banner (top of the answer, when routing.fallback = true)

```
+------------------------------------------------------------------+
|  [ ! ]  Low routing confidence - searched the whole document.    |  FallbackBanner
|         This answer was NOT scoped to a specific section.        |  bg: fallback (#8A5A00)  text: text-on-primary
|         [ Why? ]                                                 |  "Why?" jumps to ExplainabilityPanel
+------------------------------------------------------------------+
```

The banner is `role="alert"`, carries an explicit icon + text message (level not conveyed by color alone, WCAG 1.4.1), and links to the explainability rationale.

## ConfidenceMeter in fallback (LOW)

```
  Routing confidence
  +------------------------------------------------------------+
  |  LOW  0.38  [###############.........................]      |  fill: conf-low (#B3261E)
  +------------------------------------------------------------+  aria-valuetext="LOW, 0.38, fallback used"
```

## ExplainabilityPanel rationale in fallback

```
  +------------------------------------------------------------+
  | (?) Why did you look here?                          [ v ]  |
  |------------------------------------------------------------|
  | "No TOC section scored above the 0.70 threshold (highest  |  routing.rationale
  |  was 0.38). With no confident section, the system fell    |
  |  back to searching the entire document. Treat this answer |
  |  with extra care - it is not section-scoped."             |
  |                                                            |
  | Sections considered (all below threshold):                |
  |   . Installation   sec_install   p4-20    0.38 --         |  routing.sections[] x confidence[]
  |   . Maintenance    sec_maint      p61-90   0.22 --         |
  +------------------------------------------------------------+
```

## Sources area in fallback

```
  Sources
  +------------------------------------------------------------+
  | No section citations - this answer used full-document      |  citations[] empty in fallback
  | retrieval.                                                 |  text-secondary
  +------------------------------------------------------------+
```

## States / variants

| Component | Variant | Token binding | API source |
|-----------|---------|---------------|------------|
| FallbackBanner | QueryTimeFallback / StructuralFallback (fallback_only) | bg: fallback, text: text-on-primary | routing.fallback / TocResponse.fallback_only |
| ConfidenceMeter | LOW (fallback) | fill: conf-low | routing.confidence[] all < 0.5 |
| ExplainabilityPanel | FallbackRationale | surface-sunken | routing.rationale |
| Sources | NoCitations | text-secondary | citations[]=[] |

## Accessibility notes (GIGW v3.0)
- FallbackBanner `role="alert"` - announced as soon as the final event indicates fallback.
- The fallback state is conveyed by icon + heading text + LOW label + amber color together (never color alone).
- "Why?" link sets focus into the ExplainabilityPanel region and expands it.
- ConfidenceMeter `aria-valuetext` explicitly includes "fallback used" so non-visual users get the same signal.
