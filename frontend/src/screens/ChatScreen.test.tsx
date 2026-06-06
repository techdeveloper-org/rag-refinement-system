import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatScreen } from "@/screens/ChatScreen";
import type { ApiClient } from "@/api/client";
import type { DocumentId, TocResponse } from "@/api/types";

const EMPTY_TOC: TocResponse = { document_id: "doc_a", fallback_only: false, toc: [] };
const DOC_A: DocumentId = "doc_a";
const DOC_B: DocumentId = "doc_b";

/**
 * Build a fake ApiClient whose getDocumentToc resolves to an empty TOC.
 *
 * Each call returns a distinct object so a test can change the client prop
 * identity without changing its behavior.
 */
function fakeClient(): ApiClient {
  return {
    getDocumentToc: vi.fn().mockResolvedValue(EMPTY_TOC),
  } as unknown as ApiClient;
}

/** Submit a question through the composer to start an in-flight stream turn. */
async function askQuestion(text: string): Promise<void> {
  const user = userEvent.setup();
  const input = screen.getByLabelText(/ask a question about/i);
  await user.type(input, text);
  await user.click(screen.getByRole("button", { name: /send/i }));
}

describe("ChatScreen (FE-A6 reset decoupled from client prop)", () => {
  beforeEach(() => {
    const neverResolves = new ReadableStream<Uint8Array>({ start() {} });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(neverResolves, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps turns when the client prop identity changes but documentId does not", async () => {
    const firstClient = fakeClient();
    const { rerender } = render(
      <ChatScreen client={firstClient} documentId={DOC_A} documentTitle="Motor Manual" />,
    );
    await waitFor(() => {
      expect(firstClient.getDocumentToc).toHaveBeenCalledWith(DOC_A);
    });

    await askQuestion("What is the warranty?");
    expect(screen.getByText("What is the warranty?")).toBeInTheDocument();

    const secondClient = fakeClient();
    rerender(
      <ChatScreen client={secondClient} documentId={DOC_A} documentTitle="Motor Manual" />,
    );
    await waitFor(() => {
      expect(secondClient.getDocumentToc).toHaveBeenCalledWith(DOC_A);
    });

    expect(screen.getByText("What is the warranty?")).toBeInTheDocument();
  });

  it("clears turns when documentId changes", async () => {
    const firstClient = fakeClient();
    const { rerender } = render(
      <ChatScreen client={firstClient} documentId={DOC_A} documentTitle="Motor Manual" />,
    );
    await waitFor(() => {
      expect(firstClient.getDocumentToc).toHaveBeenCalledWith(DOC_A);
    });

    await askQuestion("What is the warranty?");
    expect(screen.getByText("What is the warranty?")).toBeInTheDocument();

    const secondClient = fakeClient();
    rerender(
      <ChatScreen client={secondClient} documentId={DOC_B} documentTitle="Other Manual" />,
    );
    await waitFor(() => {
      expect(secondClient.getDocumentToc).toHaveBeenCalledWith(DOC_B);
    });

    expect(screen.queryByText("What is the warranty?")).toBeNull();
  });
});
