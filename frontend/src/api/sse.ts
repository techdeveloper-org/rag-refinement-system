import { ApiError, isProblem, syntheticProblem, toApiError } from "@/api/errors";
import type { TokenProvider } from "@/api/client";
import type { AnswerFinalEvent, AnswerRequest, Problem, TokenEvent } from "@/api/types";

/**
 * Discriminated union of events emitted by the `/v1/answer` SSE stream
 * (HLD section 7.3; openapi.yaml SseAnswerStream oneOf). The consumer yields:
 *
 * - `token` repeatedly (incremental answer text),
 * - exactly one terminal `final` (the completed cited answer + routing), and
 * - `error` if the server sends a mid-stream `event: error` (Problem).
 */
export type SseAnswerEvent =
  | { kind: "token"; data: TokenEvent }
  | { kind: "final"; data: AnswerFinalEvent }
  | { kind: "error"; problem: Problem };

/** Callbacks for streamed answer consumption. */
export interface AnswerStreamHandlers {
  onToken: (event: TokenEvent) => void;
  onFinal: (event: AnswerFinalEvent) => void;
  onError: (problem: Problem) => void;
}

/** Configuration for the SSE answer client. */
export interface SseClientConfig {
  baseUrl: string;
  getToken: TokenProvider;
  fetchImpl?: typeof fetch;
}

/** A single parsed SSE message (one `event:`/`data:` block). */
interface SseMessage {
  event: string;
  data: string;
}

const DEFAULT_EVENT = "message";

/**
 * Decide whether a thrown error (or signal state) represents a deliberate
 * abort rather than a genuine transport failure.
 *
 * A deliberate abort (re-ask, document switch, or unmount via
 * `AbortController.abort()`) must stay silent and never surface as an error
 * turn; only real failures should reach `onError`.
 *
 * @param error - The value caught from a fetch/read rejection.
 * @param signal - The optional abort signal for the in-flight request.
 * @returns True when the failure is an intentional cancellation.
 */
function isAbort(error: unknown, signal: AbortSignal | undefined): boolean {
  if (signal?.aborted === true) {
    return true;
  }
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Parse a completed SSE block (lines between blank-line delimiters) into an
 * {@link SseMessage}. Concatenates multiple `data:` lines with newlines per the
 * SSE spec; ignores comment lines (starting with `:`).
 *
 * @param block - Raw text of one SSE event block (no trailing blank line).
 * @returns The parsed message, or null when the block carries no data.
 */
export function parseSseBlock(block: string): SseMessage | null {
  let event = DEFAULT_EVENT;
  const dataLines: string[] = [];

  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/\r$/u, "");
    if (line.length === 0 || line.startsWith(":")) {
      continue;
    }
    const colonIndex = line.indexOf(":");
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex);
    const valueRaw = colonIndex === -1 ? "" : line.slice(colonIndex + 1);
    const value = valueRaw.startsWith(" ") ? valueRaw.slice(1) : valueRaw;

    if (field === "event") {
      event = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: dataLines.join("\n") };
}

/**
 * Decode an SSE message's JSON `data` into a typed {@link SseAnswerEvent}.
 *
 * Maps `event: token` -> TokenEvent, `event: final` -> AnswerFinalEvent, and
 * `event: error` -> Problem. Any malformed JSON or unrecognized event becomes
 * an `error` event so a broken stream is surfaced, never silently dropped
 * (AC-ADV-002).
 *
 * @param message - The parsed SSE message to decode.
 * @returns A typed answer event, or null for ignorable keep-alive frames.
 */
export function decodeAnswerMessage(message: SseMessage): SseAnswerEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(message.data) as unknown;
  } catch {
    return {
      kind: "error",
      problem: syntheticProblem(502, "MALFORMED_STREAM", "The answer stream sent malformed data."),
    };
  }

  switch (message.event) {
    case "token": {
      if (isTokenEvent(payload)) {
        return { kind: "token", data: payload };
      }
      return malformedStreamEvent();
    }
    case "final": {
      if (isAnswerFinalEvent(payload)) {
        return { kind: "final", data: payload };
      }
      return malformedStreamEvent();
    }
    case "error": {
      if (isProblem(payload)) {
        return { kind: "error", problem: payload };
      }
      return malformedStreamEvent();
    }
    default:
      return null;
  }
}

function malformedStreamEvent(): SseAnswerEvent {
  return {
    kind: "error",
    problem: syntheticProblem(502, "MALFORMED_STREAM", "The answer stream sent an unexpected event."),
  };
}

function isTokenEvent(value: unknown): value is TokenEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  return typeof (value as Record<string, unknown>)["token"] === "string";
}

