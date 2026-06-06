import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import type { IngestRequestFields, ResidencyRegion } from "@/api/types";
import { RESIDENCY_REGIONS } from "@/api/client";
import { UploadIcon } from "@/components/icons";

interface UploadDropzoneProps {
  uploading?: boolean;
  progressLabel?: string;
  onUpload: (file: File, fields: IngestRequestFields) => void;
}

/**
 * UploadDropzone (FR-001, FR-027, FR-028). Accepts a PDF via drag-drop or the
 * native file picker and posts an `IngestRequest` (file + optional title,
 * domain, `no_retention`, `residency_region`, `ocr`) to `POST /v1/documents`.
 *
 * Keyboard-equivalent: the dropzone is a labelled button region; Enter/Space
 * opens the file picker. The progress region is `aria-live="polite"` +
 * `aria-busy` while uploading.
 *
 * @param uploading - Whether an upload is in progress.
 * @param progressLabel - Client-side progress caption (e.g. "Parsing TOC... 40%").
 * @param onUpload - Called with the selected file and the chosen ingest fields.
 */
export function UploadDropzone({ uploading = false, progressLabel, onUpload }: UploadDropzoneProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState<boolean>(false);
  const [noRetention, setNoRetention] = useState<boolean>(false);
  const [residency, setResidency] = useState<ResidencyRegion>("GLOBAL");

  const submitFile = (file: File): void => {
    onUpload(file, { no_retention: noRetention, residency_region: residency });
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0];
    if (file !== undefined) {
      submitFile(file);
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    setDragOver(false);
    const file = event.dataTransfer.files?.[0];
    if (file !== undefined) {
      submitFile(file);
    }
  };

  const openPicker = (): void => {
    inputRef.current?.click();
  };

  return (
    <div
      className={[
        "rounded-md border-2 border-dashed bg-surface-alt p-lg",
        dragOver ? "border-primary bg-surface-sunken" : "border-border",
      ].join(" ")}
      onDragOver={(event) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="sr-only"
        onChange={handleFileChange}
      />
      <div className="flex flex-col items-center gap-md text-center">
        <UploadIcon className="w-8 h-8 text-primary" />
        <button
          type="button"
          onClick={openPicker}
          aria-label="Drag a PDF here, or browse files"
          className="min-h-[44px] rounded-md bg-primary px-lg text-body font-semibold text-text-on-primary hover:bg-primary-dark"
        >
          Drag a PDF here, or browse files
        </button>
        <p className="text-body-sm text-text-secondary">PDF up to 50 MB / 1000 pages.</p>

        <div className="flex flex-wrap items-center justify-center gap-lg">
          <label className="flex items-center gap-sm text-body-sm text-text-primary">
            <input
              type="checkbox"
              checked={noRetention}
              onChange={(event) => setNoRetention(event.target.checked)}
            />
            No-retention mode
          </label>
          <label className="flex items-center gap-sm text-body-sm text-text-primary">
            Residency:
            <select
              value={residency}
              onChange={(event) => setResidency(event.target.value as ResidencyRegion)}
              className="min-h-[44px] rounded-sm border border-border bg-surface px-sm text-body-sm"
            >
              {RESIDENCY_REGIONS.map((region) => (
                <option key={region} value={region}>
                  {region}
                </option>
              ))}
            </select>
          </label>
        </div>

        {uploading ? (
          <div aria-live="polite" aria-busy="true" className="w-full">
            <p className="text-body-sm text-text-secondary">{progressLabel ?? "Uploading..."}</p>
            <div className="mt-xs h-2 w-full overflow-hidden rounded-full bg-conf-track">
              <div className="h-full w-1/2 animate-pulse bg-primary" />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
