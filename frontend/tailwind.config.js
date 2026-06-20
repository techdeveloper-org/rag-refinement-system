/**
 * Tailwind theme wired to the Phase 3 design tokens (ADR-9).
 *
 * Every value resolves to a CSS custom property defined in
 * `src/styles/tokens.css` (translated verbatim from
 * `docs/phase-3-design/tokens_css.css`). The design system is NOT recreated
 * here - utilities merely reference the token variables so a single source of
 * truth (the Phase 3 tokens) drives all surfaces, type, spacing, and color.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "var(--color-surface)",
        "surface-alt": "var(--color-surface-alt)",
        "surface-sunken": "var(--color-surface-sunken)",
        "text-primary": "var(--color-text-primary)",
        "text-secondary": "var(--color-text-secondary)",
        "text-on-primary": "var(--color-text-on-primary)",
        primary: "var(--color-primary)",
        "primary-dark": "var(--color-primary-dark)",
        info: "var(--color-info)",
        border: "var(--color-border)",
        "border-subtle": "var(--color-border-subtle)",
        error: "var(--color-error)",
        success: "var(--color-success)",
        warning: "var(--color-warning)",
        fallback: "var(--color-fallback)",
        "conf-high": "var(--color-conf-high)",
        "conf-med": "var(--color-conf-med)",
        "conf-low": "var(--color-conf-low)",
        "conf-track": "var(--color-conf-track)",
        "focus-ring": "var(--color-focus-ring)",
      },
      fontFamily: {
        base: "var(--font-family-base)",
        mono: "var(--font-family-mono)",
      },
      fontSize: {
        display: "var(--font-size-display)",
        "heading-1": "var(--font-size-heading-1)",
        "heading-2": "var(--font-size-heading-2)",
        "heading-3": "var(--font-size-heading-3)",
        body: "var(--font-size-body)",
        "body-sm": "var(--font-size-body-sm)",
        caption: "var(--font-size-caption)",
      },
      fontWeight: {
        regular: "var(--font-weight-regular)",
        medium: "var(--font-weight-medium)",
        semibold: "var(--font-weight-semibold)",
        bold: "var(--font-weight-bold)",
      },
      lineHeight: {
        tight: "var(--line-height-tight)",
        snug: "var(--line-height-snug)",
        normal: "var(--line-height-normal)",
      },
      spacing: {
        xs: "var(--spacing-xs)",
        sm: "var(--spacing-sm)",
        md: "var(--spacing-md)",
        lg: "var(--spacing-lg)",
        xl: "var(--spacing-xl)",
        "2xl": "var(--spacing-2xl)",
        "3xl": "var(--spacing-3xl)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        full: "var(--radius-full)",
      },
      boxShadow: {
        "elevation-1": "var(--elevation-1)",
        "elevation-2": "var(--elevation-2)",
        "elevation-3": "var(--elevation-3)",
      },
      zIndex: {
        sticky: "100",
        banner: "200",
        overlay: "900",
        modal: "1000",
        toast: "1100",
      },
      maxWidth: {
        chat: "var(--layout-chat-max-width)",
      },
      width: {
        "toc-sidebar": "var(--layout-toc-sidebar-width)",
      },
    },
  },
  plugins: [],
};