function isAnswerFinalEvent(value: unknown): value is AnswerFinalEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record["answer"] === "string" &&
    Array.isArray(record["citations"]) &&
    typeof record["routing"] === "object" &&
    record["routing"] !== null
  );
}

/**
 * Iterate the events of a `text/event-stream` body, yielding one typed
 * {@link SseAnswerEvent} per complete SSE block.
 *
 * Buffers partial chunks across reads and splits on the blank-line delimiter.
 * Honors `AbortSignal` cancellation between reads so an unmounted view stops
 * consuming promptly.
 *
 * @param stream - The readable byte stream from the SSE response body.
 * @param signal - Optional abort signal to stop iteration early.
 */
export async function* iterateSseStream(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseAnswerEvent, void, void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      if (signal?.aborted === true) {
        return;
      }
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });

      let delimiterIndex = buffer.indexOf("\n\n");
      while (delimiterIndex !== -1) {
        const block = buffer.slice(0, delimiterIndex);
        buffer = buffer.slice(delimiterIndex + 2);
        const message = parseSseBlock(block);
        if (message !== null) {
          const event = decodeAnswerMessage(message);
          if (event !== null) {
            yield event;
          }
        }
        delimiterIndex = buffer.indexOf("\n\n");
      }
    }

    const tail = parseSseBlock(buffer);
    if (tail !== null) {
      const event = decodeAnswerMessage(tail);
      if (event !== null) {
        yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * SSE client for the streaming `POST /v1/answer` personal-tool endpoint.
 *
 * Opens the stream with JWT bearer auth, surfaces a pre-stream RFC 7807 error
 * (auth/validation/not-found) before any tokens, then dispatches `token`,
 * `final`, and mid-stream `error` events to the supplied handlers.
 */
export class AnswerStreamClient {
  private readonly baseUrl: string;
  private readonly getToken: TokenProvider;
  private readonly fetchImpl: typeof fetch;

  public constructor(config: SseClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/u, "");
    this.getToken = config.getToken;
    this.fetchImpl = config.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  /**
   * Stream a cited answer for a question.
   *
   * Emits tokens as they arrive, then the terminal final event. A non-streaming
   * error (status not 2xx, or no body) is reported via `onError` before the
   * stream starts; a mid-stream `event: error` is reported via `onError` too,
   * so it is never silently dropped (AC-ADV-002).
   *
   * A deliberate abort stays silent on every path - the fetch rejection, the
   * non-2xx and null-body post-fetch branches, and the read-loop rejection - so
   * a user-cancelled turn never surfaces a spurious error.
   *
   * @param request - The AnswerRequest (document_id + query, plus optionals).
   * @param handlers - Token/final/error callbacks.
   * @param signal - Optional abort signal to cancel the stream.
   * @throws Never throws for protocol errors - all failures route to onError.
   */
  public async streamAnswer(
    request: AnswerRequest,
    handlers: AnswerStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    };
    if (token !== null) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}/v1/answer`, {
        method: "POST",
        headers,
        body: JSON.stringify(request),
        ...(signal === undefined ? {} : { signal }),
      });
    } catch (error) {
      if (isAbort(error, signal)) {
        return;
      }
      handlers.onError(
        syntheticProblem(0, "NETWORK_ERROR", "Could not reach the answer service."),
      );
      return;
    }

    if (!response.ok) {
      if (isAbort(undefined, signal)) {
        return;
      }
      const problem = await this.parsePreStreamProblem(response);
      handlers.onError(problem);
      return;
    }

    if (response.body === null) {
      if (isAbort(undefined, signal)) {
        return;
      }
      handlers.onError(
        syntheticProblem(502, "EMPTY_STREAM", "The answer stream returned no data."),
      );
      return;
    }

    try {
      for await (const event of iterateSseStream(response.body, signal)) {
        switch (event.kind) {
          case "token":
            handlers.onToken(event.data);
            break;
          case "final":
            handlers.onFinal(event.data);
            break;
          case "error":
            handlers.onError(event.problem);
            break;
          default: {
            const exhaustive: never = event;
            throw new Error(`Unhandled SSE event: ${JSON.stringify(exhaustive)}`);
          }
        }
      }
    } catch (error) {
      if (isAbort(error, signal)) {
        return;
      }
      handlers.onError(
        syntheticProblem(0, "NETWORK_ERROR", "Could not reach the answer service."),
      );
    }
  }

  /** Parse a pre-stream non-2xx response into a Problem (RFC 7807). */
  private async parsePreStreamProblem(response: Response): Promise<Problem> {
    let body: unknown = null;
    try {
      body = (await response.json()) as unknown;
    } catch {
      body = null;
    }
    const error: ApiError = toApiError(response.status, body);
    return error.problem;
  }
}
