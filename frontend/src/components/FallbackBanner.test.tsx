import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FallbackBanner } from "@/components/FallbackBanner";

describe("FallbackBanner (FR-009)", () => {
  it("renders as a role=alert with the default message", () => {
    render(<FallbackBanner />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/searched the whole document/i);
  });

  it("renders a custom message when provided", () => {
    render(<FallbackBanner message="No usable structure for this document." />);
    expect(screen.getByRole("alert")).toHaveTextContent("No usable structure for this document.");
  });
});
