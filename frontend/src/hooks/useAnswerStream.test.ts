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
