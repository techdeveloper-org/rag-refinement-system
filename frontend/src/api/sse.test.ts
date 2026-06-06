import { describe, expect, it, vi } from "vitest";
import { AnswerStreamClient, decodeAnswerMessage, parseSseBlock } from "@/api/sse";
import type { AnswerFinalEvent, Problem, TokenEvent } from "@/api/types";
import { sseResponse } from "@/test/fixtures";

const REQUEST = { document_id: "doc_abc123", query: "What is the warranty?" };

/** Collect the token text, final event, and error problem from a stream run. */
function collectHandlers(): {
  tokens: string[];
  finals: AnswerFinalEvent[];
  errors: Problem[];
  onToken: (event: TokenEvent) => void;
  onFinal: (event: AnswerFinalEvent) => void;
  onError: (problem: Problem) => void;
} {
  const tokens: string[] = [];
  const finals: AnswerFinalEvent[] = [];
  const errors: Problem[] = [];
  return {
    tokens,
    finals,
    errors,
    onToken: (event) => tokens.push(event.token),
    onFinal: (event) => finals.push(event),
    onError: (problem) => errors.push(problem),
  };
}

describe("parseSseBlock", () => {
  it("parses event and concatenated data lines", () => {
    const message = parseSseBlock("event: token\ndata: {\"token\":\"hi\"}");
    expect(message).toEqual({ event: "token", data: '{"token":"hi"}' });
  });

  it("returns null for a comment-only block", () => {
    expect(parseSseBlock(": keep-alive")).toBeNull();
  });
});

describe("decodeAnswerMessage", () => {
  it("maps malformed JSON to an error event", () => {
    const event = decodeAnswerMessage({ event: "token", data: "not json" });
    expect(event?.kind).toBe("error");
  });

  it("rejects a final event missing required fields", () => {
    const event = decodeAnswerMessage({ event: "final", data: '{"answer":"x"}' });
    expect(event?.kind).toBe("error");
  });
});

describe("AnswerStreamClient.streamAnswer", () => {
  it("yields token events then the terminal final event in order", async () => {
    const sse =
      'event: token\ndata: {"token":"The "}\n\n' +
      'event: token\ndata: {"token":"warranty "}\n\n' +
      'event: token\ndata: {"token":"is 24 months."}\n\n' +
      'event: final\ndata: {"answer":"The warranty is 24 months.","citations":[{"section_title":"Warranty & Support","page_start":142,"page_end":148}],"routing":{"sections":["sec_warranty"],"confidence":[0.94],"fallback":false}}\n\n';
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(sse));
    const client = new AnswerStreamClient({
      baseUrl: "http://localhost:8000",
      getToken: () => "jwt-token",
      fetchImpl,
    });
    const handlers = collectHandlers();

    await client.streamAnswer(REQUEST, handlers);

    expect(handlers.tokens).toEqual(["The ", "warranty ", "is 24 months."]);
    expect(handlers.tokens.join("")).toBe("The warranty is 24 months.");
    expect(handlers.finals).toHaveLength(1);
    expect(handlers.finals[0]?.answer).toBe("The warranty is 24 months.");
    expect(handlers.finals[0]?.citations[0]?.section_title).toBe("Warranty & Support");
    expect(handlers.finals[0]?.routing.confidence).toEqual([0.94]);
    expect(handlers.errors).toHaveLength(0);
  });

  it("sends the JWT bearer auth header and Accept: text/event-stream", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(""));
    const client = new AnswerStreamClient({
      baseUrl: "http://localhost:8000",
      getToken: () => "jwt-token",
      fetchImpl,
    });

    await client.streamAnswer(REQUEST, collectHandlers());

    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer jwt-token");
    expect(headers["Accept"]).toBe("text/event-stream");
  });

  it("surfaces a mid-stream SSE error event as an onError Problem (AC-ADV-002)", async () => {
    const sse =
      'event: token\ndata: {"token":"Partial "}\n\n' +
      'event: error\ndata: {"type":"about:blank","title":"Internal Server Error","status":500,"code":"INTERNAL_ERROR","detail":"Generation failed mid-stream."}\n\n';
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(sse));
    const client = new AnswerStreamClient({
      baseUrl: "http://localhost:8000",
      getToken: () => null,
      fetchImpl,
    });
    const handlers = collectHandlers();

    await client.streamAnswer(REQUEST, handlers);

    expect(handlers.tokens).toEqual(["Partial "]);
    expect(handlers.finals).toHaveLength(0);
    expect(handlers.errors).toHaveLength(1);
    expect(handlers.errors[0]?.code).toBe("INTERNAL_ERROR");
  });

  it("reports a pre-stream RFC-7807 error before any tokens", async () => {
    const problem: Problem = {
      type: "https://api/problems/unauthorized",
      title: "Unauthorized",
      status: 401,
      code: "UNAUTHORIZED",
      detail: "API key or bearer token is missing or invalid.",
    };
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(problem), {
        status: 401,
        headers: { "Content-Type": "application/problem+json" },
      }),
    );
    const client = new AnswerStreamClient({
      baseUrl: "http://localhost:8000",
      getToken: () => null,
      fetchImpl,
    });
    const handlers = collectHandlers();

    await client.streamAnswer(REQUEST, handlers);

    expect(handlers.tokens).toHaveLength(0);
    expect(handlers.finals).toHaveLength(0);
    expect(handlers.errors[0]?.code).toBe("UNAUTHORIZED");
    expect(handlers.errors[0]?.status).toBe(401);
  });

  it("reports a network failure as a synthetic NETWORK_ERROR problem", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("connection refused"));
    const client = new AnswerStreamClient({
      baseUrl: "http://localhost:8000",
      getToken: () => null,
      fetchImpl,
    });
    const handlers = collectHandlers();

    await client.streamAnswer(REQUEST, handlers);

    expect(handlers.errors[0]?.code).toBe("NETWORK_ERROR");
  });
});
