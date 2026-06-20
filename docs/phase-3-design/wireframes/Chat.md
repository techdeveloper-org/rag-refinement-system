# Wireframe: Chat with streaming answer + citations + confidence + explainability

**FR Coverage:** FR-007 (Q&A chat), FR-008 (citations), FR-009 (fallback indicator), FR-011 (confidence display), FR-012 (explainability panel), FR-018 (SSE streaming)
**Platform:** Web (React + Tailwind + Vite, ADR-9)
**Components:** AppHeader, ChatStream, MessageBubble, ConfidenceMeter, CitationCard, ExplainabilityPanel, FallbackBanner, ChatComposer, Button
**Design tokens:** surface, surface-alt, surface-sunken, primary, text-primary, text-secondary, border, conf-high, conf-med, conf-low, fallback
**API binding:** `POST /v1/answer` (AnswerRequest {document_id, query}) -> SSE: `event: token` (TokenEvent{token}) repeated, then `event: final` (AnswerFinalEvent{answer, citations[Citation{section_title, page_start, page_end}], routing[RoutingSummary{sections[], confidence[], fallback, rationale}]}); mid-stream `event: error` (Problem).

## Layout (after a scoped, high-confidence answer)

```
+------------------------------------------------------------------+
|  [Logo] RAG Refinement   |  Motor Manual (200p)  |  Profile (o)  |  AppHeader  h=64
+------------------------------------------------------------------+
|                                                                  |
|                          You                                     |  MessageBubble (user)  align-right
|        +-------------------------------------------+             |  bg: primary  text: text-on-primary  r=md
|        | What is the warranty period for the motor?|             |  AnswerRequest.query
|        +-------------------------------------------+             |
|                                                                  |  spacing-lg
|  Assistant                                                       |  MessageBubble (assistant)  align-left
|  +------------------------------------------------------------+  |  surface-alt  text: text-primary
|  | The motor is covered by a 24-month limited warranty from   |  |  AnswerFinalEvent.answer
|  | the date of purchase, covering parts and labour for        |  |  (streamed token-by-token, FR-018)
|  | manufacturing defects. [1]                                 |  |  [1] = inline citation ref -> CitationCard
|  +------------------------------------------------------------+  |
|                                                                  |
|  Routing confidence                                              |  ConfidenceMeter  (FR-011)
|  +------------------------------------------------------------+  |  reads routing.confidence[]
|  |  HIGH  0.94  [################################......]       |  |  fill: conf-high (>=0.7)
|  +------------------------------------------------------------+  |  label "HIGH" + numeral + bar (not color-only)
|                                                                  |
|  Sources  (1)                                                    |  CitationCard list  (FR-008)
|  +------------------------------------------------------------+  |  reads citations[]
|  | [book]  Warranty & Support                          [1]    |  |  Citation.section_title  / surface-alt  r=md
|  |         Pages 142-148           [ Jump to page 142 -> ]    |  |  Citation.page_start-page_end  / text-secondary
|  +------------------------------------------------------------+  |
|                                                                  |
|  +------------------------------------------------------------+  |  ExplainabilityPanel  (FR-012)
|  | (?) Why did you look here?                          [ v ]  |  |  disclosure  surface-sunken  r=lg
|  |------------------------------------------------------------|  |  reads routing.rationale + .sections + .confidence
|  | "The query asks about motor warranty duration; the TOC    |  |  routing.rationale  / text-primary  (italic)
|  |  section 'Warranty & Support' (pages 142-148) is the only |  |
|  |  section semantically matching 'warranty', scored 0.94.   |  |
|  |  No other section exceeded the 0.70 threshold."           |  |
|  |                                                            |  |
|  | Sections the router considered:                           |  |  text-secondary label
|  |   . Warranty & Support  sec_warranty   p142-148   0.94 OK |  |  routing.sections[] x routing.confidence[]
|  |   . Maintenance         sec_maint      p61-90     0.31 -- |  |  (full list incl. rejected, with score)
|  |   . Installation        sec_install    p4-20      0.12 -- |  |
|  +------------------------------------------------------------+  |
|                                                                  |
+------------------------------------------------------------------+
|  +--------------------------------------------------+  +------+  |  ChatComposer  (sticky bottom)
|  | Ask another question about Motor Manual...       |  | Send |  |  textarea -> AnswerRequest.query
|  +--------------------------------------------------+  +------+  |  Send: bg primary, text-on-primary
+------------------------------------------------------------------+
```

## Layout (fallback answer - router uncertain, FR-009)

