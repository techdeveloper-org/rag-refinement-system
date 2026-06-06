import type { ButtonHTMLAttributes, ReactNode } from "react";

/** Visual variant of the {@link Button} (component_library.md Button). */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-primary text-text-on-primary hover:bg-primary-dark",
  secondary: "bg-surface-alt text-text-primary hover:bg-surface-sunken border border-border",
  ghost: "bg-transparent text-primary hover:bg-surface-alt",
  destructive: "bg-error text-text-on-primary hover:opacity-90",
};

/**
 * Native button styled per the Phase 3 design tokens with a 44px minimum tap
 * target (GIGW v3.0) and visible keyboard focus from the global token style.
 *
 * @param variant - Visual treatment; defaults to `primary`.
 */
export function Button({
  variant = "primary",
  children,
  className,
  type,
  ...rest
}: ButtonProps): JSX.Element {
  return (
    <button
      type={type ?? "button"}
      className={[
        "inline-flex items-center justify-center gap-sm",
        "min-h-[44px] px-lg py-sm rounded-md",
        "text-body font-semibold",
        "transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
        VARIANT_CLASSES[variant],
        className ?? "",
      ].join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}
