/** Severity of a {@link Toast} notification. */
export type ToastTone = "success" | "info" | "warning" | "error";

interface ToastProps {
  tone: ToastTone;
  message: string;
  onDismiss?: () => void;
}

const TONE_CLASSES: Record<ToastTone, string> = {
  success: "bg-success text-text-on-primary",
  info: "bg-primary text-text-on-primary",
  warning: "bg-fallback text-text-on-primary",
  error: "bg-error text-text-on-primary",
};

const TONE_ROLE: Record<ToastTone, "status" | "alert"> = {
  success: "status",
  info: "status",
  warning: "status",
  error: "alert",
};

/**
 * Toast. Transient notification for upload outcomes and RFC 7807 errors. Success
 * / info / warning use `role="status"`; error uses `role="alert"`. For errors,
 * `message` should be the `Problem.detail` (no internal detail leaked).
 *
 * @param tone - Visual + semantic severity.
 * @param message - User-facing message.
 * @param onDismiss - Optional dismiss handler.
 */
export function Toast({ tone, message, onDismiss }: ToastProps): JSX.Element {
  return (
    <div
      role={TONE_ROLE[tone]}
      className={`flex items-center justify-between gap-md rounded-md px-md py-sm ${TONE_CLASSES[tone]}`}
    >
      <span className="text-body-sm">{message}</span>
      {onDismiss !== undefined ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss notification"
          className="min-h-[44px] min-w-[44px] text-body font-bold"
        >
          &times;
        </button>
      ) : null}
    </div>
  );
}
