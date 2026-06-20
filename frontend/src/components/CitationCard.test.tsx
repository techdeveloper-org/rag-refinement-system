import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CitationCard, NoCitations } from "@/components/CitationCard";
import { WARRANTY_CITATION } from "@/test/fixtures";

describe("CitationCard (FR-008)", () => {
  it("renders section_title and the page range from citations[]", () => {
    render(<CitationCard citation={WARRANTY_CITATION} index={1} />);
    expect(screen.getByText("Warranty & Support")).toBeInTheDocument();
    expect(screen.getByText("Pages 142-148")).toBeInTheDocument();
  });

  it("exposes a descriptive aria-label", () => {
    render(<CitationCard citation={WARRANTY_CITATION} index={1} />);
    expect(
      screen.getByLabelText("Citation: Warranty & Support, pages 142 to 148"),
    ).toBeInTheDocument();
  });

  it("invokes onJumpToPage with page_start when the jump action is activated", async () => {
    const onJump = vi.fn();
    render(<CitationCard citation={WARRANTY_CITATION} index={1} onJumpToPage={onJump} />);
    await userEvent.click(screen.getByRole("button", { name: /jump to page 142/i }));
    expect(onJump).toHaveBeenCalledWith(142);
  });

  it("renders the no-citations placeholder in fallback mode", () => {
    render(<NoCitations />);
    expect(screen.getByText(/no section citations/i)).toBeInTheDocument();
  });
});
