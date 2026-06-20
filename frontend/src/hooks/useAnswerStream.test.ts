import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { AnswerStreamClient } from "@/api/sse";
import type { AnswerStreamHandlers } from "@/api/sse";
import type { AnswerRequest, DocumentId } from "@/api/types";
import { useAnswerStream } from "@/hooks/useAnswerStream";

/** A single intercepted streamAnswer invocation, exposing its abort signal. */
interface StreamCall {
  request: AnswerRequest;
  handlers: AnswerStreamHandlers;
  signal: AbortSignal | undefined;
  resolve: () => void;
}

/**
 * Build a fake AnswerStreamClient whose streamAnswer never resolves on its own.
 *
 * Each call is recorded with its abort signal and a `resolve` hook so a test can
 * deterministically finish a specific stream and assert ordering effects.
 */
function fakeStreamClient(): { client: AnswerStreamClient; calls: StreamCall[] } {
  const calls: StreamCall[] = [];
  const streamAnswer = vi.fn(
    (request: AnswerRequest, handlers: AnswerStreamHandlers, signal?: AbortSignal): Promise<void> => {
      return new Promise<void>((resolve) => {
        calls.push({ request, handlers, signal, resolve });
      });
    },
  );
  const client = { streamAnswer } as unknown as AnswerStreamClient;
  return { client, calls };
}

const DOC_A: DocumentId = "doc_a";
const DOC_B: DocumentId = "doc_b";

describe("useAnswerStream", () => {
  it("aborts the previous stream when ask is called again", () => {
    const { client, calls } = fakeStreamClient();
    const { result } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "first question");
    });
    act(() => {
      result.current.ask(DOC_A, "second question");
    });

    expect(calls).toHaveLength(2);
    expect(calls[0]?.signal?.aborted).toBe(true);
    expect(calls[1]?.signal?.aborted).toBe(false);
    expect(result.current.pending).toBe(true);
  });

  it("aborts the in-flight stream on unmount", () => {
    const { client, calls } = fakeStreamClient();
    const { result, unmount } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "a question");
    });
    expect(calls[0]?.signal?.aborted).toBe(false);

    unmount();
    expect(calls[0]?.signal?.aborted).toBe(true);
  });

  it("aborts the in-flight stream when abort is called for a document switch", () => {
    const { client, calls } = fakeStreamClient();
    const { result } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "a question");
    });
    act(() => {
      result.current.abort();
    });

    expect(calls[0]?.signal?.aborted).toBe(true);
    expect(result.current.pending).toBe(false);
  });

  it("reset clears turns and aborts the in-flight stream on a document switch", () => {
    const { client, calls } = fakeStreamClient();
    const { result } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "first question");
    });
    expect(result.current.turns).toHaveLength(1);

    act(() => {
      result.current.reset();
    });

    expect(result.current.turns).toHaveLength(0);
    expect(result.current.pending).toBe(false);
    expect(calls[0]?.signal?.aborted).toBe(true);
  });

  it("marks a superseded turn cancelled (not a completed answer) when re-asked mid-stream", async () => {
    const { client, calls } = fakeStreamClient();
    const { result } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "first question");
    });
    act(() => {
      calls[0]?.handlers.onToken({ token: "Partial answer" });
    });
    act(() => {
      result.current.ask(DOC_A, "second question");
    });
    expect(calls[0]?.signal?.aborted).toBe(true);

    await act(async () => {
      calls[0]?.resolve();
      await Promise.resolve();
    });

    const supersededTurn = result.current.turns[0];
    expect(supersededTurn?.cancelled).toBe(true);
    expect(supersededTurn?.streaming).toBe(false);
    expect(supersededTurn?.final).toBeNull();
    expect(supersededTurn?.error).toBeNull();
    expect(supersededTurn?.answerText).toBe("Partial answer");
  });

  it("does not mark a normally completed turn as cancelled", async () => {
    const { client, calls } = fakeStreamClient();
    const { result } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "a question");
    });
    act(() => {
      calls[0]?.handlers.onFinal({
        query_id: "qry_1",
        answer: "The complete answer.",
        citations: [],
        routing: { sections: [], confidence: [], fallback: false },
      });
    });

    await act(async () => {
      calls[0]?.resolve();
      await Promise.resolve();
    });

    const completedTurn = result.current.turns[0];
    expect(completedTurn?.cancelled).toBe(false);
    expect(completedTurn?.final?.answer).toBe("The complete answer.");
  });

  it("does not update state after unmount when the aborted stream's error/finally settle", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { client, calls } = fakeStreamClient();
    const { result, unmount } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "a question");
    });

    unmount();
    expect(calls[0]?.signal?.aborted).toBe(true);

    await act(async () => {
      calls[0]?.handlers.onError({
        type: "about:blank",
        title: "NETWORK_ERROR",
        status: 0,
        code: "NETWORK_ERROR",
      });
      calls[0]?.resolve();
      await Promise.resolve();
    });

    const stateUpdateWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("unmounted component"),
    );
    expect(stateUpdateWarnings).toHaveLength(0);
    errorSpy.mockRestore();
  });

  it("does not clear pending when an older stream finishes while a newer one is live", async () => {
    const { client, calls } = fakeStreamClient();
    const { result } = renderHook(() => useAnswerStream(client));

    act(() => {
      result.current.ask(DOC_A, "first");
    });
    act(() => {
      result.current.ask(DOC_B, "second");
    });
    expect(calls).toHaveLength(2);

    await act(async () => {
      calls[0]?.resolve();
      await Promise.resolve();
    });

    expect(result.current.pending).toBe(true);

    await act(async () => {
      calls[1]?.resolve();
      await Promise.resolve();
    });

    expect(result.current.pending).toBe(false);
  });
});
