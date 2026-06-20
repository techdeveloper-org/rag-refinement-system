import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TocSidebar } from "@/components/TocSidebar";
import type { TocResponse } from "@/api/types";
import { MOTOR_TOC } from "@/test/fixtures";

const TOC: TocResponse = { document_id: "doc_abc123", fallback_only: false, toc: MOTOR_TOC };

describe("TocSidebar (FR-002, FR-003)", () => {
  it("renders a tree of section entries with titles and page ranges", () => {
    render(<TocSidebar toc={TOC} />);
    expect(screen.getByRole("tree", { name: "Sections" })).toBeInTheDocument();
    expect(screen.getAllByRole("treeitem")).toHaveLength(3);
    expect(screen.getByText("Warranty & Support")).toBeInTheDocument();
    expect(screen.getByText("142-148")).toBeInTheDocument();
  });

  it("calls onSelectSection when a section is activated", async () => {
    const onSelect = vi.fn();
    render(<TocSidebar toc={TOC} onSelectSection={onSelect} />);
    await userEvent.click(screen.getByText("Warranty & Support"));
    expect(onSelect).toHaveBeenCalledWith(MOTOR_TOC[2]);
  });

  it("shows the fallback-only empty state when there is no usable structure", () => {
    const fallbackToc: TocResponse = { document_id: "doc_x", fallback_only: true, toc: [] };
    render(<TocSidebar toc={fallbackToc} />);
    expect(screen.getByText(/no table of contents detected/i)).toBeInTheDocument();
  });
});
