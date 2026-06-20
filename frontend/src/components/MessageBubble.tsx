interface MessageBubbleProps {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}

/**
 * MessageBubble (FR-007, FR-018). A single chat turn. The user bubble binds
 * `AnswerRequest.query` (right-aligned, primary surface); the assistant bubble
 * binds the streamed `TokenEvent.token` text accumulating into
 * `AnswerFinalEvent.answer` (left-aligned, alt surface). While streaming, a
 * blinking caret follows the text.
 *
 * The assistant region is `aria-live="polite"` so tokens are announced
 * progressively without stealing focus.
 *
 * @param role - "user" or "assistant".
 * @param text - The (possibly partial) message text.
 * @param streaming - Whether the assistant message is still streaming.
 */
export function MessageBubble({ role, text, streaming = false }: MessageBubbleProps): JSX.Element {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-chat rounded-md bg-primary px-md py-sm text-body text-text-on-primary">
          {text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        aria-live="polite"
        aria-busy={streaming}
        className="max-w-chat rounded-md bg-surface-alt px-md py-sm text-body text-text-primary"
      >
        <span>{text}</span>
        {streaming ? (
          <span
            aria-hidden="true"
            className="ml-xs inline-block w-[2px] h-[1.1em] align-middle bg-primary animate-pulse"
          />
        ) : null}
      </div>
    </div>
  );
}
