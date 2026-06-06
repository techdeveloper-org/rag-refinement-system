import { describe, expect, it } from "vitest";
import { buildConsideredSections } from "@/domain/explainability";
import type { RoutingSummary } from "@/api/types";
import { MOTOR_TOC } from "@/test/fixtures";

describe("buildConsideredSections (GRC-001 TOC join)", () => {
  const routing: RoutingSummary = {
    sections: ["sec_warranty", "sec_maint", "sec_install"],
    confidence: [0.94, 0.31, 0.12],
    fallback: false,
  };

  it("joins each routing section id to the TOC for title and page range", () => {
    const rows = buildConsideredSections(routing, MOTOR_TOC);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toMatchObject({
      section_id: "sec_warranty",
      title: "Warranty & Support",
      page_start: 142,
      page_end: 148,
      confidence: 0.94,
      selected: true,
    });
  });

  it("preserves index alignment between sections[] and confidence[]", () => {
    const rows = buildConsideredSections(routing, MOTOR_TOC);
    expect(rows[1]).toMatchObject({ section_id: "sec_maint", confidence: 0.31 });
    expect(rows[2]).toMatchObject({ section_id: "sec_install", confidence: 0.12 });
  });

  it("marks rejected (below-threshold) sections as not selected", () => {
    const rows = buildConsideredSections(routing, MOTOR_TOC);
    expect(rows[1]?.selected).toBe(false);
    expect(rows[2]?.selected).toBe(false);
  });

  it("falls back to the section id as title when the TOC has no match", () => {
    const orphan: RoutingSummary = { sections: ["sec_unknown"], confidence: [0.8], fallback: false };
    const rows = buildConsideredSections(orphan, MOTOR_TOC);
    expect(rows[0]).toMatchObject({
      section_id: "sec_unknown",
      title: "sec_unknown",
      page_start: null,
      page_end: null,
    });
  });
});
