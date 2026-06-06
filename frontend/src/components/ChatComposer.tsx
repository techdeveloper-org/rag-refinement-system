import { useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { Button } from "@/components/Button";

interface ChatComposerProps {
  documentTitle: string;
  disabled?: boolean;
  onSubmit: (query: string) => void;
}

/**
 * ChatComposer (FR-007). Sticky-bottom composer that posts
 * `AnswerRequest.query` to `POST /v1/answer`. Submits on Send click or
 * Ctrl/Cmd+Enter. The textarea is labelled and the Send button is Tab-reachable.
 *
 * @param documentTitle - Title of the active document (placeholder context).
 * @param disabled - Disables input while a request is in flight.
 * @param onSubmit - Called with the trimmed, non-empty query on submit.
 */
export function ChatComposer({ documentTitle, disabled = false, onSubmit }: ChatComposerProps): JSX.Element {
  const [value, setValue] = useState<string>("");

  const submit = (): void => {
    const trimmed = value.trim();
    if (trimmed.length === 0 || disabled) {
      return;
    }
    onSubmit(trimmed);
    setValue("");
  };

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>): void => {
    setValue(event.target.value);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      className="sticky bottom-0 z-sticky flex items-end gap-sm border-t border-border bg-surface px-md py-sm"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label htmlFor="chat-composer-input" className="sr-only">
        Ask a question about {documentTitle}
      </label>
      <textarea
        id="chat-composer-input"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder={`Ask another question about ${documentTitle}...`}
        className="flex-1 resize-none rounded-md border border-border bg-surface px-md py-sm text-body text-text-primary focus:border-primary"
      />
      <Button type="submit" disabled={disabled || value.trim().length === 0}>
        Send
      </Button>
    </form>
  );
}
