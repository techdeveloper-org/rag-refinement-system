import { useCallback, useEffect, useRef, useState } from "react";
import type { AnswerStreamClient } from "@/api/sse";
import type { AnswerRequest, DocumentId } from "@/api/types";
import type { ChatTurn } from "@/components/ChatStream";

/** Public surface of the answer-stream hook. */
export interface UseAnswerStreamResult {
  turns: ChatTurn[];
  pending: boolean;
  ask: (documentId: DocumentId, query: string) => void;
  abort: () => void;
}

let turnCounter = 0;

/** Generate a stable, monotonic id for a new chat turn. */
function nextTurnId(): string {
  turnCounter += 1;
  return `turn_${turnCounter}`;
}

/**
 * React hook that drives a `POST /v1/answer` SSE request into {@link ChatTurn}
 * state for the {@link ChatStream}.
 *
 * Appends a turn on `ask`, accumulates `token` events into the turn's answer
 * text, attaches the terminal `final` event, and records a mid-stream or
 * pre-stream `error` Problem on the turn (surfaced as an alert, never dropped).
 *
 * Only one stream is in flight at a time: a new `ask` aborts the previous
 * stream before starting, the in-flight stream is aborted on unmount, and the
 * exposed `abort` cancels it on a document switch. The terminal `finally`
 * reconciles shared `pending`/abort state only when its own controller is still
 * the current one, so a late finisher never re-enables the composer while a
 * newer stream is live.
 *
 * @param client - The configured AnswerStreamClient.
 * @returns The accumulated turns, a pending flag, the `ask` action, and an
 *   `abort` action that cancels any in-flight stream.
 */
export function useAnswerStream(client: AnswerStreamClient): UseAnswerStreamResult {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pending, setPending] = useState<boolean>(false);
  const abortRef = useRef<AbortController | null>(null);

  const updateTurn = useCallback((id: string, patch: Partial<ChatTurn>): void => {
    setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn)));
  }, []);

  const ask = useCallback(
    (documentId: DocumentId, query: string): void => {
      const id = nextTurnId();
      const turn: ChatTurn = {
        id,
        query,
        answerText: "",
        streaming: true,
        phase: "routing",
        final: null,
        error: null,
      };
      setTurns((prev) => [...prev, turn]);
      setPending(true);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const request: AnswerRequest = { document_id: documentId, query };

      void client
        .streamAnswer(
          request,
          {
            onToken: (event) => {
              updateTurn(id, { phase: "streaming" });
              setTurns((prev) =>
                prev.map((existing) =>
                  existing.id === id
                    ? { ...existing, answerText: existing.answerText + event.token }
                    : existing,
                ),
              );
            },
            onFinal: (event) => {
              updateTurn(id, {
                final: event,
                answerText: event.answer,
                streaming: false,
              });
            },
            onError: (problem) => {
              updateTurn(id, { error: problem, streaming: false });
            },
          },
          controller.signal,
        )
        .finally(() => {
          updateTurn(id, { streaming: false });
          if (abortRef.current === controller) {
            setPending(false);
            abortRef.current = null;
          }
        });
    },
    [client, updateTurn],
  );

  const abort = useCallback((): void => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(false);
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

  return { turns, pending, ask, abort };
}
