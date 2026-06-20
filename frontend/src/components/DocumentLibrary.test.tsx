import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentLibrary } from "@/components/DocumentLibrary";
import type { Document, DocumentListResponse } from "@/api/types";

const INDEXED_DOC: Document = {
  doc_id: "doc_motor1",
  title: "Motor Manual",
  total_pages: 200,
  domain: "legal",
  residency_region: "GLOBAL",
  fallback_only: false,
  created_at: "2026-06-06T00:00:00Z",
};

const FALLBACK_DOC: Document = {
  doc_id: "doc_scan1",
  title: "Scanned Lease",
  total_pages: 48,
  residency_region: "IN",
  fallback_only: true,
  created_at: "2026-06-06T00:00:00Z",
};

function listOf(data: Document[]): DocumentListResponse {
  return {
    data,
    pagination: { page: 1, page_size: 20, total_count: data.length, total_pages: 1 },
  };
}

const NOOP = {
  onOpen: vi.fn(),
  onDelete: vi.fn(),
  onExportData: vi.fn(),
};

describe("DocumentLibrary (FR-024, GRC-003 badges)", () => {
  it("renders an Indexed badge for non-fallback documents", () => {
    render(<DocumentLibrary list={listOf([INDEXED_DOC])} {...NOOP} />);
    expect(screen.getByText("Motor Manual")).toBeInTheDocument();
    expect(screen.getByText("Indexed")).toBeInTheDocument();
    expect(screen.getByText("200 pages · legal")).toBeInTheDocument();
  });

  it("renders a Fallback-only badge for fallback_only documents", () => {
    render(<DocumentLibrary list={listOf([FALLBACK_DOC])} {...NOOP} />);
    expect(screen.getByText("Fallback-only")).toBeInTheDocument();
  });

  it("shows an empty state when there are no documents", () => {
    render(<DocumentLibrary list={listOf([])} {...NOOP} />);
    expect(screen.getByText(/no documents yet/i)).toBeInTheDocument();
  });

  it("opens a DPDP erasure confirm from the card menu and confirms deletion", async () => {
    const onDelete = vi.fn();
    render(<DocumentLibrary list={listOf([INDEXED_DOC])} {...NOOP} onDelete={onDelete} />);

    await userEvent.click(screen.getByRole("button", { name: /actions for motor manual/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/erase document and all data/i);

    await userEvent.click(screen.getByRole("button", { name: "Erase" }));
    expect(onDelete).toHaveBeenCalledWith(INDEXED_DOC);
  });
});
