import type {
  AnswerFinalEvent,
  Citation,
  RoutingSummary,
  TocEntry,
} from "@/api/types";

/**
 * Deterministic test fixtures mirroring the Chat wireframe's worked example
 * (Motor Manual: Warranty & Support scored 0.94, two rejected sections).
 * Synthetic data only - no real PII.
 */

export const MOTOR_TOC: TocEntry[] = [
  { section_id: "sec_install", level: 1, title: "Installation", page_start: 4, page_end: 20 },
  { section_id: "sec_maint", level: 1, title: "Maintenance", page_start: 61, page_end: 90 },
  { section_id: "sec_warranty", level: 1, title: "Warranty & Support", page_start: 142, page_end: 148 },
];

export const WARRANTY_CITATION: Citation = {
  section_id: "sec_warranty",
  section_title: "Warranty & Support",
  page_start: 142,
  page_end: 148,
};

export const HIGH_ROUTING: RoutingSummary = {
  sections: ["sec_warranty", "sec_maint", "sec_install"],
  confidence: [0.94, 0.31, 0.12],
  fallback: false,
  rationale:
    "The query asks about motor warranty duration; 'Warranty & Support' is the only section semantically matching 'warranty', scored 0.94.",
};

export const HIGH_FINAL: AnswerFinalEvent = {
  query_id: "qry_test1",
  answer: "The motor is covered by a 24-month limited warranty. [1]",
  citations: [WARRANTY_CITATION],
  routing: HIGH_ROUTING,
};

export const FALLBACK_ROUTING: RoutingSummary = {
  sections: [],
  confidence: [],
  fallback: true,
  rationale: "No TOC section scored above 0.70; the system searched the full document.",
};

export const FALLBACK_FINAL: AnswerFinalEvent = {
  query_id: "qry_test2",
  answer: "Based on a full-document search, the warranty appears to be 24 months.",
  citations: [],
  routing: FALLBACK_ROUTING,
};

/** Build a Response whose body streams the given SSE text as UTF-8 bytes. */
export function sseResponse(sseText: string, status = 200): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(sseText));
      controller.close();
    },
  });
  return new Response(stream, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}
