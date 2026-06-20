import type { AnswerFinalEvent, Problem, TocEntry } from "@/api/types";
import { MessageBubble } from "@/components/MessageBubble";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { CitationCard, NoCitations } from "@/components/CitationCard";
import { ExplainabilityPanel } from "@/components/ExplainabilityPanel";
import { FallbackBanner } from "@/components/FallbackBanner";
import { StreamingIndicator } from "@/components/StreamingIndicator";
import type { StreamPhase } from "@/components/StreamingIndicator";
import { ErrorState } from "@/components/ErrorState";

/** A completed or in-flight chat turn. */
export interface ChatTurn {
  id: string;
  query: string;
  answerText: string;
  streaming: boolean;
  phase: StreamPhase;
  final: AnswerFinalEvent | null;
  error: Problem | null;
  /**
   * True when the turn's stream was aborted (superseded by a re-ask, or
   * cancelled) rather than completed or errored. A cancelled turn holds a
   * truncated partial answer and must not be presented as a finished answer.
   */
  cancelled: boolean;
}

interface ChatStreamProps {
  turns: readonly ChatTurn[];
  toc: readonly TocEntry[];
  onJumpToPage?: (page: number) => void;
  onRetry?: (turnId: string) => void;
}

/** Render the explainability + confidence + citations block for a final answer. */
function AnswerInsights({
  final,
  toc,
  onJumpToPage,
}: {
  final: AnswerFinalEvent;
  toc: readonly TocEntry[];
  onJumpToPage?: (page: number) => void;
}): JSX.Element {
  const { routing, citations } = final;
  return (
    <div className="flex flex-col gap-md">
      {routing.fallback ? <FallbackBanner /> : null}
      <ConfidenceMeter routing={routing} />
      <section aria-labelledby="sources-heading" className="flex flex-col gap-sm">
        <h3 id="sources-heading" className="text-body-sm font-medium text-text-secondary">
          Sources ({citations.length})
        </h3>
        {citations.length === 0 ? (
          <NoCitations />
        ) : (
          citations.map((citation, index) => (
            <CitationCard
              key={`${citation.section_title}-${citation.page_start}-${index}`}
              citation={citation}
              index={index + 1}
              {...(onJumpToPage === undefined ? {} : { onJumpToPage })}
            />
          ))
        )}
      </section>
      <ExplainabilityPanel routing={routing} toc={toc} />
    </div>
  );
}

/**
 * ChatStream (FR-007, FR-018). The stacked message list that assembles each
 * turn: the user question bubble, the streamed assistant answer bubble, and -
 * once the terminal final event arrives - the ConfidenceMeter, CitationCards,
 * ExplainabilityPanel, and FallbackBanner bound to `AnswerFinalEvent`.
 *
 * A mid-stream SSE error is rendered inline as an alert (AC-ADV-002) rather than
 * dropped.
 *
 * @param turns - The chat turns to render, oldest first.
 * @param toc - The open document's TOC, used by the explainability TOC-join.
 * @param onJumpToPage - Optional citation "Jump to page" handler.
 * @param onRetry - Optional retry handler for a failed turn.
 */
export function ChatStream({ turns, toc, onJumpToPage, onRetry }: ChatStreamProps): JSX.Element {
  return (
    <div className="flex flex-col gap-xl">
      {turns.map((turn) => (
        <div key={turn.id} className="flex flex-col gap-md">
          <MessageBubble role="user" text={turn.query} />
          {turn.answerText.length > 0 || turn.streaming ? (
            <MessageBubble role="assistant" text={turn.answerText} streaming={turn.streaming} />
          ) : null}
          {turn.streaming && turn.answerText.length === 0 ? (
            <StreamingIndicator phase={turn.phase} />
          ) : null}
          {turn.cancelled && turn.final === null && turn.error === null ? (
            <p className="text-body-sm italic text-text-secondary" data-testid="cancelled-marker">
              Cancelled / superseded
            </p>
          ) : null}
          {turn.error !== null ? (
            <ErrorState
              problem={turn.error}
              midStream={turn.answerText.length > 0}
              {...(onRetry === undefined ? {} : { onRetry: () => onRetry(turn.id) })}
            />
          ) : null}
          {turn.final !== null ? (
            <AnswerInsights
              final={turn.final}
              toc={toc}
              {...(onJumpToPage === undefined ? {} : { onJumpToPage })}
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}
