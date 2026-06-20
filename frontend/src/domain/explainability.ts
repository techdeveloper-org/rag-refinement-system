import type { Confidence, RoutingSummary, SectionId, TocEntry } from "@/api/types";
import { HIGH_THRESHOLD } from "@/domain/confidence";

/**
 * A row in the ExplainabilityPanel's "sections the router considered" list.
 *
 * Title and page range are resolved client-side by joining the routing
 * section id to the already-loaded TOC (GRC-001 binding path).
 */
export interface ConsideredSection {
  section_id: SectionId;
  title: string;
  page_start: number | null;
  page_end: number | null;
  confidence: Confidence;
  selected: boolean;
}

/**
 * Build the considered-sections list for the ExplainabilityPanel (GRC-001).
 *
 * `routing.sections[]` and `routing.confidence[]` are index-aligned: each
 * `sections[i]` is a bare section id and `confidence[i]` is its score. The
 * human-readable title and page range are resolved by joining `sections[i]` to
 * `toc[]` via `section_id` (the universal key), since the SSE routing summary
 * does not carry titles. A section is marked `selected` when its score meets
 * the high threshold (>=0.70), matching the "included in targeted retrieval"
 * rule; lower-scoring (rejected) sections are still listed so the user sees
 * "why here, and why not there".
 *
 * @param routing - The RoutingSummary from the answer's final event.
 * @param toc - The TOC of the open document (TocResponse.toc[]).
 * @returns One row per `sections[i]`, joined to the TOC for title/pages.
 */
export function buildConsideredSections(
  routing: RoutingSummary,
  toc: readonly TocEntry[],
): ConsideredSection[] {
  const tocById = new Map<SectionId, TocEntry>();
  for (const entry of toc) {
    tocById.set(entry.section_id, entry);
  }

  return routing.sections.map((sectionId, index) => {
    const score = routing.confidence[index] ?? 0;
    const entry = tocById.get(sectionId);
    return {
      section_id: sectionId,
      title: entry?.title ?? sectionId,
      page_start: entry?.page_start ?? null,
      page_end: entry?.page_end ?? null,
      confidence: score,
      selected: score >= HIGH_THRESHOLD,
    };
  });
}