```
+------------------------------------------------------------------+
|  [ ! ]  Low routing confidence - searched the whole document.    |  FallbackBanner  bg: fallback  role=alert
|         The answer below was not scoped to a specific section.   |  shown when routing.fallback=true
+------------------------------------------------------------------+
|  Assistant                                                       |
|  +------------------------------------------------------------+  |
|  | (full-document answer text, streamed) ...                  |  |
|  +------------------------------------------------------------+  |
|  Routing confidence                                              |
|  +------------------------------------------------------------+  |
|  |  LOW  0.38  [###############.........................]      |  |  fill: conf-low (<0.5)  routing.fallback=true
|  +------------------------------------------------------------+  |
|  Sources                                                         |
|  | No section citations - full-document retrieval.            |  |  citations[] empty in fallback
|  +------------------------------------------------------------+  |
|  | (?) Why did you look here?                          [ v ]  |  |  rationale explains why it fell back
|  |  "No TOC section scored above 0.70; all sections were      |  |  routing.rationale
|  |   below threshold, so the system searched the full doc."   |  |
+------------------------------------------------------------------+
```

## ConfidenceMeter level mapping (FR-011, PRD 8.3)

| routing.confidence value | Level label | Fill token | Threshold rule |
|--------------------------|-------------|-----------|----------------|
| >= 0.70 | HIGH | conf-high (#1B7A40) | included in targeted retrieval |
| 0.50 - 0.69 | MEDIUM | conf-med (#8A5A00) | included only if no high section |
| < 0.50 | LOW | conf-low (#B3261E) | excluded; all-low => fallback=true |

The meter renders the numeric value AND the High/Medium/Low word AND the bar fill AND an icon, so the level is never conveyed by color alone (WCAG 1.4.1).

## States / variants

| Component | States | Token binding | API source |
|-----------|--------|---------------|------------|
| ChatStream | Idle / Streaming / Complete / Error | - | SSE event lifecycle (FR-018) |
| MessageBubble (assistant) | Streaming (caret) / Complete | bg: surface-alt; caret: primary | TokenEvent.token -> AnswerFinalEvent.answer |
| ConfidenceMeter | High / Medium / Low / Fallback | fill: conf-high/med/low | routing.confidence[] (max or aggregate) |
| CitationCard | Default / Hover / Focused | surface-alt; hover elevation-2 | Citation{section_title, page_start, page_end} |
| CitationCard (none) | "No section citations - full-doc" | text-secondary | citations[]=[] when fallback |
| ExplainabilityPanel | Collapsed / Expanded | surface-sunken; chevron rotates | routing.rationale + sections[] + confidence[] |
| FallbackBanner | shown when routing.fallback=true | bg: fallback, text: text-on-primary | routing.fallback |
| ChatComposer | Empty / Typing / Sending / Disabled | border: border -> primary (focus) | -> AnswerRequest.query |
| Mid-stream error | inline error row + retry | bg: error tint, text: error | SSE event:error (Problem) - see AC-ADV-002 |

## Differentiator -> API field binding (the 3 core differentiators)

1. **CitationCard** (FR-008) <- `AnswerFinalEvent.citations[]` = `[{section_title, page_start, page_end}]` (+ optional `section_id`). "Jump to page" uses page_start.
2. **ConfidenceMeter** (FR-011) <- `AnswerFinalEvent.routing.confidence[]` (and `routing.fallback` to flip to fallback styling).
3. **ExplainabilityPanel** (FR-012) <- `AnswerFinalEvent.routing.rationale` (the prose), `routing.sections[]` (section ids), `routing.confidence[]` (per-section score). It lists BOTH selected and considered-but-rejected sections with their scores so the user sees "why here, and why not there."

## Accessibility notes (GIGW v3.0)
- Streamed answer region is `aria-live="polite"` so tokens are announced progressively without moving focus (FR-018).
- ConfidenceMeter uses `role="meter"` with `aria-valuenow`, `aria-valuemin=0`, `aria-valuemax=1`, and `aria-valuetext="HIGH, 0.94"`.
- ExplainabilityPanel is a disclosure: a `button[aria-expanded]` controls a `region[aria-labelledby]`; Enter/Space toggles.
- CitationCard "Jump to page N" is a link/button (keyboard-activatable); focus visible.
- FallbackBanner is `role="alert"`.
- Mid-stream SSE error is surfaced as `role="alert"` text (not silently dropped on a 200-opened stream) per advisory AC-ADV-002.
- Send button is reachable by Tab; Ctrl/Cmd+Enter submits from the composer.
