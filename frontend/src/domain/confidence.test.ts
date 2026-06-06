import { describe, expect, it } from "vitest";
import { confidenceLevel, maxConfidence, resolveMeterState } from "@/domain/confidence";
import type { RoutingSummary } from "@/api/types";

describe("confidenceLevel (PRD 8.3 thresholds)", () => {
  it("maps >= 0.70 to HIGH", () => {
    expect(confidenceLevel(0.94)).toBe("HIGH");
    expect(confidenceLevel(0.7)).toBe("HIGH");
  });

  it("maps 0.50-0.69 to MEDIUM", () => {
    expect(confidenceLevel(0.69)).toBe("MEDIUM");
    expect(confidenceLevel(0.5)).toBe("MEDIUM");
  });

  it("maps < 0.50 to LOW", () => {
    expect(confidenceLevel(0.49)).toBe("LOW");
    expect(confidenceLevel(0.12)).toBe("LOW");
  });
});

describe("maxConfidence (GRC-002 reduction)", () => {
  it("returns the maximum of the array", () => {
    expect(maxConfidence([0.12, 0.94, 0.31])).toBe(0.94);
  });

  it("returns null for an empty array", () => {
    expect(maxConfidence([])).toBeNull();
  });
});

describe("resolveMeterState (GRC-002)", () => {
  it("uses max(confidence[]) for the displayed scalar and level", () => {
    const routing: RoutingSummary = {
      sections: ["a", "b", "c"],
      confidence: [0.12, 0.94, 0.31],
      fallback: false,
    };
    const state = resolveMeterState(routing);
    expect(state).toEqual({ variant: "level", level: "HIGH", value: 0.94 });
  });

  it("renders the fallback variant when routing.fallback is true", () => {
    const routing: RoutingSummary = { sections: ["a"], confidence: [0.94], fallback: true };
    expect(resolveMeterState(routing)).toEqual({ variant: "fallback" });
  });

  it("renders the fallback variant when confidence[] is empty", () => {
    const routing: RoutingSummary = { sections: [], confidence: [], fallback: false };
    expect(resolveMeterState(routing)).toEqual({ variant: "fallback" });
  });
});
