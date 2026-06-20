/**
 * Inline SVG icon set. Icons are decorative (`aria-hidden`) - meaning is always
 * carried by accompanying text so no information is conveyed by icon alone
 * (WCAG 1.4.1). Each accepts a className for token-driven sizing/color.
 */
interface IconProps {
  className?: string;
}

/** Book glyph for citation cards. */
export function BookIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M4 4h11a2 2 0 0 1 2 2v14H6a2 2 0 0 1-2-2V4z" />
      <path d="M17 6h3v14H6" />
    </svg>
  );
}

/** Upward arrow for the upload dropzone. */
export function UploadIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 19V6" />
      <path d="m6 11 6-6 6 6" />
      <path d="M5 21h14" />
    </svg>
  );
}

/** Chevron used by disclosure panels and tree entries. */
export function ChevronIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

/** Filled disc - HIGH confidence level indicator. */
export function CircleFilledIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
    </svg>
  );
}

/** Half disc - MEDIUM confidence level indicator. */
export function CircleHalfIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
    </svg>
  );
}

/** Hollow disc - LOW confidence level indicator. */
export function CircleEmptyIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
    </svg>
  );
}

/** Warning triangle - fallback banner / fallback meter. */
export function WarningIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 3 2 20h20L12 3z" />
      <path d="M12 10v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

/** Question mark - explainability disclosure header. */
export function HelpIcon({ className }: IconProps): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 0 1 4.5 1.5c0 1.5-2 2-2 3" />
      <path d="M12 17h.01" />
    </svg>
  );
}
