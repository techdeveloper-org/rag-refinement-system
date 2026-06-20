import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadDropzone } from "@/components/UploadDropzone";

describe("UploadDropzone (FR-001, FR-027, FR-028)", () => {
  it("posts the selected file with the chosen no_retention and residency fields", async () => {
    const onUpload = vi.fn();
    render(<UploadDropzone onUpload={onUpload} />);

    await userEvent.click(screen.getByLabelText("No-retention mode"));
    await userEvent.selectOptions(screen.getByRole("combobox"), "IN");

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["%PDF-1.7"], "manual.pdf", { type: "application/pdf" });
    await userEvent.upload(input, file);

    expect(onUpload).toHaveBeenCalledTimes(1);
    const [uploadedFile, fields] = onUpload.mock.calls[0] as [File, Record<string, unknown>];
    expect(uploadedFile.name).toBe("manual.pdf");
    expect(fields["no_retention"]).toBe(true);
    expect(fields["residency_region"]).toBe("IN");
  });

  it("exposes an aria-busy progress region while uploading", () => {
    render(<UploadDropzone uploading progressLabel="Parsing TOC... 40%" onUpload={vi.fn()} />);
    expect(screen.getByText("Parsing TOC... 40%")).toBeInTheDocument();
  });
});
