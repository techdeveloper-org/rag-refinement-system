# Wireframe: Empty / Loading / Error states (all screens)

**FR Coverage:** FR-007 (chat UX resilience), FR-018 (streaming lifecycle), NFR-010 (RFC-7807 errors), NFR-013 (graceful degradation)
**Platform:** Web (React + Tailwind + Vite, ADR-9)
**Components:** EmptyState, LoadingSkeleton, StreamingIndicator, ErrorState, Toast
**Design tokens:** surface, surface-alt, text-primary, text-secondary, primary, error, warning
**API binding:** RFC-7807 `Problem{type, title, status, code, detail, query_id}`; SSE `event: error`; `503 SERVICE_UNAVAILABLE` (router/dep down -> NFR-013 fallback)

## Empty state - no documents (Library)

```
+------------------------------------------------------------------+
|                                                                  |
|                        [ document-stack icon ]                   |  illustration (decorative, aria-hidden)
|                                                                  |
|                   No documents yet                               |  heading-2 / text-primary
|        Upload a PDF to get smart, cited answers that know        |  body / text-secondary
|        exactly where in the document to look.                    |
|                                                                  |
|                  +---------------------------+                   |  primary CTA -> UploadDropzone
|                  |   Upload your first PDF   |                   |  bg: primary  text: text-on-primary  r=md
|                  +---------------------------+                   |
+------------------------------------------------------------------+
```

## Empty state - no messages yet (Chat, document selected)

```
+------------------------------------------------------------------+
|                        [ chat-bubble icon ]                      |
|              Ask anything about Motor Manual                     |  heading-3 / text-primary
|     Try: "What is the warranty period?"  or  "How do I          |  body-sm / text-secondary (suggestion chips)
|     reset the controller?"                                       |
|     +----------------------+  +----------------------+           |  suggestion chips (clickable -> composer)
|     | Warranty period?     |  | Reset controller?    |           |  surface-alt  border: border  r=full
|     +----------------------+  +----------------------+           |
+------------------------------------------------------------------+
```

## Loading - routing in progress (Chat, after submit, before first token)

```
+------------------------------------------------------------------+
|  You: What is the warranty period for the motor?                 |
|                                                                  |
|  Assistant                                                       |
|  +------------------------------------------------------------+  |
|  |  [o o o]  Routing your question...                         |  |  StreamingIndicator  aria-live=polite
|  |           Finding the right sections (router)              |  |  body-sm / text-secondary  aria-busy=true
|  +------------------------------------------------------------+  |
|                                                                  |
|  Routing confidence    [ shimmer bar ]                           |  LoadingSkeleton (ConfidenceMeter placeholder)
|  Sources               [ shimmer card ]                          |  LoadingSkeleton (CitationCard placeholder)
+------------------------------------------------------------------+
```

Stages of the loading caption track the pipeline (HLD 3.2): "Routing your question..." -> "Retrieving sections..." -> first `event: token` arrives -> switches to live streaming caret.

## Loading - library/TOC skeleton

```
+------------------------------------------------------------------+
|  [ shimmer card ]  [ shimmer card ]                              |  LoadingSkeleton grid (DocumentCard placeholders)
|  [ shimmer card ]  [ shimmer card ]                              |  shimmer over surface-alt
+------------------------------------------------------------------+
```

## Error - blocking (pre-stream auth/validation/not-found)

```
+------------------------------------------------------------------+
|                        [ alert-circle icon ]  (error)            |
|                  Something went wrong                            |  heading-3 / text-primary
|        {Problem.detail}                                          |  body / text-secondary  (e.g. "No document
|        Error code: {Problem.code}                                |  with the given id exists.")  caption / text-secondary
|                  +-----------------+                             |  ErrorState
|                  |   Try again     |                             |  primary CTA  bg: primary
|                  +-----------------+                             |  focus moves here on error (a11y)
+------------------------------------------------------------------+
```

## Error - mid-stream (SSE event: error after 200 opened, AC-ADV-002)

```
+------------------------------------------------------------------+
|  Assistant                                                       |
|  +------------------------------------------------------------+  |
|  | ...the motor is covered by a 24-month                      |  |  partial answer kept visible
|  |  +-----------------------------------------------------+   |  |
|  |  | [ ! ] The answer stream was interrupted.            |   |  |  inline error row  role=alert
|  |  |       {Problem.detail}              [ Retry ]       |   |  |  bg: error tint  text: error
|  |  +-----------------------------------------------------+   |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
```

## Error - degraded dependency (503, NFR-013)

```
+------------------------------------------------------------------+
|  [ ! ]  Routing is temporarily degraded. Answers may search the  |  warning banner  bg: warning tint
|         whole document until the service recovers.   Retry-After |  text: warning  role=status
+------------------------------------------------------------------+
```

## States / variants

| Component | Variant | Token binding | API source |
|-----------|---------|---------------|------------|
| EmptyState | NoDocuments / NoMessages | text-primary, primary CTA | DocumentListResponse.data=[] |
| LoadingSkeleton | Card / Bar / Bubble | shimmer over surface-alt | (pending) |
| StreamingIndicator | Routing / Retrieving / Streaming | text-secondary; caret primary | SSE lifecycle (FR-018) |
| ErrorState (blocking) | 400/401/404/422 | error icon; primary retry | Problem.code/detail (RFC-7807) |
| ErrorState (mid-stream) | interrupted | error tint inline | SSE event:error |
| DegradedBanner | 503 | warning tint | SERVICE_UNAVAILABLE + Retry-After |

## Accessibility notes (GIGW v3.0)
- Loading regions: `aria-busy="true"` + `aria-live="polite"`; the changing caption is announced.
- Blocking error: focus programmatically moves to the "Try again" button; `Problem.detail` is in a `role="alert"`.
- Mid-stream error: `role="alert"`, partial answer preserved, Retry re-issues `POST /v1/answer`.
- 503 degraded banner: `role="status"` (non-interrupting), surfaces Retry-After.
- `Problem.detail` is shown to the user but internal stack/DB details are never exposed (RFC-7807 contract; matches common-standards rule 2).
- Suggestion chips are buttons (keyboard-activatable); no PII in placeholder examples (DPDP - generic queries only).
