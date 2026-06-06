import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { HIGH_ROUTING, FALLBACK_ROUTING } from "@/test/fixtures";

describe("ConfidenceMeter (FR-011)", () => {
  it("renders HIGH with max(confidence[]) as a role=meter and aria-valuetext", () => {
    render(<ConfidenceMeter routing={HIGH_ROUTING} />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "0.94");
    expect(meter).toHaveAttribute("aria-valuemax", "1");
    expect(meter).toHaveAttribute("aria-valuetext", "HIGH, 0.94");
  });

  it("conveys the level by label text and numeral, not color alone (WCAG 1.4.1)", () => {
    render(<ConfidenceMeter routing={HIGH_ROUTING} />);
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("0.94")).toBeInTheDocument();
  });

  it("renders the fallback variant when routing.fallback is true", () => {
    render(<ConfidenceMeter routing={FALLBACK_ROUTING} />);
    expect(screen.getByText("FALLBACK")).toBeInTheDocument();
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuetext", "Fallback, full-document retrieval");
  });
});
